# Temporal Knowledge Graph

News articles → events, entities and topics → confidence-scored links between events → Neo4j (graph lane) and a learned index (RMI lane). See `PROJECT_PLAN.md` for the full plan.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # add GUARDIAN_API_KEY if you want to fetch live articles
pytest
```

## Production

```
GitHub Actions (daily 06:17 UTC)                       Render (Docker web service)
  scripts.ingest: Guardian -> extract -> link  ---->  Neo4j Aura  <----  graphdb.api (X-API-Key)
                                       writes                     reads
```

| Piece | Where | Config |
|---|---|---|
| CI: ruff, all tests incl. live Neo4j integration (service container), Docker build + fail-closed check | `.github/workflows/ci.yml`, every PR and push to `main` | none |
| Ingestion: incremental, idempotent, one run at a time | `.github/workflows/ingest.yml` (daily + manual "Run workflow", optional dry run) | repo secrets `GUARDIAN_API_KEY`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`; queries in `config/ingest_queries.json` |
| Read API | `Dockerfile` + `render.yaml`, auto-deploys from `main` after CI passes | Render env: `NEO4J_*`, `API_KEYS` (generated), `API_CORS_ORIGINS` |
| Tests' database | local: `docker compose --profile test up -d neo4j-test`; CI: service container | `NEO4J_TEST_*` (never the real database) |

### Web UI ("Storyline")

The API serves a browser UI at `/` (`graphdb/static/`, plain HTML/CSS/JS, no build step). Type a question
("How did UK interest rates change in 2024?") and the matching part of the knowledge graph is drawn as an
interactive force-directed graph: events, people/organisations/places and topics, with event→event
"led to" links. Hover to highlight a node's neighbours; click for details (headline link, date, connections).
The panel also lists the graph's events in date order. Search URLs are shareable (`/?q=...`).

**How a prompt becomes a graph** (`graphdb/search.py`, endpoint `GET /graph?q=`), with no LLM and no external service:

1. **Names:** fuzzy-matched against entity names that exist in the graph (typos are OK; short acronyms like UK must be capitals).
2. **Dates:** "in 2024", "June 2024", "since March", "last 3 months", "between X and Y", "Q3 2024".
3. **Keywords:** what is left, matched with a Neo4j full-text index (English stemming).
4. **Meaning:** the prompt is embedded locally (model2vec `potion-base-8M`, about 30 MB, CPU) and matched against event
   embeddings in a Neo4j vector index, so "who drove UK borrowing costs?" finds rate decisions. Off-topic prompts
   return an empty graph instead of the nearest noise (thresholds calibrated in `graphdb/search.py`).

The results are merged with reciprocal-rank fusion and filtered by the date range. The UI shows what was understood
(names, dates, keywords) so results are explainable.

**What happened (summary).** Above the graph, a short chronological summary of the results, grouped into monthly
paragraphs, with every sentence cited [n] (`graphdb/summary.py`, returned as `summary` by `/graph`). It is *extractive*:
built only from the articles' own headlines and key sentences, so nothing is invented. The most relevant articles are
picked (best event first), the same story reported twice within two days is dropped, and question-style headlines are
replaced by the article's key sentence. Click a sentence to find it in the graph.

**Explanations and sources.** Every result explains itself and cites its source articles as numbered references [1], [2]…
with headline, publisher, date and link:
- *The story*: event count and span, the most connected names, and the strongest thread of linked events, each step with its reason.
- *Relationship panel* (click or hover any line): for event→event links, both source sentences quoted, the shared names and topic,
  the days apart, the link strength (names 50%, subject 30%, timing 20%), and a note that a link means "part of the same story",
  not proof of cause. For event→person/topic lines, the sentence that names them.
- *Event panel*: why it is in the results (asked-about name, matched keywords, similar meaning, date range) and the evidence quote.

Quotes are single sentences (max 280 characters) shown with attribution and a link to the original. Ingestion maintains the indexes and embeds new events
(`python -m graphdb.search_index` does the same by hand).

- Same origin as the API, so no CORS setup is needed. The graph library (force-graph, MIT) is vendored in `graphdb/static/vendor/`.
- On first visit it asks for an API key (one of `API_KEYS`), stored only in that browser's localStorage.
- Locally: `API_KEYS=dev .venv/bin/uvicorn graphdb.api:app --port 8000`, open http://localhost:8000 and enter `dev`.

### First deployment

1. **GitHub secrets:** repo → Settings → Secrets and variables → Actions → add `GUARDIAN_API_KEY`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (the Aura values; Aura's database name is the instance id from its credentials file, **not** `neo4j`).
2. **Render:** dashboard → New → Blueprint → select this repo → fill `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` (and `API_CORS_ORIGINS` if a browser app will call the API). Copy the generated `API_KEYS` value for clients.
3. **Check:** `curl https://<service>.onrender.com/health`, then `curl -H "X-API-Key: <key>" "https://<service>.onrender.com/events?start=2024-01-01&end=2024-12-31"`.
4. **First ingestion:** Actions → Ingest → Run workflow (tick *dry run* first to see the summary without writing).

### Runbook

| Situation | What to do |
|---|---|
| Ingest run failed | Open the run log (JSON lines; search `"level": "ERROR"`). Exit code 1 = configuration (missing secret, bad `config/ingest_queries.json`), 2 = run failure (Guardian/Neo4j). Re-running is safe: writes are idempotent and already-stored articles are skipped. |
| Log shows `guardian results capped` | A query had more results than `max_per_query`. Results are fetched oldest-first, so the next run continues; raise `max_per_query` to catch up faster. |
| Rotate an API key | Render env `API_KEYS=new,old` → deploy → move clients to `new` → remove `old`. |
| Rotate Neo4j password | Change it in Aura, then update Render env and the GitHub secret `NEO4J_PASSWORD`. |
| API returns 503 on `/health` / Render deploy never finishes | Read the `error` in the `/health` body. `DatabaseNotFound` means `NEO4J_DATABASE` is wrong (Aura uses the instance id). Otherwise Neo4j is unreachable: check the Aura console. Aura Free pauses idle instances; the daily ingestion keeps it active. |
| Extraction changed (e.g. a date fix) and stored events are out of date | `python -m scripts.reextract --input data/guardian_articles.json` (dry run: prints what would change), then add `--apply`. Articles not in `--input` are re-fetched from the Guardian by URL. Safe to re-run: a second run reports 0 changes. |
| Add a news topic | Add a query to `config/ingest_queries.json` via PR. New queries start from the newest article already in the graph. |

**Limits to know:** Render Free sleeps after 15 min idle (first request about 30s); GitHub disables scheduled workflows after 60 days without repository activity; Aura Free caps the graph size (200k nodes / 400k relationships at the time of writing).

## ML/NLP pipeline (Person A lane)

### Running it

```bash
# Optional: pull real articles from the Guardian (repeat --query to build several event chains).
# Quote phrases and use AND: unquoted words match ANY word, so "OPEC oil production" pulls in Fiat and Boeing.
python -m scripts.fetch_guardian --query '"Bank of England" AND "interest rates"' --query 'Opec AND "oil production"' \
    --section business --from-date 2024-01-01 --to-date 2024-12-31 --max-per-query 10

# Incremental: fetch new articles, link them to events already in Neo4j, write (what the scheduled job runs)
python -m scripts.ingest --dry-run          # drop --dry-run to write

# One-off batch: ingest -> extract -> link -> export, no database
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

**Event dates.** A sentence's date is only used if it says when *that* event happened. Skipped: reference points
("since 2008", "by 2027", "until the end of 2025", "from X to Y"), dates used as modifiers ("the 2008 crisis",
"July's election", "a February rate cut"), past years attached to a noun ("the Iraq war in 2003"), year-only mentions
not introduced by "in"/"during", and anything more than a week after the article (forecasts and targets).
A bare month means its nearest occurrence; "last month"/"last week" are resolved. Otherwise the event takes the
article's date (`date_source = inferred`). On the 15-article Guardian sample this moved 23 of 74 event dates,
all corrections (for example the August 2024 rate cut had been dated 2008).

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
