from pydantic import BaseModel, validator, HttpUrl, Extra, Field
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
        extra = Extra.allow

    @validator("event_date", pre=True)
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
            return datetime.strptime(value, "%m/%d/%Y").date()
        
        raise ValueError(f"Unsupported type for event_date: {type(value)}")

class AthleteResultHeat(BaseModel):
    place: int
    name: str
    category: Optional[str]
    usac_number: Optional[int]
    bib: Optional[str]
    team: Optional[str]

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
    bar: str