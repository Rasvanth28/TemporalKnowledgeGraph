from common.schema import PipelineOutput
from pipeline.config import LinkConfig
from pipeline.extract import Extractor, SpacyExtractor
from pipeline.ingest import ArticleSource
from pipeline.link import TopicScorer, link_events


def run_pipeline(source: ArticleSource, extractor: Extractor | None = None,
                 link_config: LinkConfig = LinkConfig(), scorer: TopicScorer | None = None) -> PipelineOutput:
    extractor = extractor or SpacyExtractor()
    results = [extractor.extract(raw.article, raw.text) for raw in source.load()]
    links = link_events(results, link_config, scorer)
    return PipelineOutput(results=results, links=links)
