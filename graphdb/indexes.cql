CREATE INDEX event_date  IF NOT EXISTS FOR (e:Event)  ON (e.date);
CREATE INDEX event_type  IF NOT EXISTS FOR (e:Event)  ON (e.type);
CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name);
CREATE INDEX topic_name  IF NOT EXISTS FOR (t:Topic)  ON (t.name);
