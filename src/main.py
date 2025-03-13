import requests
from bs4 import BeautifulSoup
import polars as pd
import csv
import click
import re
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from src.filters import filter_athlete_results

from .scraper import scrape_athlete_result_page


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

load_dotenv()
@click.command()
@click.option('--athlete_name', default=lambda: os.getenv('ATHLETE_NAME'), required=False, help="Athlete's name to search for on USA Cycling results website. Can also be set via .env or ATHLETE_NAME env var.")
@click.option(
    '--category', '--cat', 
    type=click.Choice(["1","2","3","4","5"]),
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
def main(athlete_name, category, lookback, discipline):
    if not athlete_name or not category or not lookback or not discipline:
        raise click.UsageError("Missing required option(s). Please provide athlete_name, category, discipline, and lookback either via command line or environment variables.")
    
    athlete_results = scrape_athlete_result_page(athlete_name)
    athlete_results_filtered = filter_athlete_results(athlete_results, lookback, discipline)

    breakpoint()

if __name__ == "__main__":
    main()
