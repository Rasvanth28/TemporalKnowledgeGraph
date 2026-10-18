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
    date_source : str = "explicit" # "explicit" (stated in the text) | "inferred" (article's publication date)

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
class ExtractedEvent:
    # One event plus what it INVOLVES and is ABOUT.
    # source_text is the sentence the event came from (evidence + input for topic similarity).
    event : Event
    entities : list[Entity]
    topic : Topic
    source_text : str = ""

@dataclass
class ExtractionResult:
    # Article DESCRIBES events; Article MENTIONS entities (every entity found in the article).
    article : Article
    entities : list[Entity]
    events : list[ExtractedEvent] = field(default_factory=list)

@dataclass
class PipelineOutput:
    # EventLinks are corpus-level: they connect events across articles.
    results : list[ExtractionResult]
    links : list[EventLink] = field(default_factory=list)
