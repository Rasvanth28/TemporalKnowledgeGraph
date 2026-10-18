# Temporal Knowledge Graph

News articles → events, entities and topics → confidence-scored links between events → Neo4j (graph lane) and a learned index (RMI lane). See `PROJECT_PLAN.md` for the full plan.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # add GUARDIAN_API_KEY if you want to fetch live articles
pytest
```

## ML/NLP pipeline (Person A lane)

### Running it

```bash
# Optional: pull real articles from the Guardian (repeat --query to build several event chains).
# Quote phrases and use AND: unquoted words match ANY word, so "OPEC oil production" pulls in Fiat and Boeing.
python -m scripts.fetch_guardian --query '"Bank of England" AND "interest rates"' --query 'Opec AND "oil production"' \
    --section business --from-date 2024-01-01 --to-date 2024-12-31 --max-per-query 10

# ingest -> extract -> link -> export
python -m scripts.run_pipeline --input data/guardian_articles.json   # default input: data/sample_articles.json
```

The run writes two files to `data/exports/`:

| File | For | Contents |
|---|---|---|
| `pipeline_output.json` | Graph lane (writer) | Every `ExtractionResult` (article, entities it MENTIONS, events with the entities they INVOLVE and topic they're ABOUT) plus all `EventLink`s |
| `event_keys.csv` | RMI lane | `event_id, date_key, date, date_source, type, article_id`, sorted by `date_key` (days since 1970-01-01) |

### Modules

| Module | Responsibility |
|---|---|
| `common/schema.py` | Shared contract: `Article`, `Event`, `Entity`, `Topic`, `EventLink`, `ExtractedEvent`, `ExtractionResult`, `PipelineOutput` |
| `pipeline/ingest.py` | `ArticleSource` interface and `JsonFileSource` |
| `pipeline/guardian.py` | `GuardianSource`, which pulls from the Guardian Open Platform search API |
| `pipeline/extract.py` | `Extractor` interface and `SpacyExtractor` (NER, per-sentence events, dates, types, topics) |
| `pipeline/link.py` | `TopicScorer` interface, `TfidfTopicScorer`, confidence scoring, `link_events` |
| `pipeline/export.py` | JSON and CSV exports |
| `pipeline/config.py` | `ExtractConfig` / `LinkConfig`, overridable from `.env` |
| `pipeline/run.py` | `run_pipeline(source, extractor, link_config, scorer)` |

### Design notes

**Off-the-shelf model.** Entity recognition uses spaCy's pre-trained `en_core_web_sm`, and the dependency parse drives event extraction. No custom model is trained because there's no labelled data, and accuracy on domain-specific language is limited. Everything sits behind the `Extractor` interface, so a fine-tuned model can replace `SpacyExtractor` without any caller changing.

**Per-sentence events: clean up, rank, cap.** An article DESCRIBES several events. Each article is parsed once, and sentences are processed as spans of that parse.
- *Clean up.* For reporting verbs ("said", "told", "added"…) the event is the reported clause: "Bailey said the Bank would cut rates" → "Bank of England cut interest rates". A bare "she said." is not an event. Copula sentences ("X is Y") are dropped. Commentary with a pronoun subject and no named entity ("I think…") is dropped.
- *Qualify.* A sentence must still have an event verb with a subject and at least one anchor (a named entity or a date).
- *Rank and cap.* `salience = 3·headline overlap + explicit date + named entities + non-general type + 1/(1+position)`. The top `EXTRACT_MAX_EVENTS` (5) per article are kept, in article order. On 20 real Guardian articles this cut 322 noisy events to about 75.

**Deterministic IDs.** IDs are uuid5 values derived from content: entities from their normalized name plus type, events from article id + description + date. Re-processing the same article produces the same IDs, so `MERGE` in Neo4j doesn't create duplicates. Entity names are normalized ("The Federal Reserve" → "Federal Reserve") and deduped by name within an article, because spaCy sometimes tags the same name PERSON in one place and ORG in another.

**Dates.** Only DATE mentions that name a month or year are trusted, plus today, yesterday and tomorrow. Anything else ("Tuesday", "last quarter") falls back to the article's publication date. A mention without a day or month resolves to the start of its period, unless that period contains the publication date. For example, "March 2024" in an article published on 15 March 2024 means 15 March, not 1 March. The first date in a sentence becomes the event's date. `Event.date_source` records whether that date was `explicit` (stated in the sentence) or `inferred` (inherited from the article).

**Event types.** The keyword lemmas (`EVENT_TYPE_KEYWORDS`) are matched against the main verb first, then the heads of the subject and object, never side clauses.

**Linking.** `confidence = (0.5·entity_jaccard + 0.3·topic_cosine + 0.2·date_score) / sum(weights)`. The weights are configurable. Entities weigh most because date proximity alone would link unrelated news from the same week. Topic similarity is the TF-IDF cosine of "topic + source sentence", fitted once over the whole corpus. Links always point earlier → later, so they can become `PRECEDES`/`LINKED_TO` edges. Same-article pairs are skipped by default, links below `LINK_THRESHOLD` (0.3) are dropped, and each event keeps at most `LINK_TOP_K` (5) outgoing links. Date proximity alone never creates a link: a link also needs shared entities or a similar topic. When either date is inferred, the date score is multiplied by `LINK_INFERRED_DATE_FACTOR` (0.5), because otherwise every article from the same week would look related. The `reason` field lists which signals fired: `shared_entities`, `similar_topic`, `date_proximity`, or `weak_link`.

**Known limitations / backlog.**
- Year-only dates become 1 January. The schema has no date-precision field yet.
- Event descriptions are subject + verb + object only, so complements, negation and passives are lost ("policy committee voted" rather than "…voted 5–4 to cut rates to 5%").
- About half of the events are still typed `general`: the keyword lists are short.
- Linking compares every pair of events (O(n²)). That's fine for hundreds of events; block by date window or shared entity before scaling up.
- `TfidfTopicScorer` can be swapped for sentence embeddings behind the same `TopicScorer` interface.
- `data/sample_articles.json` (3 articles) contains no event chains, so the chains come from Guardian fetches. Fetched Guardian text is git-ignored because their terms don't allow republishing full article bodies.
