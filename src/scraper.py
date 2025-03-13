from datetime import datetime
from typing import List
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

from src.models import AthleteResult

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
            event_url = f"https://legacy.usacycling.org{event_link_tag.get('href')}" if event_link_tag and event_link_tag.get('href') else None

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