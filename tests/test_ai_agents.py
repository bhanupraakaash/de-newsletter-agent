import json
from datetime import datetime, timezone

import pytest

from src.agents import ArticleClassifier, ArticleSummarizer, fallback_select
from src.agents.classifier import parse_classifications
from src.agents.json_utils import extract_json_objects
from src.agents.summarizer import fallback_summary, parse_summaries
from src.models import Article
from src.services import LLMError, LLMResponse


class ScriptedLLM:
    """Returns queued texts in order; records prompts. Never touches the network."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.prompts = []

    def generate(self, system, user, max_tokens=None, purpose=""):
        self.prompts.append(user)
        if not self.texts:
            raise LLMError("no more scripted responses")
        return LLMResponse(text=self.texts.pop(0), model="claude-haiku-5-5", input_tokens=10, output_tokens=5)


def art(i, py_score=5.0, **kw) -> Article:
    return Article(id=f"a{i}", title=f"Article {i}", source="S", url=f"https://ex.com/{i}",
                   published_date=datetime(2026, 10, 25, tzinfo=timezone.utc),
                   description="desc " * 10, relevance_score=py_score, **kw)


def cls(i, score=8, rec=True, cat="Databricks & Spark", tutorial=False, tech=("Spark",)):
    return {"id": i, "category": cat, "relevance_score": score, "technologies": list(tech),
            "recommended": rec, "is_tutorial": tutorial}


# --- JSON extraction ---------------------------------------------------------

def test_extract_plain_fenced_and_chatty():
    arr = '[{"id": 1}, {"id": 2}]'
    assert extract_json_objects(arr) == [{"id": 1}, {"id": 2}]
    assert extract_json_objects(f"```json\n{arr}\n```") == [{"id": 1}, {"id": 2}]
    assert extract_json_objects(f"Sure! Here you go:\n{arr}\nHope that helps") == [{"id": 1}, {"id": 2}]


def test_extract_salvages_truncated_output():
    assert extract_json_objects('[{"id": 1}, {"id": 2}, {"id": 3, "summ') == [{"id": 1}, {"id": 2}]


def test_extract_handles_garbage():
    assert extract_json_objects("no json here") == []
    assert extract_json_objects("[]") == []


# --- classifier --------------------------------------------------------------

def test_parse_drops_invalid_items():
    text = json.dumps([
        cls(1), cls(2, score=11), cls(3, cat="Cooking"), {"id": 4}, cls(99), cls(1, score=3),
    ])
    parsed = parse_classifications(text, valid_ids={1, 2, 3, 4})
    assert list(parsed) == [1]
    assert parsed[1].relevance_score == 8  # first occurrence wins


def test_selection_prefers_recommended_then_score_then_python_score():
    cands = [art(1, 5), art(2, 5), art(3, 9), art(4, 5)]
    llm = ScriptedLLM(json.dumps([cls(1, 7), cls(2, 9), cls(3, 7), cls(4, 10, rec=False)]))
    out = ArticleClassifier(llm, max_selected=2, min_selected=2).classify_and_select(cands)
    assert [a.id for a in out] == ["a2", "a3"]  # 9 first, then 7 with higher python score
    assert out[0].relevance_score == 9 and out[0].category == "Databricks & Spark" and out[0].processed


def test_selection_pads_with_solid_unrecommended_only():
    cands = [art(1), art(2), art(3)]
    llm = ScriptedLLM(json.dumps([cls(1, 9), cls(2, 6, rec=False), cls(3, 3, rec=False)]))
    out = ArticleClassifier(llm, max_selected=5, min_selected=3).classify_and_select(cands)
    assert [a.id for a in out] == ["a1", "a2"]  # a3 scored below 5, never padded in


def test_selection_never_exceeds_max():
    cands = [art(i) for i in range(1, 6)]
    llm = ScriptedLLM(json.dumps([cls(i, 8) for i in range(1, 6)]))
    assert len(ArticleClassifier(llm, max_selected=3).classify_and_select(cands)) == 3


def test_classifier_retries_once_then_succeeds():
    llm = ScriptedLLM("sorry, I cannot", json.dumps([cls(1)]))
    out = ArticleClassifier(llm, max_selected=1, min_selected=1).classify_and_select([art(1)])
    assert len(out) == 1 and len(llm.prompts) == 2


def test_classifier_raises_after_two_bad_answers():
    llm = ScriptedLLM("nope", "still nope")
    with pytest.raises(LLMError):
        ArticleClassifier(llm).classify_and_select([art(1)])
    assert len(llm.prompts) == 2  # exactly one retry, to cap spend


def test_prompt_contains_only_compact_fields():
    llm = ScriptedLLM(json.dumps([cls(1)]))
    ArticleClassifier(llm, description_chars=20).classify_and_select([art(1)])
    prompt = llm.prompts[0]
    assert "[1] Article 1 | S |" in prompt and "ex.com" not in prompt  # no URLs sent


def test_fallback_select_infers_category_and_limits():
    a = art(1, matched_keywords=["azure", "sql"])
    b = art(2, matched_keywords=["spark"])
    out = fallback_select([a, b, art(3)], limit=2)
    assert [x.id for x in out] == ["a1", "a2"]
    assert out[0].category == "Azure Data Engineering" and out[1].category == "Databricks & Spark"
    assert out[1].technologies == ["Spark"]


# --- summarizer --------------------------------------------------------------

def test_summarizer_applies_valid_and_falls_back_for_missing():
    arts = [art(1), art(2)]
    llm = ScriptedLLM(json.dumps([{"id": 1, "summary": "  Great   news. ", "why_it_matters": "Because."}]))
    out = ArticleSummarizer(llm).summarize(arts)
    assert out[0].summary == "Great news." and out[0].why_it_matters == "Because."
    assert out[1].summary == fallback_summary(arts[1]) and out[1].why_it_matters == ""


def test_summarizer_never_raises_when_llm_fails():
    out = ArticleSummarizer(ScriptedLLM("junk", "junk")).summarize([art(1)])
    assert out[0].summary  # fallback text present


def test_summarizer_without_llm_uses_fallback():
    out = ArticleSummarizer(None).summarize([art(1)])
    assert out[0].summary and out[0].why_it_matters == ""


def test_summary_lengths_are_capped_and_empty_rejected():
    parsed = parse_summaries(json.dumps([
        {"id": 1, "summary": "word " * 200, "why_it_matters": "why " * 200},
        {"id": 2, "summary": "   ", "why_it_matters": "x"},
    ]), valid_ids={1, 2})
    assert list(parsed) == [1]
    assert len(parsed[1].summary) <= 401 and len(parsed[1].why_it_matters) <= 281
