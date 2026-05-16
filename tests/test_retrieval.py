"""
Unit tests run without an API key.
Integration tests require ANTHROPIC_API_KEY in .env — run with:
    pytest tests/test_retrieval.py                         # unit only
    pytest tests/test_retrieval.py -m integration          # integration only
    pytest tests/test_retrieval.py -m "not integration"    # unit only (explicit)
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from app.retrieval.retriever import retrieve
from app.retrieval.generator import generate_answer, _extract_sources, _format_context
from app.retrieval.validator import validate_answer, _parse_json
from app.retrieval.pipeline import answer_question


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_chunks(*texts, filename="policy.pdf") -> list[dict]:
    return [
        {"text": t, "metadata": {"doc_id": "doc1", "filename": filename, "chunk_index": i}, "distance": 0.1}
        for i, t in enumerate(texts)
    ]


def _mock_client(response_text: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=response_text)]
    client = MagicMock()
    client.messages.create.return_value = mock_response
    return client


# ── Retriever unit tests ──────────────────────────────────────────────────────

def test_retrieve_delegates_to_store(store):
    store.add_document("doc1", ["Employees get 15 days vacation per year."], "pto.pdf")
    results = retrieve("How many vacation days?", store, n_results=3)
    assert isinstance(results, list)
    assert len(results) >= 1


def test_retrieve_empty_store_returns_empty(store):
    results = retrieve("vacation days", store)
    assert results == []


def test_retrieve_respects_n_results(store):
    chunks = [f"Policy chunk {i} about vacation leave entitlement." for i in range(10)]
    store.add_document("doc1", chunks, "pto.pdf")
    results = retrieve("vacation", store, n_results=3)
    assert len(results) <= 3


def test_retrieve_returns_expected_structure(store):
    store.add_document("doc1", ["Sick leave is 10 days per year."], "pto.pdf")
    results = retrieve("sick leave", store)
    assert "text" in results[0]
    assert "metadata" in results[0]
    assert "distance" in results[0]


# ── Generator unit tests ──────────────────────────────────────────────────────

def test_extract_sources_finds_citations():
    text = "You get 15 days PTO [Source: pto_vacation_policy.pdf]. Meals are capped at EUR 50 [Source: expense_reimbursement.docx]."
    sources = _extract_sources(text)
    assert "pto_vacation_policy.pdf" in sources
    assert "expense_reimbursement.docx" in sources


def test_extract_sources_deduplicates():
    text = "See [Source: pto.pdf] and also [Source: pto.pdf] again."
    assert _extract_sources(text) == ["pto.pdf"]


def test_extract_sources_returns_empty_when_none():
    assert _extract_sources("No citations here.") == []


def test_format_context_includes_filenames():
    chunks = _make_chunks("chunk text", filename="travel_policy.docx")
    context = _format_context(chunks)
    assert "travel_policy.docx" in context
    assert "chunk text" in context


def test_format_context_numbers_excerpts():
    chunks = _make_chunks("first chunk", "second chunk")
    context = _format_context(chunks)
    assert "Excerpt 1" in context
    assert "Excerpt 2" in context


def test_generate_answer_empty_chunks_returns_not_found():
    result = generate_answer("How many vacation days?", chunks=[])
    assert "could not find" in result["answer"].lower()
    assert result["sources"] == []


def test_generate_answer_calls_claude_with_question(store):
    chunks = _make_chunks("Employees get 15 days vacation per year.")
    client = _mock_client("You get 15 days PTO per year [Source: policy.pdf].")
    result = generate_answer("How many vacation days?", chunks, client=client)
    client.messages.create.assert_called_once()
    call_kwargs = client.messages.create.call_args
    user_message = call_kwargs[1]["messages"][0]["content"]
    assert "How many vacation days?" in user_message


def test_generate_answer_context_included_in_prompt():
    chunks = _make_chunks("Sick leave is 10 days per year.", filename="pto.pdf")
    client = _mock_client("Sick leave is 10 days [Source: pto.pdf].")
    generate_answer("How much sick leave?", chunks, client=client)
    call_kwargs = client.messages.create.call_args
    user_message = call_kwargs[1]["messages"][0]["content"]
    assert "Sick leave is 10 days" in user_message
    assert "pto.pdf" in user_message


def test_generate_answer_extracts_sources_from_response():
    chunks = _make_chunks("PTO policy content.")
    client = _mock_client("You get 15 days [Source: pto_vacation_policy.pdf].")
    result = generate_answer("vacation days?", chunks, client=client)
    assert "pto_vacation_policy.pdf" in result["sources"]


def test_generate_answer_uses_cache_control():
    chunks = _make_chunks("some policy text")
    client = _mock_client("Answer [Source: policy.pdf].")
    generate_answer("question?", chunks, client=client)
    call_kwargs = client.messages.create.call_args[1]
    system = call_kwargs["system"]
    assert any(block.get("cache_control") for block in system)


def test_generate_answer_result_structure():
    chunks = _make_chunks("policy text")
    client = _mock_client("Answer with no citation.")
    result = generate_answer("question?", chunks, client=client)
    assert "answer" in result
    assert "sources" in result
    assert isinstance(result["sources"], list)


# ── Validator unit tests ──────────────────────────────────────────────────────

def test_parse_json_clean():
    raw = '{"valid": true, "confidence": 0.9, "issues": [], "reasoning": "ok"}'
    result = _parse_json(raw)
    assert result["valid"] is True
    assert result["confidence"] == 0.9


def test_parse_json_strips_markdown_fences():
    raw = '```json\n{"valid": false, "confidence": 0.3, "issues": ["hallucination"], "reasoning": "bad"}\n```'
    result = _parse_json(raw)
    assert result["valid"] is False
    assert "hallucination" in result["issues"]


def test_validate_answer_returns_valid_structure():
    chunks = _make_chunks("Employees get 15 days PTO.")
    validator_json = '{"valid": true, "confidence": 0.95, "issues": [], "reasoning": "Grounded in context."}'
    client = _mock_client(validator_json)
    result = validate_answer("How many PTO days?", "You get 15 days.", chunks, client=client)
    assert "valid" in result
    assert "confidence" in result
    assert "issues" in result
    assert "reasoning" in result


def test_validate_answer_calls_claude_with_all_inputs():
    chunks = _make_chunks("PTO is 15 days.", filename="pto.pdf")
    client = _mock_client('{"valid": true, "confidence": 0.9, "issues": [], "reasoning": "fine"}')
    validate_answer("vacation days?", "You get 15 days [Source: pto.pdf].", chunks, client=client)
    call_kwargs = client.messages.create.call_args[1]
    user_content = call_kwargs["messages"][0]["content"]
    assert "vacation days?" in user_content
    assert "You get 15 days" in user_content
    assert "pto.pdf" in user_content


def test_validate_answer_handles_unparseable_response():
    chunks = _make_chunks("some policy text")
    client = _mock_client("This is not JSON at all.")
    result = validate_answer("question?", "answer", chunks, client=client)
    assert result["valid"] is False
    assert result["confidence"] == 0.0
    assert len(result["issues"]) > 0


def test_validate_answer_uses_cache_control():
    chunks = _make_chunks("policy text")
    client = _mock_client('{"valid": true, "confidence": 0.9, "issues": [], "reasoning": "ok"}')
    validate_answer("q?", "a", chunks, client=client)
    call_kwargs = client.messages.create.call_args[1]
    system = call_kwargs["system"]
    assert any(block.get("cache_control") for block in system)


# ── Pipeline unit tests ───────────────────────────────────────────────────────

def test_pipeline_result_has_all_keys(store):
    store.add_document("doc1", ["Employees get 15 days PTO per year."], "pto.pdf")
    gen_response = '{"answer": "15 days [Source: pto.pdf].", "sources": ["pto.pdf"]}'
    val_response = '{"valid": true, "confidence": 0.95, "issues": [], "reasoning": "ok"}'

    gen_client = _mock_client("15 days [Source: pto.pdf].")
    val_json = '{"valid": true, "confidence": 0.95, "issues": [], "reasoning": "Grounded."}'

    def side_effect(**kwargs):
        msg = kwargs["messages"][0]["content"]
        mock_resp = MagicMock()
        if "Employee question:" in msg:
            mock_resp.content = [MagicMock(text="15 days [Source: pto.pdf].")]
        else:
            mock_resp.content = [MagicMock(text=val_json)]
        return mock_resp

    client = MagicMock()
    client.messages.create.side_effect = side_effect

    result = answer_question("How many PTO days?", store, client=client)
    assert "question" in result
    assert "answer" in result
    assert "sources" in result
    assert "validation" in result
    assert "chunks_used" in result


def test_pipeline_chunks_used_matches_retrieved(store):
    store.add_document("doc1", ["Vacation is 15 days.", "Sick leave is 10 days."], "pto.pdf")

    val_json = '{"valid": true, "confidence": 0.9, "issues": [], "reasoning": "ok"}'

    def side_effect(**kwargs):
        msg = kwargs["messages"][0]["content"]
        mock_resp = MagicMock()
        if "Employee question:" in msg:
            mock_resp.content = [MagicMock(text="15 days [Source: pto.pdf].")]
        else:
            mock_resp.content = [MagicMock(text=val_json)]
        return mock_resp

    client = MagicMock()
    client.messages.create.side_effect = side_effect

    result = answer_question("vacation days?", store, n_results=2, client=client)
    assert result["chunks_used"] == 2


# ── Integration tests (require ANTHROPIC_API_KEY) ─────────────────────────────

@pytest.mark.integration
def test_pto_question_answered_correctly(indexed_store, api_client):
    result = answer_question("How many vacation days do employees get per year?", indexed_store, client=api_client)
    assert "15" in result["answer"]
    assert result["chunks_used"] > 0


@pytest.mark.integration
def test_expense_meal_limit_answered(indexed_store, api_client):
    result = answer_question("What is the daily meal allowance for domestic travel?", indexed_store, client=api_client)
    assert "50" in result["answer"]
    assert result["chunks_used"] > 0


@pytest.mark.integration
def test_remote_work_days_answered(indexed_store, api_client):
    result = answer_question("How many days per week can I work from home?", indexed_store, client=api_client)
    assert "3" in result["answer"]
    assert result["chunks_used"] > 0


@pytest.mark.integration
def test_parental_leave_weeks_answered(indexed_store, api_client):
    result = answer_question("How many weeks of paid leave does the primary caregiver receive?", indexed_store, client=api_client)
    assert "16" in result["answer"]
    assert result["chunks_used"] > 0


@pytest.mark.integration
def test_travel_flight_class_answered(indexed_store, api_client):
    result = answer_question("When am I allowed to fly business class?", indexed_store, client=api_client)
    answer_lower = result["answer"].lower()
    assert "6" in result["answer"] or "business" in answer_lower
    assert result["chunks_used"] > 0


@pytest.mark.integration
def test_password_policy_answered(indexed_store, api_client):
    result = answer_question("What are the password requirements?", indexed_store, client=api_client)
    assert "12" in result["answer"]
    assert result["chunks_used"] > 0


@pytest.mark.integration
def test_performance_review_rating_scale_answered(indexed_store, api_client):
    result = answer_question("What rating do I need to be eligible for a promotion?", indexed_store, client=api_client)
    assert "4" in result["answer"]
    assert result["chunks_used"] > 0


@pytest.mark.integration
def test_unknown_topic_returns_not_found(indexed_store, api_client):
    result = answer_question("What is the company's policy on pet insurance?", indexed_store, client=api_client)
    assert "could not find" in result["answer"].lower() or "not" in result["answer"].lower()


@pytest.mark.integration
def test_answer_includes_source_citations(indexed_store, api_client):
    result = answer_question("How many sick days do employees get?", indexed_store, client=api_client)
    assert len(result["sources"]) > 0


@pytest.mark.integration
def test_validator_approves_correct_answer(indexed_store, api_client):
    result = answer_question("How many vacation days per year?", indexed_store, client=api_client)
    assert result["validation"]["valid"] is True
    assert result["validation"]["confidence"] >= 0.7


@pytest.mark.integration
def test_validator_rejects_hallucinated_answer(indexed_store, api_client):
    chunks = _make_chunks(
        "Employees are entitled to 15 days of PTO per year.",
        filename="pto_vacation_policy.pdf",
    )
    hallucinated = "Employees receive 60 days of vacation per year and unlimited sick leave [Source: pto_vacation_policy.pdf]."
    result = validate_answer(
        "How many vacation days?",
        hallucinated,
        chunks,
        client=api_client,
    )
    assert result["valid"] is False


@pytest.mark.integration
def test_pipeline_end_to_end(indexed_store, api_client):
    result = answer_question(
        "What is the expense submission deadline?",
        indexed_store,
        n_results=5,
        client=api_client,
    )
    assert result["question"] == "What is the expense submission deadline?"
    assert len(result["answer"]) > 20
    assert isinstance(result["sources"], list)
    assert isinstance(result["validation"], dict)
    assert result["chunks_used"] > 0
    assert "valid" in result["validation"]
