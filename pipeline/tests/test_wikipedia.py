import datetime

from pipeline.wikipedia import clean, page_title, parse_day

DAY = datetime.date(2026, 10, 20)
# Written for this test in the portal's format (category headings, nested stories, cited leaves).
SAMPLE = """{{Current events|year=2026|month=10|day=20|top=yes}}
<!-- All news items below this line -->
'''Armed conflicts and attacks'''
*[[Example civil war (2023–present)|Example civil war]]
**[[Example border conflict]]
***The death toll in the market attack in [[Exampletown]] rises to 220. [https://news.example/a (''Example Post'')]
'''Business and economy'''
*[[Opec]] agrees to extend production cuts until the end of 2027, says the [[Ministry of Energy (Saudi Arabia)|Saudi energy ministry]]. [https://www.reuters.com/x (Reuters)] [https://apnews.com/y (AP)]
*Short heading only
"""


def test_page_title():
    assert page_title(DAY) == "2026_October_20"
    assert page_title(datetime.date(2024, 1, 5)) == "2024_January_5"


def test_clean_strips_markup_and_keeps_publishers():
    text, publishers = clean("The [[Sudanese Army|army]] repels an [[attack]] on '''[[Blue Nile]]'''. [https://x.example/1 (''Sudan Tribune'')]")
    assert text == "The army repels an attack on Blue Nile."
    assert publishers == ["Sudan Tribune"]


def test_parse_day_keeps_only_leaf_news_items():
    raws = parse_day(SAMPLE, DAY)
    assert [r.text for r in raws] == [
        "The death toll in the market attack in Exampletown rises to 220.",
        "Opec agrees to extend production cuts until the end of 2027, says the Saudi energy ministry.",
    ]
    second = raws[1].article
    assert second.date == DAY and second.url.endswith("Portal:Current_events/2026_October_20")
    assert second.source == "Wikipedia Current Events (CC BY-SA 4.0) · original: Reuters, AP"


def test_article_ids_are_stable_across_runs():
    assert [r.article.id for r in parse_day(SAMPLE, DAY)] == [r.article.id for r in parse_day(SAMPLE, DAY)]
