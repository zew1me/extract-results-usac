from itertools import groupby
import json
from operator import attrgetter
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import polars as pd
import csv
import click
import re
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from pydantic import BaseModel, HttpUrl
from src.container import Container
from src.filters import filter_athlete_results
from src.models import AthleteResult, AthleteResultDetailed
from collections import defaultdict
from dateutil.parser import isoparse
from fastapi.encoders import jsonable_encoder

CACHE_ATHLETE_BASENAME = "athlete_results_dump"
CACHE_EVENT_SERIES_BASENAME_PREFIX = "event_series_dump_"

def to_file_basename(prefix: str, identifier: str) -> str:
    return f"{prefix}{identifier}"


def to_file_id(url: HttpUrl) -> str:
    return re.sub(r'\W+', '', str(url))

def parse_dates(obj):
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    elif isinstance(obj, datetime.date):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: parse_dates(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [parse_dates(v) for v in obj]
    elif isinstance(obj, str):
        try:
            dt = isoparse(obj)
            return dt.isoformat()
        except ValueError:
            return obj
    else:
        return obj

def group_by_event_url(results: list[AthleteResult]) -> dict[HttpUrl, list[AthleteResult]]:
    """
    Groups a list of AthleteResult objects by their event_url.
    Returns a dictionary where each key is a distinct event_url,
    and the value is a list of AthleteResult objects for that URL.
    """
    grouped = defaultdict(list)
    for r in results:
        grouped[r.event_url].append(r)
    return dict(grouped)

def lookback_callback(_, __, value):
    """
    Parses a flexible lookback period (e.g., '2y', '36mo') into a timedelta.
    
    This is a Click callback, so it accepts (ctx, param, value).
    If 'value' is None or empty, returns None.
    Otherwise, it expects a string with a number followed by a time unit:
      - 'y', 'yr', 'yrs', 'year', 'years' => years
      - 'mo', 'month', 'months' => months
      - 'w', 'wk', 'wks', 'week', 'weeks' => weeks
      - 'd', 'day', 'days' => days
    Raises:
        BadParameter: If the format is invalid or if the unit is unsupported.
    """

    if not value:
        return None

    match = re.match(r'(\d+)([a-zA-Z]+)', value)
    if not match:
        raise click.BadParameter(f"Invalid lookback period format: {value}")

    num_str, unit = match.groups()
    try:
        amount = int(num_str)
    except ValueError:
        raise click.BadParameter(f"'{num_str}' is not a valid integer.")
    
    unit = unit.lower()
    if unit in ('y', 'yr', 'yrs', 'year', 'years'):
        delta = relativedelta(years=amount)
    elif unit in ('mo', 'month', 'months'):
        delta = relativedelta(months=amount)
    elif unit in ('w', 'wk', 'wks', 'week', 'weeks'):
        delta = relativedelta(weeks=amount)
    elif unit in ('d', 'day', 'days'):
        delta = timedelta(days=amount)
    else:
        raise click.BadParameter(f"Unsupported time unit: {unit}")

    return (datetime.now() - delta).date()


def discipline_callback(_, __, value):
    if not value:
        return None
    value = value.lower()
    if value == "cyclocross":
        return "cx"
    return value

def parse_heat_category(s: str) -> tuple[Optional[int], str]:
    '''
    Determine the number of participants in the athlete's category ∂
    and the athlete's placement within that category.
    '''
    if s is None:
        return None, None
    match = re.search(r"(\d+)\s*-\s*Cat(\d+)", s, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid category format: {s}")
    return int(match.group(1)), match.group(2)

load_dotenv()
@click.command()
@click.option('--athlete_name', default=lambda: os.getenv('ATHLETE_NAME'), required=False, help="Athlete's name to search for on USA Cycling results website. Can also be set via .env or ATHLETE_NAME env var.")
@click.option(
    '--category', '--cat', 
    type=click.Choice(["1", "2", "3", "4", "5"]),
    default=lambda: os.getenv('CATEGORY'), 
    required=False,
    help="Relevant category to filter results for (1-5). Can also be set via .env or CATEGORY env var.")
@click.option(
    '--lookback', 
    default=lambda: os.getenv('LOOKBACK'), 
    required=False, 
    callback=lookback_callback,
    help="Lookback period (e.g., '2y' for 2 years, '36mo' for 36 months). Can also be set via .env or LOOKBACK env var.")
@click.option(
    '--discipline', 
    type=click.Choice(["cx", "road", "cyclocross"], case_sensitive=False),
    default=lambda: os.getenv('DISCIPLINE'), 
    required=False, 
    callback=discipline_callback,
    help="Discipline to filter results for. Can also be set via .env or DISCIPLINE env var.")
@click.option(
    '--dump', 
    is_flag=True, 
    default=False, 
    help="Dump raw results to JSON files.")
@click.option(
    '--use-cached',
    is_flag=True,
    default=False,
    help="Use cached results. Mutually exclusive with --dump."
)
def main(athlete_name, category, lookback, discipline, dump, use_cached):
    if dump and use_cached:
        raise click.UsageError("--dump and --use-cached cannot be used together. Please choose one.")

    def dump_to_json(prefix: str, data, identifier: str = None):
        if dump: 
            file_name = to_file_basename(prefix, identifier) if identifier else prefix
            file_name += ".json"
            encoded = jsonable_encoder(data)
            with open(file_name, "w") as file:
                json.dump(encoded, file) 

    if not athlete_name or not category or not lookback or not discipline:
        raise click.UsageError("Missing required option(s). Please provide athlete_name, category, discipline, and lookback either via command line or environment variables.")

    if use_cached:
        container = Container(config={
            "athlete_basename": CACHE_ATHLETE_BASENAME,
            "event_series_basename_prefix": CACHE_EVENT_SERIES_BASENAME_PREFIX,
            "to_id": to_file_id
        })
    else:
        container = Container()
    scraper = container.scraper()

    athlete_results = scraper.scrape_athlete_result_page(athlete_name)
    dump_to_json(CACHE_ATHLETE_BASENAME, athlete_results)
        
    athlete_results_filtered = filter_athlete_results(athlete_results, lookback, discipline)
    detailed_results = []
    groups = group_by_event_url(athlete_results_filtered)
    for athlete_result_url, group in groups.items():
        race_series_results = scraper.scrape_event_series_page(athlete_result_url, group)
        dump_to_json(CACHE_EVENT_SERIES_BASENAME_PREFIX, race_series_results, to_file_id(athlete_result_url))
        # Group athlete results by event_date in this URL's group
        athlete_results_by_date = defaultdict(list)
        for ar in group:
            athlete_results_by_date[ar.event_date].append(ar)

        for event in race_series_results.events:
            # Only process athlete results matching the event date
            matching_results = athlete_results_by_date.get(event.event_date)
            if not matching_results:
                continue
            for heat in event.heats:
                for athlete_result in matching_results:
                    matches = [p for p in heat.participants if p.name == athlete_result.name]
                    if not matches:
                        continue
                    if len(matches) > 1:
                        raise ValueError(
                            f"Multiple heat entries found for athlete {athlete_result.name} in heat {heat.heat_id}."
                        )
                    heat_result = matches[0]

                    parsed_place, parsed_cat = parse_heat_category(heat_result.category)
                    heat_result.place = parsed_place  # update the athlete's heat placement
                    participants_in_cat = 0
                    for p in heat.participants:
                        p_place, p_cat = parse_heat_category(p.category)
                        p.parsed_place = p_place
                        p.parsed_cat = p_cat
                        if p_cat == parsed_cat:
                            participants_in_cat += 1
                    sorted_participants = sorted(
                        [p for p in heat.participants if p.parsed_cat == parsed_cat],
                        key=lambda p: float('inf') if (p.parsed_place is None or p.parsed_place == 0) else p.parsed_place
                    )
                    place_in_cat = sorted_participants.index(heat_result) + 1

                    detailed_result = AthleteResultDetailed.from_components(
                        result=athlete_result,
                        heat_result=heat_result,
                        heat=heat,
                        event=event,
                        series=race_series_results,
                        participants_in_cat=participants_in_cat,
                        place_in_cat=place_in_cat
                    )
                    detailed_results.append(detailed_result)
        
    def flatten_dict(d, parent_key="", sep="_"):
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(flatten_dict(v, new_key, sep=sep))
            else:
                items[new_key] = v
        return items


    flat_results = [flatten_dict(jsonable_encoder(dr)) for dr in detailed_results]
    if flat_results:
        fieldnames = [
            "event_date",
            "event_details_age",
            "event_details_class",
            "event_details_discipline",
            "event_title",
            "heat_name",
            "place",
            "participant_count",
            "place_in_cat",
            "participants_in_cat",
            "heat_id",
            "event_url",
        ]
        with open("detailed_results_export.csv", "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in flat_results:
                filtered_row = {field: row.get(field) for field in fieldnames}
                writer.writerow(filtered_row)

if __name__ == "__main__":
    main()
