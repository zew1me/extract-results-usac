from datetime import date, datetime
import re
from typing import List
import requests
from requests import Session
from bs4 import BeautifulSoup
from pydantic import HttpUrl
from urllib.parse import quote_plus, urlparse, urlunparse, parse_qs, urlencode

from src.models import AthleteResult, AthleteResultHeat, Heat, RaceEvent, RaceSeries

def split_place(place_participant):
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

def scrape_athlete_result_page(athlete_name) -> List[AthleteResult]:
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
            pass
        else:
            cols = row.find_all('td')
            if len(cols) > 1:
                place_participant = cols[0].get_text(strip=True)
                place, participant_count = split_place(place_participant)
                points = cols[1].get_text(strip=True)
                points = None if points == '-' else float(points)
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

def extract_html(data):
    if data.get("error") == 0:
        return data.get("message")
    else:
        raise RuntimeError(f"Server returned an error: {data.get('message')}")

def extract_race_date(soup: BeautifulSoup) -> date:
    bold_tag = soup.find("b")

    if not bold_tag:
        raise RuntimeError("No <b> tag found.")

    match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", bold_tag.get_text())
    if not match:
        raise RuntimeError("No valid date found in <b> tag.")

    return datetime.strptime(match.group(1), "%m/%d/%Y").date()


def scrape_athlete_race_result(): 
    return AthleteResultHeat()

def scrape_heat(session: Session, race_id: str, heat_name: str):
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
    response = session.get(ajax_url, params=params)
    response.raise_for_status()
    html = extract_html(response.json())
    soup = BeautifulSoup(html, "html.parser")

    athlete_result_row = soup.find_all("div", class_="tablerow") 
    
    for result in athlete_result_row:
        cells = result.find_all("div", class_="tablecell")
        if not cells or "header" in cells[0].get("class", []):
            continue

        place = None
        try: 
            place = int(cells[1].get_text(strip=True))
        except ValueError:
            continue # skip is DNS, DNF, ... being lenient here 

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

def scrape_race_event(session: Session, info_id: str, label: str):

    # Fetches detailed results for a single instance of a race in a series. 
    # Example: This would be a Road Race on 04/30/2024 as part of the Pacific Raceways Circuit Series 2024. 
    # It contains multiple categories within the race, each which has its own results, and are loaded through AJAX. 
    base_url = "https://legacy.usacycling.org/results/index.php"
    params = {
        "ajax": "1",
        "act": "infoid",
        "info_id": info_id,
        "label": label,
    }

    response = session.get(base_url, params=params)
    response.raise_for_status()
    html = extract_html(response.json())
    
    soup = BeautifulSoup(html, 'html.parser')

    race = RaceEvent(
        id = info_id, 
        event_name = soup.find("h3").get_text(separator=" ", strip=True),
        event_date = extract_race_date(soup) 
    )

    for li in soup.find_all("li", id=lambda x: x and x.startswith("race_")):
        race_id = li["id"].split("_")[1]
        link = li.find("a")
        heat_name = link.get_text(strip=True) if link else None
        race.heats.append(scrape_heat(session, race_id, heat_name))    

    return race


def parse_load_info_id(onclick_str: str):
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

def scrape_event_series_page(url: HttpUrl, athlete_results: List[AthleteResult]): 
    session = requests.Session()
    response = session.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')    
    title_tag = soup.find("title")
    series_title = title_tag.get_text(strip=True) if title_tag else None
    race_series = RaceSeries(
        series_name=series_title,
        permit_id=parse_qs(url.query).get("permit")[0]
    )

    races_in_series = soup.select(".tablerow")    

    athlete_results_by_date = sorted(athlete_results, key=lambda x: x.event_date) 

    for race_html in races_in_series:
        if race_html.select_one("div.tablecell.header"):
            continue

        cells = race_html.find_all("div", class_="tablecell")
        if len(cells) < 2:
            continue
        date_text = cells[1].get_text(strip=True)  # e.g. "04/30/2024"
        row_date = datetime.strptime(date_text, "%m/%d/%Y").date()

        # 4) Find matching AthleteResult objects with the same date
        matching_results = [ar for ar in athlete_results_by_date if ar.event_date == row_date]

        if matching_results:
            if (len(matching_results) > 1):
                raise ValueError(f"Multiple AthleteResult objects found for {row_date}")
                    
            race_result = matching_results[0]

            link = cells[0].find("a")
            if not link:
                continue
            onclick_val = link.get("onclick", "")
            id, label = parse_load_info_id(onclick_val)
            race_series.events.append(scrape_race_event(session, id, label)) 
        
        else:
            # No matching AthleteResult found for row_date, this is okay just because there was a race in the series
            # it doesn't mean the athlete competed in it. 
            pass

    return race_series