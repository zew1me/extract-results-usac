from pydantic import BaseModel, field_validator, HttpUrl, Extra, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime

class AthleteResult(BaseModel):
    event_date:  date
    event_title: str
    event_details: Dict[str, Any] = Field(default_factory=dict)
    event_url: HttpUrl
    place: Optional[int]
    participant_count: int
    points: Optional[float]
    name: str
    time: Optional[str]

    class Config:
        extra = 'allow'

    @field_validator("event_date", mode="before")
    def parse_event_date(cls, value):
        """
        Accept a string (MM/DD/YYYY), a date, or a datetime. 
        Convert any of them into a date object.
        """
        if value is None:
            return None

        if isinstance(value, date):
            return value

        if isinstance(value, datetime):
            return value.date()
        
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%m/%d/%Y").date()
            except ValueError:
                return datetime.fromisoformat(value).date()

        raise ValueError(f"Unsupported type for event_date: {type(value)}")

class AthleteResultHeat(BaseModel):
    place: int
    name: str
    category: Optional[str]
    usac_number: Optional[int]
    bib: Optional[str]
    team: Optional[str]

    class Config:
        extra = 'allow'

class Heat(BaseModel):
    """
    A 'heat' or sub-event, e.g. "RR Men CAT 1/2/3" with an ID like "1525491".
    Contains a list of participant rows.
    """
    heat_id: str
    heat_name: str
    participants: List[AthleteResultHeat] = []

class RaceEvent(BaseModel): 
    """
    The event/race container.
    """
    event_name: str
    id: str
    event_date: date
    race_label: Optional[str] = None
    heats: List[Heat] = []    

class RaceSeries(BaseModel): 
    """
    The top-level container for multiple RaceEvents, each of which may have
    multiple heats. Has a series name and a permit ID.
    """
    series_name: str
    permit_id: str
    events: List[RaceEvent] = []    

class AthleteResultDetailed(AthleteResult):
    # Fields from AthleteResultHeat
    category: Optional[str]
    usac_number: Optional[int]
    bib: Optional[str]
    team: Optional[str]
    # Fields from Heat (excluding participants)
    heat_id: str
    heat_name: str
    # Fields from RaceEvent (excluding heats)
    race_event_id: str
    race_event_race_label: Optional[str] = None
    # Fields from RaceSeries (excluding events)
    series_name: str
    permit_id: str
    # Additional category-specific fields
    participants_in_cat: int
    place_in_cat: int

    @classmethod
    def from_components(
        cls,
        result: AthleteResult,
        heat_result: AthleteResultHeat,
        heat: "Heat",
        event: "RaceEvent",
        series: "RaceSeries",
        participants_in_cat: Optional[int],
        place_in_cat: Optional[int]
    ) -> "AthleteResultDetailed":
        """
        Constructs an AthleteResultDetailed object from the given component objects.
        Parameters:
            result (AthleteResult): The primary athlete result containing overall performance data.
            heat_result (AthleteResultHeat): The athlete result specific to a heat. Must have the same 'name'
                as the primary result. Provides additional attributes like category, usac_number, bib, and team.
            heat (Heat): The heat information, providing details such as heat_id and heat_name.
            event (RaceEvent): The event information, from which the race_event_id and race_event_race_label are derived.
            series (RaceSeries): The series information, contributing attributes like series_name and permit_id.
            participants_in_cat (int): The total number of participants in the athlete's category.
            place_in_cat (int): The athlete's placement within their category.
        Returns:
            AthleteResultDetailed: A new instance constructed by merging fields from the provided components.
        Raises:
            ValueError: If there is a mismatch between the names in result and heat_result.
        """

        if result.name != heat_result.name:
            raise ValueError("Mismatch between AthleteResult.name and AthleteResultHeat.name")
        
        # Start with AthleteResult's fields
        data = result.dict()
        # Add AthleteResultHeat fields
        data.update({
            "category": heat_result.category,
            "usac_number": heat_result.usac_number,
            "bib": heat_result.bib,
            "team": heat_result.team,
        })
        # Add Heat fields (excluding participants)
        data.update({
            "heat_id": heat.heat_id,
            "heat_name": heat.heat_name,
        })
        # Add RaceEvent fields (excluding heats)
        data.update({
            "race_event_id": event.id,
            "race_event_race_label": event.race_label,
        })
        # Add RaceSeries fields (excluding events)
        data.update({
            "series_name": series.series_name,
            "permit_id": series.permit_id,
        })
        # Add additional fields
        data.update({
            "participants_in_cat": participants_in_cat,
            "place_in_cat": place_in_cat,
        })
        return cls(**data)