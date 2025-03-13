from datetime import datetime, timedelta
from typing import List

from src.models import AthleteResult

def filter_athlete_results(
    results: List[AthleteResult],
    cutoff_date: datetime,
    discipline: str
) -> List[AthleteResult]:
    """
    Filters the given athlete results to those that:
      1) Have an event_date >= (now - lookback).
      2) Have a non-None place.
      3) event_details["discipline"] matches one of the mapped disciplines for 'discipline'.

    :param results: A list of AthleteResult objects to filter.
    :param lookback: A timedelta representing how far back to include results.
    :param discipline: A string indicating the discipline category (e.g. 'road', 'cx', etc.).
    :return: A new list of AthleteResult objects meeting all criteria.
    """
    discipline_map = {
        "road": {"Road", "Criterium", "Crit", "CCR", "RR", "OMNI"},
        "cx": {"Cyclocross", "CX"},
    }

    filtered = []
    for result in results:
        if result.event_date < cutoff_date:
            continue

        # 2) Must have a place (i.e., not None)
        if result.place is None:
            continue

        # 3) Discipline must match one of the allowed values
        discipline_val = result.event_details.get("discipline", "")
        valid_disciplines = discipline_map.get(discipline.lower(), set())
        if discipline_val not in valid_disciplines:
            continue

        filtered.append(result)

    return filtered