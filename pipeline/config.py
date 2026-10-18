import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LinkConfig:
    entity_weight : float = 0.5
    topic_weight : float = 0.3
    date_weight : float = 0.2
    threshold : float = 0.3        # links below this confidence are dropped
    top_k : int = 5                # max outgoing links kept per event
    date_window_days : int = 30    # date score reaches 0 at this distance
    link_within_article : bool = False
    inferred_date_factor : float = 0.5  # date score multiplier when either date was inherited from the article


@dataclass(frozen=True)
class ExtractConfig:
    spacy_model : str = "en_core_web_sm"
    # A sentence becomes an event only if it has a subject + verb and at least this many anchors
    # (a named entity or a DATE). Filters out filler sentences like "This is important."
    min_anchors : int = 1
    max_events_per_article : int = 5    # keep only the most salient sentences


def _env(name: str, default, cast):
    value = os.environ.get(name)
    return default if value is None or value == "" else cast(value)


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def load_link_config() -> LinkConfig:
    d = LinkConfig()
    return LinkConfig(
        entity_weight=_env("LINK_ENTITY_WEIGHT", d.entity_weight, float),
        topic_weight=_env("LINK_TOPIC_WEIGHT", d.topic_weight, float),
        date_weight=_env("LINK_DATE_WEIGHT", d.date_weight, float),
        threshold=_env("LINK_THRESHOLD", d.threshold, float),
        top_k=_env("LINK_TOP_K", d.top_k, int),
        date_window_days=_env("LINK_DATE_WINDOW_DAYS", d.date_window_days, int),
        link_within_article=_env("LINK_WITHIN_ARTICLE", d.link_within_article, _bool),
        inferred_date_factor=_env("LINK_INFERRED_DATE_FACTOR", d.inferred_date_factor, float),
    )


def load_extract_config() -> ExtractConfig:
    d = ExtractConfig()
    return ExtractConfig(
        spacy_model=_env("SPACY_MODEL", d.spacy_model, str),
        min_anchors=_env("EXTRACT_MIN_ANCHORS", d.min_anchors, int),
        max_events_per_article=_env("EXTRACT_MAX_EVENTS", d.max_events_per_article, int),
    )
