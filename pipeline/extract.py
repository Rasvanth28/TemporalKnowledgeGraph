import spacy
from common.schema import Entity, Event, Topic
import uuid
import dateutil.parser
import datetime

nlp = spacy.load("en_core_web_sm")

LABEL_MAP = {"ORG":"ORG","PERSON":"PERSON","GPE":"LOCATION","LOC":"LOCATION"}
EVENT_TYPE_KEYWORDS = {"raise":"policy_change","rate":"policy_change"}


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
    return entities


def extract_event_date(text:str,article_date: datetime.date)-> list[datetime.date]:
    doc = nlp(text)
    date = []
    for ent in doc.ents:
      if ent.label_ == "DATE":
        date.append(dateutil.parser.parse(ent.text).date())
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

if __name__ == "__main__":
    pass
