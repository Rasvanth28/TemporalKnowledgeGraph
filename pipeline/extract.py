import spacy
from common.schema import Entity
import uuid

nlp = spacy.load("en_core_web_sm")
LABEL_MAP = {"ORG":"ORG","PERSON":"PERSON","GPE":"LOCATION","LOC":"LOCATION"}


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
                if (child.dep_ == "nsubj"):
                    subject = child
                if (child.dep_ == "dobj" or child.dep_ == "obj"):
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

            
if __name__ == "__main__":
    pass 
