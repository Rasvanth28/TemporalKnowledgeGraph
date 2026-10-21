from graphdb.summary import MAX_ARTICLES, build_summary, headline_sentence


def event(i, article, relevance, evidence="Officials met to discuss the outlook."):
    return {"id": f"e:{i}", "kind": "event", "article_id": article, "relevance": relevance, "evidence": evidence}


def source(i, title, date):
    return {"id": i, "title": title, "date": date, "url": f"https://example.com/{i}", "publisher": "The Guardian"}


def test_headline_sentence():
    assert headline_sentence("Bank of England cuts interest rates to 5%") == "Bank of England cuts interest rates to 5%."
    assert headline_sentence("Bank of England holds rates | Letters") == "Bank of England holds rates."
    assert headline_sentence("Will the Bank of England cut interest rates this week?") is None
    assert headline_sentence("Rates: explained") is None


def test_summary_is_chronological_grouped_by_month_and_cited():
    nodes = [event(1, "aug", 3.0), event(2, "jun", 2.0), event(3, "jun2", 1.0)]
    sources = [source("aug", "Bank of England cuts interest rates to 5% in first reduction since 2020", "2024-08-01"),
               source("jun", "Bank of England keeps interest rates at 5.25% in finely balanced decision", "2024-06-20"),
               source("jun2", "Mortgage lenders trim fixed rates ahead of expected cut", "2024-06-28")]
    summary = build_summary(nodes, sources)
    assert [p["month"] for p in summary["paragraphs"]] == ["2024-06", "2024-08"]
    june = summary["paragraphs"][0]["sentences"]
    assert [s["article_id"] for s in june if not s["quote"]] == ["jun", "jun2"]
    assert all(s["article_id"] and s["event_node"] for p in summary["paragraphs"] for s in p["sentences"])
    assert (summary["start"], summary["end"], summary["articles_used"]) == ("2024-06-20", "2024-08-01", 3)


def test_question_headlines_are_replaced_by_the_key_sentence():
    nodes = [event(1, "q", 1.0, evidence="Inflation stayed at 2.2% in August, the ONS said.")]
    summary = build_summary(nodes, [source("q", "With inflation at 2.2%, will the Bank cut rates?", "2024-09-18")])
    (sentence,) = summary["paragraphs"][0]["sentences"]
    assert sentence["quote"] and sentence["text"].startswith("Inflation stayed at 2.2%")


def test_near_duplicate_stories_are_dropped_and_count_is_capped():
    nodes = [event(i, f"a{i}", 10 - i) for i in range(12)]
    topics = ["Bank cuts rates", "Opec trims output", "Pound slides against dollar", "Inflation eases in Britain",
              "Mortgage lenders reprice deals", "Retail sales disappoint analysts", "Steelworks announce closures",
              "Oil prices fall sharply", "Unemployment rises slightly", "Gilt yields climb again",
              "Budget raises taxes broadly", "Housebuilders report slowdown"]
    sources = [source(f"a{i}", f"{topics[i]} this week, officials confirm", f"2024-0{1 + i % 9}-01") for i in range(12)]
    sources[1]["title"], sources[1]["date"] = sources[0]["title"], "2024-01-02"  # same story, next day
    summary = build_summary(nodes, sources)
    used = [s["article_id"] for p in summary["paragraphs"] for s in p["sentences"] if not s["quote"]]
    assert "a1" not in used and summary["articles_used"] == MAX_ARTICLES


def test_strongest_stories_get_a_supporting_quote():
    nodes = [event(1, "big", 5.0, evidence="The MPC voted 5-4 to cut the base rate to 5%."), event(2, "small", 0.1)]
    sources = [source("big", "Bank of England cuts interest rates to 5% after close vote", "2024-08-01"),
               source("small", "Analysts react to the latest decision on rates", "2024-08-02")]
    sentences = build_summary(nodes, sources)["paragraphs"][0]["sentences"]
    assert [s["quote"] for s in sentences if s["article_id"] == "big"] == [False, True]


def test_similar_headlines_on_different_days_are_different_stories():
    nodes = [event(1, "jul", 2.0), event(2, "sep", 1.0)]
    sources = [source("jul", "Bank of England should keep interest rates on hold, says policymaker", "2024-07-08"),
               source("sep", "Interest rates on path down despite hold, Bank of England chief says", "2024-09-19")]
    assert build_summary(nodes, sources)["articles_used"] == 2


def test_articles_rank_by_their_best_event_not_their_length():
    nodes = [event(1, "key", 3.0)] + [event(i, "long", 0.5) for i in range(2, 9)]
    sources = [source("key", "Bank of England cuts interest rates to 5% in first cut", "2024-08-01"),
               source("long", "Long analysis piece about the wider economy this year", "2024-08-02")]
    sentences = build_summary(nodes, sources)["paragraphs"][0]["sentences"]
    # The single strong event outranks seven weak ones, so it gets the supporting quote first.
    assert sentences[0]["article_id"] == "key"
    from graphdb.summary import _article_score
    assert _article_score(nodes[:1]) > _article_score(nodes[1:])
