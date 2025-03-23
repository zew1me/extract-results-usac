from datetime import date, datetime
import re
from typing import List
from bs4 import BeautifulSoup
from pydantic import HttpUrl
from urllib.parse import quote_plus, urlparse, urlunparse, parse_qs
import json
import requests

from .models import AthleteResult, AthleteResultHeat, Heat, RaceEvent, RaceSeries
from abc import ABC, abstractmethod
from .models import AthleteResult
import os
import glob
from .models import AthleteResult, RaceSeries

class ScraperInterface(ABC):
    @abstractmethod
    def scrape_athlete_result_page(self, athlete_name: str) -> List[AthleteResult]:
        pass

    @abstractmethod
    def scrape_event_series_page(self, url: HttpUrl, athlete_results: List[AthleteResult]):
        pass
    
class CachedDataScraper(ScraperInterface): 
    def __init__(self, athlete_basename: str, event_series_basename_prefix: str, func_to_id: callable):
        self.cache = {}
        # Series cache stores RaceSeries objects keyed by a safe identifier derived from the dumped filename.
        self.series_cache = {}
        self.to_id = func_to_id

        # Load cached athlete results from JSON files dumped by main.py.
        # Expect files named like "athlete_results_dump.json" 
        athlete_file = glob.glob(os.path.join(".", f"{athlete_basename}.json"))[0]
        with open(athlete_file) as f: 
            data = json.load(f)
            # Each file is expected to be a list of athlete result dicts.
            for record in data:
                athlete_name = record.get("name")
                if athlete_name:
                    self.cache.setdefault(athlete_name, []).append(AthleteResult(**record))

        # Load cached event series results from JSON files dumped by main.py.
        # Files are expected to be named like "event_series_dump_<safe_identifier>.json"
        series_files = glob.glob(os.path.join(".", f"{event_series_basename_prefix}*.json"))
        for file in series_files:
            base = os.path.basename(file)
            identifier = base[len(event_series_basename_prefix):].replace(".json", "")
            with open(file) as f: 
                data = json.load(f)
                self.series_cache[identifier] = RaceSeries(**data)      

    def scrape_athlete_result_page(self, athlete_name: str) -> List[AthleteResult]:
        return self.cache[athlete_name]

    def scrape_event_series_page(self, url: HttpUrl, athlete_results: List[AthleteResult]):
        # Generate a safe identifier based on the URL's query by applying the regex pattern
        url_str = str(url) 
        identifier = self.to_id(url_str)
        return self.series_cache[identifier]


class WebScraper(ScraperInterface):
    def __init__(self):
        self.session = requests.Session()

    def split_place(self, place_participant):
        """
        Splits a string into (place, participant_count).

        Cases handled:
          1) "DNF" => Did not finish, so place is None.
          2) Single numeric value (e.g. "2") => place = "2", participant_count = "2".
          3) Slash-delimited (e.g. "2 / 17") => place = "2", participant_count = "17".
          4) If no value is provided, returns (None, None).

        :param place_participant: A string that might look like "2 / 17", "DNF", or "2".
        :return: A tuple (place, participant_count), both as strings or None.
        """
        if place_participant:
            if place_participant.strip().isdigit():
                place_str = participant_count = place_participant.strip()
            else:
                place_str, participant_count = map(str.strip, place_participant.split('/'))
            place = None if place_str == "DNF" else place_str
        else:
            place, participant_count = None, None
        return place, participant_count

    def extract_html(self, data):
        if data.get("error") == 0:
            return data.get("message")
        else:
            raise RuntimeError(f"Server returned an error: {data.get('message')}")

    def extract_race_date(self, soup: BeautifulSoup) -> date:
        bold_tag = soup.find("b")
        if bold_tag:           
            match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", bold_tag.get_text())
            if match: 
                return datetime.strptime(match.group(1), "%m/%d/%Y").date()

        h3_tag = soup.find("h3")
        if h3_tag:
            brs = h3_tag.find_all("br")
                # Prepare a regex pattern that matches both abbreviated and full month names.
                # It looks for one or more letters for the month, then whitespace, one or two digits, a comma, whitespace, and four digits.
            date_pattern = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})")
            for br in brs:
                next_text = br.next_sibling
                if next_text:
                    candidate = next_text.strip()
                    match = date_pattern.search(candidate)
                    if match:
                        # Extract the whole matched string, e.g., "September 14, 2024" or "Apr 14, 2024"
                        date_str = match.group(0)
                        try:
                            return datetime.strptime(date_str, "%b %d, %Y").date()
                        except ValueError:
                            try:
                                return datetime.strptime(date_str, "%B %d, %Y").date()
                            except ValueError:
                                # If parsing fails, continue to next candidate.
                                continue

        raise RuntimeError("No date found in h3 nested br or b tags.")

    def parse_load_info_id_onclick(self, onclick_str: str):
        """
        Extracts the numeric ID and label from an onclick string like:
          loadInfoID(149913,'Road Race 04/30/2024')
          

        Returns (race_id, label) as strings
        """
        match = re.search(r"loadInfoID\((\d+),\s*'([^']+)'\)", onclick_str)
        if match:
            race_id = match.group(1)
            label = match.group(2)
            return race_id, label
        raise ValueError(f"Could not extract info_id and label from {onclick_str}")
    
    def parse_load_info_id_script(self, script_text: str):
        """
        Extracts the numeric ID and label from a script text like:
          \n\tloadInfoID(149455,null,0);\n
        """
        def js_value_to_python(val: str):
            val = val.strip()
            if val == "null":
                return None
            # Remove surrounding quotes if present.
            if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                return val[1:-1]
            return val

        match = re.search(r"\s*loadInfoID\(\s*(\d+)\s*,\s*([^,]+?)\s*,\s*0\s*\);\s*", script_text)
        if match:
            info_id = match.group(1)
            label = js_value_to_python(match.group(2))
            return info_id, label 
        raise ValueError(f"Could not extract info_id and label from {script_text}")

    def scrape_athlete_result_page(self, athlete_name) -> List[AthleteResult]:
        url = f'https://legacy.usacycling.org/results/index.php?compid={quote_plus(athlete_name)}'
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        table = soup.find('table')
        if not table:
            return []

        results = []
        rows = table.find_all('tr')
        event_date = None
        event_title = None
        event_details_dict = None

        for row in rows:
            event_header = row.find('span', class_='homearticleheader')
            if event_header:
                event_url = None
                event_info = event_header.get_text(strip=True)
                if '-' in event_info:
                    event_date_str, event_title = map(str.strip, event_info.split('-', 1))
                    event_date = datetime.strptime(event_date_str, "%m/%d/%Y")
                else:
                    event_date = None
                    event_title = event_info.strip()

                event_link_tag = event_header.find_parent().find('a')
                event_query_param = event_link_tag.get('href').lstrip('?') if event_link_tag else None
                event_url = urlunparse(urlparse(url)._replace(query=event_query_param)) if event_query_param else None

                parent_td = event_header.find_parent('td')
                details_spans = parent_td.find_all('span', title=True) if parent_td else []
                event_details_dict = {span.get('title'): span.get_text(strip=True) for span in details_spans}
            else:
                cols = row.find_all('td')
                if len(cols) > 1:
                    place_participant = cols[0].get_text(strip=True)
                    place, participant_count = self.split_place(place_participant)
                    points_text = cols[1].get_text(strip=True)
                    points = None if points_text == '-' else float(points_text)
                    name = cols[2].get_text(strip=True)
                    usac_number = cols[3].get_text(strip=True)
                    time = cols[4].get_text(strip=True)
                    bib = cols[5].get_text(strip=True)
                    team = cols[6].get_text(strip=True)

                    result = AthleteResult(
                        event_date=event_date,
                        event_title=event_title,
                        event_details=event_details_dict,
                        event_url=event_url,
                        place=place,
                        participant_count=participant_count,
                        points=points,
                        name=name,
                        usac_number=usac_number,
                        time=time,
                        bib=bib,
                        team=team
                    )
                    results.append(result)

        return results

    def scrape_athlete_race_result(self): 
        return AthleteResultHeat()

    def scrape_heat(self, race_id: str, heat_name: str):
        heat = Heat(
            heat_id=race_id,
            heat_name=heat_name
        )

        ajax_url = "https://legacy.usacycling.org/results/index.php"
        params = {
            "ajax": "1",
            "act": "loadresults",
            "race_id": heat.heat_id
        }
        response = self.session.get(ajax_url, params=params)
        response.raise_for_status()
        html = self.extract_html(response.json())
        soup = BeautifulSoup(html, "html.parser")

        athlete_result_rows = soup.find_all("div", class_="tablerow")
        for result in athlete_result_rows:
            cells = result.find_all("div", class_="tablecell")
            if not cells or "header" in cells[0].get("class", []):
                continue

            try:
                place = int(cells[1].get_text(strip=True))
            except ValueError:
                continue  # skip if DNS, DNF, etc.

            name_cell = cells[4]
            name_link = name_cell.find("a")
            name = name_link.get_text(strip=True) if name_link else name_cell.get_text(strip=True)
            category_match = re.search(r"\(([^)]+)\)", name_cell.get_text())
            category = category_match.group(1) if category_match else None

            usac_cell = cells[8]
            usac_number_link = usac_cell.find("a")
            try:
                usac_number = int(usac_number_link.get_text(strip=True)) if usac_number_link else None
            except (ValueError, AttributeError):
                usac_number = None

            bib = cells[9].get_text(strip=True)
            team = cells[10].get_text(strip=True)

            heat.participants.append(AthleteResultHeat(
                place=place,
                name=name,
                category=category,
                usac_number=usac_number,
                bib=bib,
                team=team
            ))

        return heat

    def scrape_race_event(self, info_id: str, label: str):
        # Fetches detailed results for a single instance of a race in a series.
        base_url = "https://legacy.usacycling.org/results/index.php"
        params = {
            "ajax": "1",
            "act": "infoid",
            "info_id": info_id,
            "label": label,
        }

        response = self.session.get(base_url, params=params)
        response.raise_for_status()
        html = self.extract_html(response.json())
        soup = BeautifulSoup(html, 'html.parser')

        race = RaceEvent(
            id=info_id, 
            event_name=soup.find("h3").get_text(separator=" ", strip=True),
            event_date=self.extract_race_date(soup)
        )

        for li in soup.find_all("li", id=lambda x: x and x.startswith("race_")):
            race_id = li["id"].split("_")[1]
            link = li.find("a")
            heat_name = link.get_text(strip=True) if link else None
            race.heats.append(self.scrape_heat(race_id, heat_name))

        return race
    
    def process_inline_event(self, event_label):
        raise NotImplementedError("process_inline_event() not implemented")


    def scrape_event_series_page(self, url: HttpUrl, athlete_results: List[AthleteResult]):
        response = self.session.get(str(url))
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find("title")
        series_title = title_tag.get_text(strip=True) if title_tag else None
        race_series = RaceSeries(
            series_name=series_title,
            permit_id=parse_qs(url.query).get("permit")[0]
        )

        races_in_series = soup.select(".tablerow")
        if not races_in_series: #check for inline
            script_tag = soup.find("script", text=re.compile("loadInfoID"))
            id, label = self.parse_load_info_id_script(script_tag.get_text())
            race_event = self.scrape_race_event(id, label)
            race_series.events.append(race_event)
        else:    
            athlete_results_by_date = sorted(athlete_results, key=lambda x: x.event_date)

            for race_html in races_in_series:
                if race_html.select_one("div.tablecell.header"):
                    continue

                cells = race_html.find_all("div", class_="tablecell")
                if len(cells) < 2:
                    continue
                date_text = cells[1].get_text(strip=True)  # e.g. "04/30/2024"
                row_date = datetime.strptime(date_text, "%m/%d/%Y").date()

                # Find matching AthleteResult objects with the same date
                matching_results = [ar for ar in athlete_results_by_date if ar.event_date == row_date]

                if matching_results:
                    if len(matching_results) > 1:
                        raise ValueError(f"Multiple AthleteResult objects found for {row_date}")

                    link = cells[0].find("a")
                    if not link:
                        continue
                    onclick_val = link.get("onclick", "")
                    info_id, label = self.parse_load_info_id_onclick(onclick_val)
                    race_series.events.append(self.scrape_race_event(info_id, label))
                else:
                    # No matching AthleteResult found for row_date; this is acceptable.
                    pass

        return race_series
