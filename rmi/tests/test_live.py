from rmi.config import RMIConfig
from rmi.live import EventKey, drift, iso, make_queries, sweep

KEYS = ([EventKey(f"old{i}", 100 + (i % 5) * 10, 104) for i in range(20)]
        + [EventKey("late-old-day", 110, 120), EventKey("new-day-inside", 105, 121),
           EventKey("new-day-after", 300, 121)])


def test_iso_is_the_inverse_of_date_key():
    assert iso(0) == "1970-01-01" and iso(-1) == "1969-12-31"


def test_queries_alternate_days_and_ranges_from_real_dates():
    queries = make_queries(KEYS, 10, seed=1)
    assert [kind for kind, _, _ in queries] == ["day", "range"] * 5
    days = {k.date_key for k in KEYS}
    assert all(start in days for _, start, _ in queries)
    assert all(start == end for kind, start, end in queries if kind == "day")
    assert all(start < end for kind, start, end in queries if kind == "range")


def test_drift_counts_silent_staleness_and_retrain_fixes_it():
    result = drift(KEYS, RMIConfig(bucket_count=2), cutoff=110)
    assert result["trained_events"] == 20 and result["new_events"] == 3
    assert result["existing_days_with_new_events"] == 1  # day 110 gained an event: answer silently incomplete
    assert result["new_days_after_old_range"] == 1 and result["new_days_inside_old_range"] == 1
    assert result["before_retrain"]["days_correct"] == 0
    assert result["before_retrain"]["days_flagged_by_model"] == 2  # the model only notices unseen days
    assert result["after_retrain"] == {"days_correct": 3, "days_incomplete": 0, "days_flagged_by_model": 0}


def test_sweep_reports_each_configuration_and_the_bisect_baseline():
    rows = sweep(KEYS, make_queries(KEYS, 6), repeats=1, bucket_counts=(1, 2), stage_models=(("linear", "linear"),))
    assert [r.get("bucket_count") for r in rows] == [1, 2, None]
    assert rows[-1]["stage_models"] == "bisect"
    assert all(r["fallbacks"] == 0 for r in rows[:-1])
