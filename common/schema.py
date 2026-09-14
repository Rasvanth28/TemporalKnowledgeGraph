from dataclasses import dataclass, field
import datetime

@dataclass
class Entity:
    id : str
    name : str
    type : str # "ORG" | "PERSON" | "LOCATION" | "POLICY"

@dataclass
class Article:
    id : str
    title : str
    date : datetime.date
    source : str
    url : str

@dataclass
class Event:
    id : str
    description : str
    date : datetime.date
    type : str

@dataclass
class Topic:
    name : str

@dataclass
class EventLink:
    from_event_id : str
    to_event_id : str
    confidence : float
    reason : str

@dataclass
class ExtractionResult:
    entities : list[Entity]
    event : Event
    topic : Topic
    eventlinks : list[EventLink] = field(default_factory=list)
