import spacy
from common.schema import Entity, Event, Topic,ExtractionResult,EventLink
import uuid
import dateutil.parser
import datetime

nlp = spacy.load("en_core_web_sm")

LABEL_MAP = {"ORG":"ORG","PERSON":"PERSON","GPE":"LOCATION","LOC":"LOCATION", "LAW":"POLICY"}
EVENT_TYPE_KEYWORDS = {"raise":"policy_change","rate":"policy_change"}
POLICY_KEYWORDS = {"encryption policy","access control","quantitative easing"}

def full_phrase(token):
    if (token is None):
        return None
    words = [child for child in token.children if child.dep_ == "compound"]
    words.append(token)
    words.sort(key=lambda word:word.i)
    text = " ".join(w.text for w in words)
    return text


def extract_event_description(text: str):
    doc = nlp(text)
    root = None
    subject = None
    obj = None
    for token in doc:
        if(token.dep_ == "ROOT"):
            root = token
            for child in root.children:
              if(child.dep_ == "nsubj"):
                subject = child
              if(child.dep_ == "dobj" or child.dep_ =="obj"):
                obj = child
    parts_found = sum(x is not None for x in (root,subject,obj))
    conf = (parts_found/3)*100
    parts = [str(p) for p in (full_phrase(subject),root,full_phrase(obj)) if p is not None]
    desc = " ".join(parts)
    return (desc,conf)


def get_id(text : str) -> str:
    namespace = uuid.NAMESPACE_DNS
    unique_id = uuid.uuid5(namespace,text)
    return str(unique_id)


def extract_entities(text: str) -> list[Entity]:
    doc = nlp(text)
    entities= []
    for ent in doc.ents:
        if ent.label_ in LABEL_MAP:
            ent_fed = get_id(ent.text+ent.label_)
            e = Entity(id=ent_fed,name=ent.text,type=LABEL_MAP[ent.label_])
            entities.append(e)
    policy_entities = extract_policy_entities(text)
    existing_names = {e.name.lower() for e in entities}
    for en in policy_entities:
        if en.name.lower() not in existing_names:
            entities.append(en)
    return entities


def extract_event_date(text:str,article_date: datetime.date)-> list[datetime.date]:
    doc = nlp(text)
    date = []
    for ent in doc.ents:
      if ent.label_ == "DATE":
        try:
            date.append(dateutil.parser.parse(ent.text,default=datetime.datetime(1,1,1)).date())
        except (dateutil.parser.ParserError,ValueError):
            pass
    if not date:
        return [article_date]
    else:
        return date


def pick_event_date(dates: list[datetime.date])->datetime.date:
    return dates[0]


def classify_event_type(text:str)->str:
   text_lower = text.lower()
   for keyword,category in EVENT_TYPE_KEYWORDS.items():
       if keyword in text_lower:
           return category
   return "general"

def extract_event(text: str, article_date: datetime.date) -> Event:

    (desc, conf) = extract_event_description(text)
    date = pick_event_date(extract_event_date(text, article_date))
    event_type = classify_event_type(text)
    id = get_id(desc + str(date))
    return Event(id=id, description=desc, date=date, type=event_type)


def extract_topic(text: str) -> Topic:
    doc = nlp(text)
    root = "general"
    for chunk in doc.noun_chunks:
        if (chunk.root.dep_ == "dobj" or chunk.root.dep_ == "obj"):
            root = chunk.text.lower()
    return Topic(name=root)

def extract_policy_entities(text:str) -> list[Entity]:
    entities = []
    for policy in POLICY_KEYWORDS:
        if policy in text.lower():
            policy_id = get_id(policy+"POLICY")
            entities.append(Entity(id=policy_id,name=policy,type="POLICY"))
    return entities 

def extract_all(text:str,article_date:datetime.date) -> ExtractionResult:
    entities = extract_entities(text)
    event = extract_event(text,article_date)
    topic = extract_topic(text)
    return ExtractionResult(entities=entities,event=event,topic=topic)

def get_jaccard_score(a : list[Entity] , b : list[Entity]) -> float:
    names_a = {e.name.lower() for e in a}
    names_b = {e.name.lower() for e in b}
    intersection = names_a & names_b
    union = names_a | names_b
    if not union:
        return 0.0
    return len(intersection)/len(union)


def get_topic_score(a : Topic , b : Topic) -> float:
    return 1.0 if a.name == b.name else 0.0

def get_date_score(a: datetime.date, b:datetime.date,window_days: int = 30) -> float:
    days_apart = abs((a-b).days)
    if days_apart >= window_days:
        return 0.0
    return 1.0 - (days_apart/window_days)

def get_confidence(jaccard_score:float,topic_score:float,date_score:float) -> float:
     return (jaccard_score+topic_score+date_score)/3

def get_reason(jaccard_score : float,topic_score: float, date_score :float) -> str:
    reasons = []
    if jaccard_score > 0:
        reasons.append("shared_entities")
    if topic_score > 0:
        reasons.append("same_topic")
    if date_score > 0.5:
        reasons.append("date_proximity")
    return "+".join(reasons) if reasons else "weak_link"

def compute_link(a : ExtractionResult,b:ExtractionResult) -> EventLink:
   from_event_id = a.event.id
   to_event_id = b.event.id
   jaccard_score = get_jaccard_score(a.entities,b.entities)
   topic_score = get_topic_score(a.topic,b.topic)
   date_score = get_date_score(a.event.date,b.event.date)
   confidence = get_confidence(jaccard_score,topic_score,date_score)
   reason = get_reason(jaccard_score,topic_score,date_score)
   return EventLink(from_event_id = from_event_id,to_event_id = to_event_id , confidence = confidence , reason = reason);


if __name__ == "__main__":
    pass
