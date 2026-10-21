"""C4: the RMI against Neo4j's B+ tree on the real graph. Read-only.

    python -m rmi.live [--queries 300] [--out results.json] [--export-csv keys.csv]

1. Export ``(event_id, date_key, published_key)`` for every dated event.
2. Build a ``DateIndex`` (RMI over the distinct days) from the export.
3. Run one query set (single days and date ranges, sampled like real use: busy days more often) through
   the RMI, an in-process ``bisect`` baseline, Neo4j's ``event_date`` range index, and the RMI in front of
   Neo4j (RMI finds the ids, Neo4j fetches them). Every answer is checked against Neo4j's.
4. Drift: train on events published before a cutoff, add the rest (what the daily ingest does), and
   measure answers before and after one retrain.

Neo4j times are reported twice: the client round trip and the server's own time from the result summary,
so the network does not hide what the index itself costs.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
import time
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from graphdb.connection import Neo4jClient
from graphdb.queries import date_key
from rmi.config import RMIConfig, load_rmi_config
from rmi.date_index import DateIndex

EXPORT = """
MATCH (e:Event) WHERE e.date IS NOT NULL
OPTIONAL MATCH (a:Article)-[:DESCRIBES]->(e)
RETURN e.id AS id, toString(e.date) AS date, toString(min(a.date)) AS published
ORDER BY date, id
"""
# graphdb.queries' date-range query without the entity/topic fan-out: what the B+ tree index answers.
IDS_IN_RANGE = """
MATCH (e:Event) WHERE e.date >= date($start) AND e.date <= date($end)
RETURN e.id AS id ORDER BY e.date, e.id
"""
IDS_BY_ID = "MATCH (e:Event) WHERE e.id IN $ids RETURN e.id AS id"
DAYS_BEFORE = "MATCH (e:Event) WHERE e.date < date($day) RETURN count(DISTINCT e.date) AS n"
EPOCH = dt.date(1970, 1, 1)


@dataclass(frozen=True)
class EventKey:
    event_id: str
    date_key: int
    published_key: int | None  # date of the article that reported it


def iso(key: int) -> str:
    return (EPOCH + dt.timedelta(days=int(key))).isoformat()


def export_event_keys(client: Neo4jClient) -> list[EventKey]:
    return [EventKey(row["id"], date_key(row["date"]), date_key(row["published"]) if row["published"] else None)
            for row in client.run(EXPORT)]


def write_keys_csv(keys: list[EventKey], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["event_id", "date_key", "date", "published_key"])
        writer.writerows((k.event_id, k.date_key, iso(k.date_key), k.published_key) for k in keys)


def neo4j_lower_bound(client: Neo4jClient) -> Callable[[np.ndarray], Callable[[int], int]]:
    """``DateIndex`` fallback answered by Neo4j: the number of distinct event days before ``key``."""

    def build(_days: np.ndarray) -> Callable[[int], int]:
        return lambda key: int(client.run(DAYS_BEFORE, {"day": iso(key)})[0]["n"])

    return build


def timed_query(client: Neo4jClient, query: str, params: dict) -> tuple[list[str], float, float]:
    """Rows, client round trip (ms) and server time (ms: planning/execution + streaming)."""

    with client.session() as session:
        start = time.perf_counter_ns()
        result = session.run(query, params)
        ids = [record["id"] for record in result]
        summary = result.consume()
        client_ms = (time.perf_counter_ns() - start) / 1e6
    return ids, client_ms, float((summary.result_available_after or 0) + (summary.result_consumed_after or 0))


def _median_ns(function: Callable[[], object], repeats: int) -> float:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        function()
        samples.append(time.perf_counter_ns() - start)
    return float(statistics.median(samples))


def _stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {"median": round(statistics.median(ordered), 3),
            "p95": round(ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))], 3),
            "mean": round(statistics.mean(ordered), 3)}


def make_queries(keys: list[EventKey], count: int, seed: int = 42, max_span: int = 30) -> list[tuple[str, int, int]]:
    """Half single days, half ranges of 2..max_span days; start days sampled per event, so busy days recur."""

    rng = np.random.default_rng(seed)
    starts = rng.choice(np.array([k.date_key for k in keys], dtype=np.int64), size=count)
    queries = []
    for i, start in enumerate(starts):
        if i % 2 == 0:
            queries.append(("day", int(start), int(start)))
        else:
            queries.append(("range", int(start), int(start) + int(rng.integers(1, max_span))))
    return queries


def benchmark(client: Neo4jClient, keys: list[EventKey], queries: list[tuple[str, int, int]],
              config: RMIConfig, repeats: int = 5, warmup: int = 10) -> dict:
    build_start = time.perf_counter()
    index = DateIndex.build(((k.date_key, k.event_id) for k in keys), config)
    build_ms = (time.perf_counter() - build_start) * 1e3

    sorted_keys = [k.date_key for k in sorted(keys, key=lambda k: (k.date_key, k.event_id))]
    ids = index.event_ids

    def bisect_between(start: int, end: int) -> list[str]:
        return ids[bisect_left(sorted_keys, start):bisect_right(sorted_keys, end)]

    for _, start, end in queries[:warmup]:  # connection pool, plan cache
        timed_query(client, IDS_IN_RANGE, {"start": iso(start), "end": iso(end)})

    rows = {"rmi_us": [], "bisect_us": [], "neo4j_client_ms": [], "neo4j_server_ms": [],
            "rmi_then_neo4j_client_ms": [], "rmi_then_neo4j_server_ms": []}
    correct = {"rmi": 0, "bisect": 0, "rmi_then_neo4j": 0}
    rows_returned = []
    for _, start, end in queries:
        truth, client_ms, server_ms = timed_query(client, IDS_IN_RANGE, {"start": iso(start), "end": iso(end)})
        truth_set = set(truth)
        rows_returned.append(len(truth))
        rows["neo4j_client_ms"].append(client_ms)
        rows["neo4j_server_ms"].append(server_ms)

        rmi_ids = index.between(start, end)
        correct["rmi"] += set(rmi_ids) == truth_set and len(rmi_ids) == len(truth)
        correct["bisect"] += set(bisect_between(start, end)) == truth_set
        rows["rmi_us"].append(_median_ns(lambda: index.between(start, end), repeats) / 1e3)
        rows["bisect_us"].append(_median_ns(lambda: bisect_between(start, end), repeats) / 1e3)

        fetched, hybrid_client, hybrid_server = timed_query(client, IDS_BY_ID, {"ids": rmi_ids})
        correct["rmi_then_neo4j"] += set(fetched) == truth_set
        rows["rmi_then_neo4j_client_ms"].append(hybrid_client)
        rows["rmi_then_neo4j_server_ms"].append(hybrid_server)

    plan = client.explain("EXPLAIN " + IDS_IN_RANGE, {"start": "2026-10-01", "end": "2026-10-07"})
    return {
        "index": index.summary() | {"build_ms": round(build_ms, 2)},
        "queries": len(queries),
        "rows_returned": _stats(rows_returned),
        "correct": correct,
        "rmi_fallbacks": index.fallbacks,
        "latency": {name: _stats(values) for name, values in rows.items()},
        "neo4j_operators": sorted(_operators(plan)),
    }


def _operators(plan: dict) -> set[str]:
    found = {str(plan.get("operatorType", "")).split("@")[0]} if plan else set()
    for child in plan.get("children", []) if plan else []:
        found |= _operators(child)
    return found - {""}


def sweep(keys: list[EventKey], queries: list[tuple[str, int, int]], repeats: int = 5,
          bucket_counts: tuple[int, ...] = (4, 16, 64, 128, 256),
          stage_models: tuple[tuple[str, str], ...] = (("linear", "linear"), ("linear", "constant"))) -> list[dict]:
    """In-process only: how the RMI's error and work depend on its configuration on the real days.

    ``candidates`` (keys compared per lower bound) is independent of the machine and of Python's overhead;
    ``bisect`` needs about log2(days) comparisons for the same answer.
    """

    bounds = [b for _, start, end in queries for b in (start, end + 1)]
    out = []
    for models in stage_models:
        for buckets in bucket_counts:
            config = RMIConfig(stage_models=models, bucket_count=buckets)
            index = DateIndex.build(((k.date_key, k.event_id) for k in keys), config)
            results = [index.model.lower_bound(b) for b in bounds]
            out.append({
                "stage_models": "/".join(models), "bucket_count": buckets,
                "stage1_error_buckets": index.model.stage1_error_buckets,
                "max_stage2_error": int(np.max(index.model.stage2_errors)),
                "candidates_mean": round(statistics.mean(r.candidates_checked for r in results), 1),
                "fallbacks": sum(r.used_fallback for r in results),
                "lower_bound_us_median": round(statistics.median(
                    _median_ns(lambda b=b: index.model.lower_bound(b), repeats) for b in bounds) / 1e3, 2),
            })
    days = sorted({k.date_key for k in keys})
    out.append({"stage_models": "bisect", "candidates_mean": round(float(np.log2(len(days))), 1),
                "lower_bound_us_median": round(statistics.median(
                    _median_ns(lambda b=b: bisect_left(days, b), repeats) for b in bounds) / 1e3, 2)})
    return out


def drift(keys: list[EventKey], config: RMIConfig, cutoff: int | None = None) -> dict:
    """Train on what was published before ``cutoff``, then add the rest, like the daily ingest does."""

    published = [k.published_key for k in keys if k.published_key is not None]
    cutoff = cutoff if cutoff is not None else max(published) - 7
    old = [k for k in keys if k.published_key is not None and k.published_key < cutoff]
    old_ids = {k.event_id for k in old}
    new = [k for k in keys if k.event_id not in old_ids]
    old_index = DateIndex.build(((k.date_key, k.event_id) for k in old), config)
    old_days = set(old_index.days.tolist())

    truth: dict[int, set[str]] = {}
    for k in keys:
        truth.setdefault(k.date_key, set()).add(k.event_id)
    queried = sorted({k.date_key for k in new})

    def score(index: DateIndex) -> dict[str, int]:
        right = stale = 0
        for day in queried:
            if set(index.on(day)) == truth[day]:
                right += 1
            else:
                stale += 1
        return {"days_correct": right, "days_incomplete": stale}

    before = score(old_index)
    flagged = sum(old_index.model.lookup(day).used_fallback for day in queried)
    start = time.perf_counter()
    new_index = DateIndex.build(((k.date_key, k.event_id) for k in keys), config)
    retrain_ms = (time.perf_counter() - start) * 1e3
    return {
        "cutoff": iso(cutoff),
        "trained_events": len(old), "new_events": len(new),
        "days_touched_by_new_events": len(queried),
        "new_days_after_old_range": sum(day > old_index.model.max_key for day in queried),
        "new_days_inside_old_range": sum(day <= old_index.model.max_key and day not in old_days for day in queried),
        "existing_days_with_new_events": sum(day in old_days for day in queried),
        "before_retrain": before | {"days_flagged_by_model": flagged},
        "retrain_ms": round(retrain_ms, 2),
        "after_retrain": score(new_index) | {"days_flagged_by_model": sum(
            new_index.model.lookup(day).used_fallback for day in queried)},
    }


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    from graphdb.config import load_neo4j_config

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--queries", type=int, default=300)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", help="write the results JSON here")
    parser.add_argument("--export-csv", help="also write the exported event keys here")
    args = parser.parse_args(argv)
    load_dotenv()
    config = load_rmi_config()

    with Neo4jClient(load_neo4j_config()) as client:
        keys = export_event_keys(client)
        queries = make_queries(keys, args.queries, args.seed)
        if args.export_csv:
            write_keys_csv(keys, args.export_csv)
        result = {
            "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "config": asdict(config),
            "benchmark": benchmark(client, keys, queries, config, args.repeats),
            "config_sweep": sweep(keys, queries, args.repeats),
            "drift": drift(keys, config),
        }
    text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
