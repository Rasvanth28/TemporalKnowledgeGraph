We used spaCy's pre-trained en_core_web_sm model for entity recognition and its dependency parser for event extraction, rather than training a custom NLP model. A custom model is not yet trained because of no labeled training data. SpaCy's model gives low accuracy on domain-specific language it wasn't trained on.

We have made reusable and swappable functions so that when we decide to change the model or architecture it will be easier. A fine-tuned NER model could later replace extract_entitie's internals without any caller needing to change.

We have used uuid5 to get the id because it is deterministic. When the same input is given it gives the same output. Which prevents duplicate nodes when we re-process the same article.

For now we have picked only the first DATE even though there are multiple dates in an article because we need to create more complex system if we take all dates. Our topic extraction sometimes includes the article 'the' on the topic name (e.g. 'the coast' instead of 'coast'), since spaCy's noun chunks include determiners.

There can be a optimized version by computing doc = nlp(text) and passing it as parameter.

We have used Jaccard method for overlapping of entities and topic and date score to find confidence and reason of the event link

