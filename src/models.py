from pydantic import BaseModel, validator, HttpUrl, Extra, Field
from typing import Optional, Dict, Any
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
    
class RaceResult(BaseModel): 
    foo: str

class AthleteResultDetailed(AthleteResult): 
    bar: str