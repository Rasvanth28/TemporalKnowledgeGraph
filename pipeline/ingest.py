import json
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from common.schema import Article


@dataclass
class RawArticle:
    # Text stays out of Article so the graph's Article nodes don't carry full bodies.
    article : Article
    text : str


class ArticleSource(Protocol):
    # Swap point: a live feed only has to implement load(); the pipeline doesn't change.
    def load(self) -> list[RawArticle]: ...


def _from_record(record: dict) -> RawArticle:
    article = Article(
        id=record["id"],
        title=record["title"],
        date=datetime.date.fromisoformat(record["date"]),
        source=record.get("source", ""),
        url=record.get("url", ""),
    )
    return RawArticle(article=article, text=record["text"])


def _to_record(raw: RawArticle) -> dict:
    a = raw.article
    return {"id":a.id,"title":a.title,"date":a.date.isoformat(),"source":a.source,"url":a.url,"text":raw.text}


class JsonFileSource:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[RawArticle]:
        with open(self.path, encoding="utf-8") as f:
            return [_from_record(r) for r in json.load(f)]


def save_articles_json(raws: list[RawArticle], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([_to_record(r) for r in raws], f, indent=2, ensure_ascii=False)
