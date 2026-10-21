# RMI results: learned index vs Neo4j's B+ tree on the live graph

**Short answer:** the learned index is correct on every query and never needed its fallback, but it does
not beat Neo4j's B+ tree for this project. The bottleneck is not the index: a Neo4j lookup costs about
4 ms on the server and about 125 ms end to end, of which the index is a small part. Putting the RMI in
front of Neo4j makes queries slower, not faster. New data also makes the RMI's answers silently
incomplete until it is retrained (retraining takes 7 ms). As the research plan allowed, this is a
negative result, and it is reported as one.

Reproduce (read-only against the configured database):

```bash
python -m rmi.live --queries 300 --out rmi_live.json --export-csv data/exports/event_keys.csv
```

Run on 2026-10-21 against Neo4j Aura Free (the production graph), from an Apple M3 laptop running
Python 3.13 over the public internet. RMI configuration: 2 stages, `linear,linear`, 128 buckets (the
defaults).

## 1. The real keys are nothing like the synthetic ones

| | |
|---|---|
| Events with a date | 26,421 |
| Distinct days (the RMI's keys) | 561 |
| Range | 1802-01-01 … 2026-10-26 |
| Events dated 2026 | 23,354 (88%) |

The pipeline dates most events on the day they were reported, and dates a few by the history they
mention ("the 1926 general strike"). The result is a dense recent month plus a sparse tail of two
centuries. Many events share each date, but the RMI needs unique sorted keys. So it learns the
**distinct days**, and an offsets array maps each day to its run of events sorted by `(date, id)`
(`rmi/date_index.py`). This answers the same two questions the `event_date` B+ tree answers: the
events on a day, and the events in a date range.

The long tail breaks a linear stage 1. A straight line through 1802…2026 puts nearly every recent day in
the wrong bucket: the stage-1 error is **39 of 128 buckets**.

## 2. Correctness

300 queries: half single days, half ranges of 2–30 days. Start days were sampled per event, so busy
days come up as often as they do in real use. Each query returned between 0 and 14,231 events (median 796).

| Method | Same events as Neo4j | Fallbacks |
|---|---|---|
| RMI (`DateIndex`) | **300 / 300** | **0** |
| `bisect` over the same arrays | 300 / 300 | — |
| RMI picks the ids, Neo4j fetches them | 300 / 300 | — |

Range ends are usually days with no events, which the model never trained on. `RMIModel.lower_bound`
handles these. Both stage models are non-decreasing, so an unseen key falls at most one position outside
the training error, and the search window is widened by one. Each candidate is checked against its left
neighbour. A unit test checks every key in and around the trained range against `bisect`, with no
fallback.

## 3. Latency

| Path | Median | p95 |
|---|---|---|
| RMI lookup + slice of ids (in process) | 31.5 µs | 88 µs |
| `bisect` lookup + slice (in process) | 2.5 µs | 58 µs |
| Neo4j `event_date` index, **server time** | 4 ms | 50 ms |
| Neo4j `event_date` index, client round trip | 126 ms | 1.8 s |
| RMI → `WHERE e.id IN $ids`, server time | 8 ms | 104 ms |
| RMI → `WHERE e.id IN $ids`, client round trip | 146 ms | 2.3 s |

Neo4j's plan for the date query is `NodeIndexSeekByRange`, so the B+ tree is used. Its "server time" is
the database's own figure (`result_available_after + result_consumed_after`), and it includes
returning rows, not just the index seek.

How to read the table:

- **In process, the RMI loses to binary search by about 13×.** It compares fewer keys: about 2 window
  candidates against `bisect`'s about 9 (log₂ 561). But it pays for Python arithmetic per step and a
  stage-1 correction walk of up to 39 bucket boundaries. `bisect` is one call into C. At 561 keys,
  binary search finishes in a few cache-resident steps.
- **Neither in-process number matters to the application.** A Neo4j lookup costs 4 ms on the server and
  about 125 ms on the wire. Even a free index would save at most the server's index-seek share of the
  4 ms.
- **The RMI in front of Neo4j is slower (8 ms vs 4 ms server).** The RMI finds the ids instantly, but
  Neo4j then needs one unique-index lookup per id. The B+ tree range seek reads the same events as one
  contiguous scan. To help, a learned index would have to replace the B+ tree inside the database's
  storage engine, which a client library cannot do.

### Configuration sweep (in process, same query bounds)

| Stage models | Buckets | Stage-1 error (buckets) | Max stage-2 error | Candidates / lookup | Lower bound median |
|---|---|---|---|---|---|
| linear/linear | 4 | 1 | 41 | 53.4 | 6.1 µs |
| linear/linear | **16** | 4 | 6 | 3.1 | **2.9 µs** |
| linear/linear | 64 | 19 | 2 | 2.3 | 4.8 µs |
| linear/linear | 128 (default) | 39 | 2 | 2.2 | 6.9 µs |
| linear/linear | 256 | 79 | 1 | 1.5 | 11.5 µs |
| linear/constant | 16 | 4 | 18 | 17.1 | 3.3 µs |
| linear/constant | 128 | 39 | 2 | 2.5 | 6.2 µs |
| `bisect` | — | — | — | 9.1 (log₂ n) | 0.12 µs |

More buckets make stage 2 more accurate, but they also make stage 1's error larger in buckets, and on
this skewed data the walk costs more than the window saves. The best setting here is about 16 buckets,
not the default 128. Every configuration had zero fallbacks.

## 4. Update drift: what the daily ingest does to a trained index

We trained on everything published before 2026-10-14 (20,006 events), then added the 6,415 events
published since then. The daily job does the same thing every morning.

| New events touched… | Days |
|---|---|
| days after the trained range | 6 |
| days inside the range that had no events | 89 (older dates mentioned in new articles) |
| days that already had events | 180 |

| | Days answered completely | Days the model itself flagged |
|---|---|---|
| Before retrain | **0 / 275** | 95 |
| After one retrain (6.96 ms) | 275 / 275 | 0 |

The error bounds are guaranteed **only for the snapshot the model was trained on**. The model notices
keys it has never seen (95 days: out of range or not found) and falls back. But on 180 days it returns
an answer that looks fine and is missing new events. The model cannot detect this, because every
position after an insert has shifted. So "retrain weekly", as the design document suggested, is not
safe for a graph that changes daily. The index has to be rebuilt in the same transaction boundary as
each ingest, or invalidated by a version check. A rebuild is cheap (7 ms for 26k events), so if the RMI
were ever used, it should be rebuilt at the end of `run_ingest`.

## 5. Synthetic results (C2/C3), rerun after the routing fix

Live testing found that lookups searched every bucket in stage 1's error range (79 at 128 buckets on
the real keys). Lookups now walk to the one bucket that holds the key, which is the original RMI
design, and the error bound still guarantees correctness. Synthetic C2, 10,000 keys, 2,000 queries:

| Distribution | RMI median | Before the fix | `bisect` median | Correct / fallbacks |
|---|---|---|---|---|
| uniform | 2.4 µs | 4.4 µs | 0.2 µs | 2000 / 0 |
| clustered | 4.0 µs | 37.6 µs | 0.2 µs | 2000 / 0 |

The C3 drift results (0 → 500 / 500 correct after one retrain, about 4 ms) are unchanged. See
`contributions/person-c-rmi/RESULTS.md` for the original runs.

## 6. Conclusion

| Question | Answer |
|---|---|
| Can a two-stage RMI index the real event timeline correctly? | Yes: 300 / 300, zero fallbacks, and a proven lower-bound search for unseen keys. |
| Is it faster than Neo4j's B+ tree? | Not in any way the application can use. Network (about 120 ms) and query execution (about 4 ms) dominate, and the RMI-in-front design doubles server time. |
| Is it faster than binary search in process? | No, about 13× slower in Python at 561 keys, although it compares about 4× fewer keys. |
| Does it survive update drift? | Only with a rebuild per ingest. Staleness is silent on days that already existed. |

The RMI stays a research module. It is tested in CI, it is not on any request path, and the app keeps
using Neo4j's indexes. To revisit it, it would need:

1. far more keys (millions: per-event timestamps, not days), where binary search's log n grows;
2. a compiled implementation; and
3. a place inside the storage layer to run, rather than in front of the database.
