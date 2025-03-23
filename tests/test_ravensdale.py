from datetime import date

from pydantic import HttpUrl
from src.scraper import WebScraper
from src.models import AthleteResult

def test_ravensdale_event():
    # Create a dummy AthleteResult matching the Ravensdale event in your dump
    dummy_result = AthleteResult(
         event_date = date(2024, 4, 14),
         event_title = "Ravensdale Spring Classic presented by Apex, powered by Bloom",
         event_details = {"discipline": "RR", "class": "Master", "age": "40+"},
         event_url = "https://legacy.usacycling.org/results/index.php?permit=2024-12061",
         place = "2",
         participant_count = "11",
         points = 444.08,
         name = "Nummoo Salamoteru",
         usac_number = "6477",
         time = "1:43:51",
         bib = "601",
         team = "Hamburg in paradise"
    )
    scraper = WebScraper()
    # Call the scraper using only our dummy athlete result
    series = scraper.scrape_event_series_page(HttpUrl("https://legacy.usacycling.org/results/index.php?permit=2024-12061"), [dummy_result])
    # Print or assert properties for debugging
    print(series)
    assert series.series_name is not None
    # Optionally, check that the event with the matching date exists
    matching_events = [event for event in series.events if event.event_date == dummy_result.event_date]
    assert matching_events, "No event found for the given date"

if __name__ == "__main__":
    test_ravensdale_event()