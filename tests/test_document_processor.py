"""Tests for document_processor: fingerprinting, chunking, multi-format loading."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.document_processor import (
    FINGERPRINT_STORE,
    apply_chunking,
    file_hash,
    get_fingerprint_registry,
    is_already_indexed,
    is_semantically_duplicate,
    load_file_as_documents,
    redact_pii,
    register_indexed,
)
# ── Fingerprinting ────────────────────────────────────────────────────────────


def test_file_hash_returns_sha256(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    h = file_hash(str(f))
    assert len(h) == 64  # SHA-256 hex digest
    assert h == file_hash(str(f))  # deterministic


def test_file_hash_different_content(tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("content A")
    f2.write_text("content B")
    assert file_hash(str(f1)) != file_hash(str(f2))


def test_is_already_indexed_false_for_new_file(tmp_path, monkeypatch):
    import src.document_processor as dp
    f = tmp_path / "new.txt"
    f.write_text("brand new content")
    monkeypatch.setattr(dp, "FINGERPRINT_STORE", tmp_path / "fingerprints.json")
    assert is_already_indexed(str(f)) is False


def test_register_and_check_indexed(tmp_path, monkeypatch):
    import src.document_processor as dp
    f = tmp_path / "doc.txt"
    f.write_text("some supply chain content")
    fp_path = tmp_path / "fingerprints.json"
    monkeypatch.setattr(dp, "FINGERPRINT_STORE", fp_path)

    assert is_already_indexed(str(f)) is False
    register_indexed(str(f), chunk_count=5)
    assert is_already_indexed(str(f)) is True

    # Verify fingerprint file contents
    registry = json.loads(fp_path.read_text())
    h = file_hash(str(f))
    assert h in registry
    assert registry[h]["chunk_count"] == 5
    assert "indexed_at" in registry[h]


def test_register_updates_existing(tmp_path, monkeypatch):
    import src.document_processor as dp
    f = tmp_path / "doc.txt"
    f.write_text("content")
    monkeypatch.setattr(dp, "FINGERPRINT_STORE", tmp_path / "fingerprints.json")

    register_indexed(str(f), chunk_count=3)
    f.write_text("updated content")  # changes hash
    assert is_already_indexed(str(f)) is False  # new hash not registered


# ── File Loading ───────────────────────────────────────────────────────────────


def test_load_txt_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("This is a supply chain document with some content.")
    # SimpleDirectoryReader requires llama-index-readers-file; skip if absent
    pytest.importorskip("llama_index.readers", reason="llama-index-readers-file not installed")
    docs = load_file_as_documents(str(f), metadata={"doc_type": "policy"})
    assert len(docs) >= 1
    assert any("supply chain" in d.get_content() for d in docs)
    assert all(d.metadata.get("doc_type") == "policy" for d in docs)


def test_load_csv_file(tmp_path):
    f = tmp_path / "suppliers.csv"
    f.write_text(
        "supplier_id,name,country,lead_time_days\n"
        "SUP-001,Acme Corp,USA,14\n"
        "SUP-002,Beta Ltd,UK,21\n"
        "SUP-003,Gamma GmbH,Germany,10\n"
    )
    docs = load_file_as_documents(str(f), metadata={"doc_type": "supplier_info"})
    assert len(docs) >= 1
    # CSV rows should be merged into batches
    combined = " ".join(d.get_content() for d in docs)
    assert "Acme Corp" in combined
    assert "Beta Ltd" in combined


def test_load_markdown_file(tmp_path):
    f = tmp_path / "policy.md"
    f.write_text("# Safety Stock Policy\n\nSafety stock = Z × σ × √(L)")
    pytest.importorskip("llama_index.readers", reason="llama-index-readers-file not installed")
    docs = load_file_as_documents(str(f), metadata={})
    assert len(docs) >= 1


def test_load_unsupported_extension_falls_back(tmp_path):
    f = tmp_path / "report.log"
    f.write_text("Plain log file content here.")
    pytest.importorskip("llama_index.readers", reason="llama-index-readers-file not installed")
    # Should fall back to SimpleDirectoryReader and not raise
    docs = load_file_as_documents(str(f), metadata={})
    assert isinstance(docs, list)


# ── Chunking ──────────────────────────────────────────────────────────────────


def test_apply_chunking_sentence_strategy(tmp_path):
    """Sentence splitter should produce multiple nodes from a long document."""
    from llama_index.core import Document as LIDocument
    docs = [LIDocument(text="This is sentence one. " * 40 + "This is sentence two. " * 40)]
    nodes = apply_chunking(docs, chunk_size=512, chunk_overlap=64, strategy="sentence")
    assert len(nodes) >= 1
    for node in nodes:
        assert hasattr(node, "get_content")


def test_apply_chunking_fixed_strategy(tmp_path):
    from llama_index.core import Document as LIDocument
    docs = [LIDocument(text="Fixed chunking test document. " * 20)]
    nodes = apply_chunking(docs, chunk_size=256, chunk_overlap=32, strategy="fixed")
    assert len(nodes) >= 1


def test_apply_chunking_unknown_strategy_falls_back(tmp_path):
    from llama_index.core import Document as LIDocument
    docs = [LIDocument(text="Unknown strategy fallback test. " * 10)]
    # "nonexistent" strategy should fall back gracefully to sentence splitter
    nodes = apply_chunking(docs, chunk_size=512, chunk_overlap=64, strategy="nonexistent")
    assert len(nodes) >= 1


def test_apply_chunking_semantic_without_embed_falls_back(tmp_path):
    from llama_index.core import Document as LIDocument
    docs = [LIDocument(text="Semantic chunking needs an embed model. " * 10)]
    # semantic without embed_model → should fall back to sentence
    nodes = apply_chunking(
        docs, chunk_size=512, chunk_overlap=64, strategy="semantic", embed_model=None
    )
    assert len(nodes) >= 1


# ── get_fingerprint_registry ──────────────────────────────────────────────────


def test_get_fingerprint_registry_empty_when_no_file(tmp_path, monkeypatch):
    import src.document_processor as dp
    monkeypatch.setattr(dp, "FINGERPRINT_STORE", tmp_path / "missing.json")
    registry = get_fingerprint_registry()
    assert registry == {}


def test_redact_pii_masks_sensitive_patterns():
    redacted = redact_pii("Email john@acme.com phone 555-123-4567 ssn 123-45-6789")
    assert "john@acme.com" not in redacted
    assert "555-123-4567" not in redacted
    assert "123-45-6789" not in redacted


def test_semantic_duplicate_detection(tmp_path, monkeypatch):
    import src.document_processor as dp

    fp_store = tmp_path / "fingerprints.json"
    monkeypatch.setattr(dp, "FINGERPRINT_STORE", fp_store)

    f1 = tmp_path / "d1.txt"
    f2 = tmp_path / "d2.txt"
    f1.write_text("Supplier lead time increased due to port congestion and weather.")
    f2.write_text("Port congestion and weather increased supplier lead time.")

    register_indexed(str(f1), chunk_count=1)
    assert is_semantically_duplicate(str(f2), threshold=0.5) is True
