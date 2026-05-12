"""
Multi-format document processor with semantic chunking and fingerprint-based
incremental re-indexing.

Supported formats : .txt  .pdf  .md  .csv  .xlsx  .xls
Chunking strategies: "sentence" (default) | "semantic" | "fixed"

Fingerprinting     : SHA-256 of file bytes stored in data/fingerprints.json.
                     Unchanged files are skipped on re-upload.
"""

import csv
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from llama_index.core import Document

logger = logging.getLogger(__name__)

FINGERPRINT_STORE = Path("data/fingerprints.json")
_CSV_BATCH_ROWS = 20   # rows per Document chunk for CSV/Excel


# ─────────────────────────── fingerprinting ───────────────────────────────

def file_hash(file_path: str) -> str:
    """Return SHA-256 hex digest of the file's raw bytes."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_fingerprints() -> dict:
    if FINGERPRINT_STORE.exists():
        try:
            return json.loads(FINGERPRINT_STORE.read_text())
        except Exception:
            return {}
    return {}


def _save_fingerprints(fp: dict) -> None:
    FINGERPRINT_STORE.parent.mkdir(parents=True, exist_ok=True)
    FINGERPRINT_STORE.write_text(json.dumps(fp, indent=2))


def is_already_indexed(file_path: str) -> bool:
    """Return True if this exact file content has already been indexed."""
    sha = file_hash(file_path)
    return _load_fingerprints().get(sha, {}).get("indexed", False)


def register_indexed(file_path: str, chunk_count: int) -> None:
    """Mark a file as successfully indexed."""
    sha = file_hash(file_path)
    fp = _load_fingerprints()
    fp[sha] = {
        "filename": Path(file_path).name,
        "indexed": True,
        "chunk_count": chunk_count,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_fingerprints(fp)
    logger.info(f"Fingerprint registered: {Path(file_path).name} ({chunk_count} chunks)")


def get_fingerprint_registry() -> dict:
    """Return the full fingerprint store for inspection."""
    return _load_fingerprints()


# ─────────────────────────── loaders ──────────────────────────────────────

def load_file_as_documents(file_path: str, metadata: dict) -> list[Document]:
    """Dispatch to the correct loader based on file extension."""
    ext = Path(file_path).suffix.lower()
    if ext == ".csv":
        return _load_csv(file_path, metadata)
    if ext in {".xlsx", ".xls"}:
        return _load_excel(file_path, metadata)
    # txt / md / pdf → read as plain text when possible so the demo does not
    # depend on optional file-reader extras.
    try:
        if ext == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore
            except ImportError:
                with open(file_path, "rb") as f:
                    raw = f.read().decode("utf-8", errors="ignore")
                text = raw.strip()
            else:
                reader = PdfReader(file_path)
                text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()

        if not text:
            text = Path(file_path).name

        return [Document(text=text, metadata={"file_name": Path(file_path).name, "file_type": ext.lstrip("."), **metadata})]
    except Exception as e:
        logger.error(f"Failed to load text file {file_path}: {e}")
        raise


def _load_csv(file_path: str, metadata: dict) -> list[Document]:
    """
    Convert a CSV to Documents.  Every _CSV_BATCH_ROWS rows are merged into
    one Document so the LLM receives relational context rather than isolated
    field values.
    """
    documents: list[Document] = []
    try:
        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            headers = list(reader.fieldnames or [])

        stem = Path(file_path).stem
        for i in range(0, len(rows), _CSV_BATCH_ROWS):
            batch = rows[i: i + _CSV_BATCH_ROWS]
            lines = [
                ", ".join(f"{k}: {v}" for k, v in row.items())
                for row in batch
            ]
            text = (
                f"[Table: {stem}]\n"
                f"Columns: {', '.join(headers)}\n\n"
                + "\n".join(lines)
            )
            documents.append(Document(
                text=text,
                metadata={
                    "file_name": Path(file_path).name,
                    "file_type": "csv",
                    "row_start": i,
                    "row_end": i + len(batch) - 1,
                    **metadata,
                },
            ))
        logger.info(f"CSV: {len(rows)} rows → {len(documents)} docs from {Path(file_path).name}")
    except Exception as e:
        logger.error(f"Failed to load CSV {file_path}: {e}")
        raise
    return documents


def _load_excel(file_path: str, metadata: dict) -> list[Document]:
    """Convert an Excel workbook to Documents (one batch per sheet)."""
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "pandas + openpyxl required for Excel ingestion: "
            "pip install pandas openpyxl"
        )
    documents: list[Document] = []
    try:
        xl = pd.ExcelFile(file_path)
        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)
            rows = df.to_dict(orient="records")
            headers = [str(c) for c in df.columns]
            for i in range(0, len(rows), _CSV_BATCH_ROWS):
                batch = rows[i: i + _CSV_BATCH_ROWS]
                lines = [
                    ", ".join(f"{k}: {v}" for k, v in row.items())
                    for row in batch
                ]
                text = (
                    f"[Sheet: {sheet_name}]\n"
                    f"Columns: {', '.join(headers)}\n\n"
                    + "\n".join(lines)
                )
                documents.append(Document(
                    text=text,
                    metadata={
                        "file_name": Path(file_path).name,
                        "sheet_name": sheet_name,
                        "file_type": "excel",
                        "row_start": i,
                        **metadata,
                    },
                ))
        logger.info(f"Excel: {len(documents)} docs from {Path(file_path).name}")
    except Exception as e:
        logger.error(f"Failed to load Excel {file_path}: {e}")
        raise
    return documents


# ─────────────────────────── chunking ─────────────────────────────────────

def apply_chunking(
    documents: list[Document],
    chunk_size: int = 1024,
    chunk_overlap: int = 256,
    strategy: str = "sentence",
    embed_model=None,
) -> list:
    """
    Split documents into indexable nodes.

    strategy="sentence" — SentenceSplitter: respects sentence boundaries.
                          Recommended for most supply chain documents.
    strategy="semantic"  — SemanticSplitterNodeParser: uses embeddings to
                           detect topic shifts. Highest quality; adds latency.
                           Falls back to "sentence" if not installed.
    strategy="fixed"    — Raw character-based splitting (legacy behaviour).
    """
    if not documents:
        return []

    if strategy == "semantic" and embed_model is not None:
        try:
            from llama_index.core.node_parser import SemanticSplitterNodeParser
            splitter = SemanticSplitterNodeParser(
                embed_model=embed_model,
                breakpoint_percentile_threshold=95,
            )
            nodes = splitter.get_nodes_from_documents(documents)
            logger.info(f"Semantic chunking: {len(documents)} docs → {len(nodes)} nodes")
            return nodes
        except ImportError:
            logger.warning("SemanticSplitterNodeParser unavailable; falling back to sentence")
            strategy = "sentence"

    if strategy in {"sentence", "fixed"}:
        from llama_index.core.node_parser import SentenceSplitter
        splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        nodes = splitter.get_nodes_from_documents(documents)
        logger.info(f"Sentence chunking: {len(documents)} docs → {len(nodes)} nodes")
        return nodes

    return documents  # fallback: no chunking
