import pytest
from pathlib import Path
from app.indexer.parser import parse_pdf, parse_docx, parse_document
from app.indexer.chunker import chunk_text
from app.indexer.store import PolicyStore
from app.indexer.pipeline import index_document, remove_document


# --- Parser tests ---

def test_parse_pdf_returns_text(sample_pdf):
    text = parse_pdf(sample_pdf)
    assert isinstance(text, str)
    assert "vacation" in text.lower()


def test_parse_docx_returns_text(sample_docx):
    text = parse_docx(sample_docx)
    assert isinstance(text, str)
    assert "vacation" in text.lower()


def test_parse_document_pdf(sample_pdf):
    result = parse_document(sample_pdf)
    assert result["filename"] == "test_policy.pdf"
    assert "vacation" in result["text"].lower()


def test_parse_document_docx(sample_docx):
    result = parse_document(sample_docx)
    assert result["filename"] == "test_policy.docx"
    assert "vacation" in result["text"].lower()


def test_parse_document_unsupported_extension(tmp_path):
    bad_file = tmp_path / "notes.txt"
    bad_file.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_document(bad_file)


# --- Chunker tests ---

def test_chunk_text_produces_multiple_chunks():
    words = ["word"] * 1200
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) > 1


def test_chunk_text_each_chunk_not_exceeds_size():
    words = ["word"] * 1200
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    for chunk in chunks:
        assert len(chunk.split()) <= 500


def test_chunk_text_overlap_is_present():
    words = [f"w{i}" for i in range(600)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) == 2
    first_end_words = set(chunks[0].split()[-50:])
    second_start_words = set(chunks[1].split()[:50])
    assert first_end_words == second_start_words


def test_chunk_text_short_text_single_chunk():
    text = "This is a short text with only a few words."
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


# --- Store tests ---

def test_store_add_and_count(store):
    store.add_document("doc1", ["chunk one about vacation", "chunk two about sick leave"], "policy.pdf")
    assert store.count() == 2


def test_store_query_returns_relevant_result(store):
    store.add_document("doc1", [
        "Employees are entitled to 15 days of paid vacation per year.",
        "The expense reimbursement limit for meals is 50 EUR per day.",
    ], "policy.pdf")
    results = store.query("How many vacation days do employees get?", n_results=2)
    assert len(results) > 0
    assert any("vacation" in r["text"].lower() for r in results)


def test_store_query_empty_collection_returns_empty(store):
    results = store.query("vacation days")
    assert results == []


def test_store_delete_document(store):
    store.add_document("doc1", ["chunk about vacation policy"], "policy.pdf")
    assert store.count() == 1
    store.delete_document("doc1")
    assert store.count() == 0


def test_store_delete_nonexistent_document_does_not_raise(store):
    store.delete_document("does_not_exist")


def test_store_update_document(store):
    store.add_document("doc1", ["original content about vacation"], "policy.pdf")
    store.update_document("doc1", ["updated content about parental leave"], "policy.pdf")
    results = store.query("parental leave", n_results=1)
    assert "parental leave" in results[0]["text"].lower()


def test_store_results_include_metadata(store):
    store.add_document("doc1", ["vacation policy chunk"], "vacation.pdf")
    results = store.query("vacation", n_results=1)
    assert results[0]["metadata"]["doc_id"] == "doc1"
    assert results[0]["metadata"]["filename"] == "vacation.pdf"
    assert "distance" in results[0]


# --- Pipeline tests ---

def test_index_document_pdf(sample_pdf, store):
    result = index_document(sample_pdf, doc_id="test_pto", store=store)
    assert result["doc_id"] == "test_pto"
    assert result["filename"] == "test_policy.pdf"
    assert result["chunks"] > 0
    assert store.count() == result["chunks"]


def test_index_document_docx(sample_docx, store):
    result = index_document(sample_docx, doc_id="test_conduct", store=store)
    assert result["chunks"] > 0


def test_index_document_uses_stem_as_default_doc_id(sample_pdf, store):
    result = index_document(sample_pdf, store=store)
    assert result["doc_id"] == "test_policy"


def test_remove_document(sample_pdf, store):
    index_document(sample_pdf, doc_id="test_pto", store=store)
    assert store.count() > 0
    remove_document("test_pto", store=store)
    assert store.count() == 0
