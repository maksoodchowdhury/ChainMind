import pytest
from src.document_catalog import (
    get_catalog_document,
    list_catalog_documents,
    mark_job_result,
    register_upload,
    transition_lifecycle_state,
)


def test_register_upload_increments_version():
    first = register_upload("phase2_versioning.txt", {"doc_type": "policy"}, "job-1")
    second = register_upload("phase2_versioning.txt", {"doc_type": "policy"}, "job-2")

    assert first["version"] >= 1
    assert second["version"] == first["version"] + 1
    assert second["lifecycle_state"] == "draft"


def test_mark_job_result_updates_lifecycle():
    uploaded = register_upload("phase2_lifecycle.txt", {}, "job-lifecycle")
    assert uploaded["lifecycle_state"] == "draft"

    mark_job_result(
        "phase2_lifecycle.txt",
        "job-lifecycle",
        lifecycle_state="approved",
        chunk_count=9,
    )

    docs = {d["filename"]: d for d in list_catalog_documents()}
    assert docs["phase2_lifecycle.txt"]["lifecycle_state"] == "approved"
    assert docs["phase2_lifecycle.txt"]["chunk_count"] == 9


def test_get_catalog_document_returns_entry():
    register_upload("phase2_get_test.txt", {"doc_type": "demand_plan"}, "job-get-1")
    entry = get_catalog_document("phase2_get_test.txt")
    assert entry is not None
    assert entry["filename"] == "phase2_get_test.txt"


def test_get_catalog_document_returns_none_for_unknown():
    assert get_catalog_document("definitely_does_not_exist.txt") is None


def test_transition_lifecycle_draft_to_approved():
    register_upload("phase2_trans_test.txt", {}, "job-trans-1")
    mark_job_result("phase2_trans_test.txt", "job-trans-1", lifecycle_state="approved")
    entry = transition_lifecycle_state("phase2_trans_test.txt", "retired")
    assert entry["lifecycle_state"] == "retired"


def test_transition_lifecycle_invalid_raises():
    register_upload("phase2_trans_invalid.txt", {}, "job-trans-inv")
    with pytest.raises(ValueError, match="Cannot transition"):
        transition_lifecycle_state("phase2_trans_invalid.txt", "retired")


def test_transition_lifecycle_terminal_raises():
    register_upload("phase2_trans_terminal.txt", {}, "job-trans-term")
    mark_job_result("phase2_trans_terminal.txt", "job-trans-term", lifecycle_state="approved")
    transition_lifecycle_state("phase2_trans_terminal.txt", "retired")
    with pytest.raises(ValueError, match="terminal"):
        transition_lifecycle_state("phase2_trans_terminal.txt", "draft")


def test_transition_lifecycle_not_found_raises():
    with pytest.raises(KeyError):
        transition_lifecycle_state("ghost_document.txt", "approved")


def test_transition_history_appended():
    register_upload("phase2_history_test.txt", {}, "job-hist-1")
    entry = transition_lifecycle_state("phase2_history_test.txt", "approved")
    # The last history item should be the state_transition event
    transition_events = [h for h in entry["history"] if h.get("event") == "state_transition"]
    assert len(transition_events) >= 1
    assert transition_events[-1]["to_state"] == "approved"
