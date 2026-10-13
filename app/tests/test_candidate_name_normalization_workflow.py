"""Coverage of the candidate-name normalization workflow without AWS calls."""
import hashlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.domains.candidates import name_normalization_router as module

UUID_ONE = "f8f50fc2-7cb4-4efe-b7bb-80c5fcb64ebd"
UUID_TWO = "a61b852f-5cbf-4ee9-b8c4-80c5fcb64ebd"
USER = {"sub": "admin-test"}
NAME = "María Fernanda Torres"


def fake_db(candidate=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = candidate
    db.query.return_value.filter.return_value.with_for_update.return_value.one_or_none.return_value = candidate
    return db


def candidate(name="Computrabajo profile", metadata=None):
    return SimpleNamespace(id=UUID_ONE, name=name, metadata_={} if metadata is None else metadata)


def stored_proposal():
    return {
        "name_normalization": {
            "document_sha256": "abc",
            "model": module._MODEL,
            "suggested_name": NAME,
            "evidence": "Nombre completo: " + NAME,
            "status": "REVIEW_REQUIRED",
        }
    }


def test_preview_scans_shared_directory_and_flags():
    db = fake_db()
    db.query.return_value.order_by.return_value.all.return_value = [
        (UUID_ONE, "Computrabajo profile"),
        (UUID_TWO, "María González"),
        ("3", "Ana"),
        ("4", "Juan@correo.com"),
    ]
    response = module.preview_candidate_name_normalization(db=db, user=USER, limit=10)
    assert response["total_scanned"] == 4
    assert response["suspected_count"] == 3
    assert response["auto_changed"] == 0
    assert len(response["items"]) == 3
    assert "suspected_import_artifact" in response["reasons"]


def test_preview_respects_item_limit_but_counts_all():
    db = fake_db()
    db.query.return_value.order_by.return_value.all.return_value = [
        (UUID_ONE, "Computrabajo"), (UUID_TWO, "Oferta Director"),
    ]
    output = module.preview_candidate_name_normalization(db=db, user=USER, limit=1)
    assert output["suspected_count"] == 2
    assert output["has_more"] is True
    assert len(output["items"]) == 1


def test_ask_bedrock_accepts_literal_name_and_rejects_unsupported():
    session = MagicMock()
    result = {"output": {"message": {"content": [{
        "text": json.dumps({
            "full_name": NAME,
            "exact_visible_evidence": "Nombre completo: " + NAME,
        })
    }]}}}
    session.client.return_value.converse.return_value = result
    name, evidence, status = module._ask_bedrock(session, b"png")
    assert (name, status) == (NAME, "REVIEW_REQUIRED")
    assert NAME in evidence
    assert session.client.return_value.converse.call_args.kwargs["modelId"] == module._MODEL
    result["output"]["message"]["content"] = [{"text": "not JSON"}]
    assert module._ask_bedrock(session, b"png")[2] == "UNRESOLVED"
    result["output"]["message"]["content"] = [{"text": "[]"}]
    assert module._ask_bedrock(session, b"png")[2] == "UNRESOLVED"
    result["output"]["message"]["content"] = [{
        "text": json.dumps({"full_name": NAME, "exact_visible_evidence": "Cargo: Supervisor"})
    }]
    assert module._ask_bedrock(session, b"png")[2] == "UNRESOLVED"


def test_suggest_reuses_document_sha_cache_without_model_call():
    saved = candidate(metadata=stored_proposal())
    db = fake_db(saved)
    with patch.object(module, "_cv_image", return_value=(MagicMock(), "abc", b"image")), \
         patch.object(module, "_ask_bedrock") as model:
        response = module.suggest_candidate_names(
            body=module.SuggestRequest(candidate_ids=[UUID_ONE]), db=db, user=USER
        )
    assert response["items"][0]["cached"] is True
    assert response["items"][0]["suggested_name"] == NAME
    model.assert_not_called()
    db.commit.assert_not_called()


def test_suggest_calls_model_and_caches_new_proposal():
    saved = candidate()
    db = fake_db(saved)
    with patch.object(module, "_cv_image", return_value=(MagicMock(), "abc", b"image")), \
         patch.object(module, "_ask_bedrock", return_value=(NAME, "Nombre completo: " + NAME, "REVIEW_REQUIRED")):
        output = module.suggest_candidate_names(
            body=module.SuggestRequest(candidate_ids=[UUID_ONE]), db=db, user=USER
        )
    assert output["items"][0]["cached"] is False
    assert saved.metadata_["name_normalization"]["document_sha256"] == "abc"
    db.commit.assert_called_once()


def test_suggest_handles_api_error_without_persisting_name():
    saved = candidate()
    db = fake_db(saved)
    with patch.object(module, "_cv_image", side_effect=RuntimeError("not available")):
        result = module.suggest_candidate_names(
            body=module.SuggestRequest(candidate_ids=[UUID_ONE]), db=db, user=USER
        )
    assert result["items"][0]["status"] == "PROCESSING_ERROR"
    db.rollback.assert_called_once()
    assert saved.name == "Computrabajo profile"


def test_suggest_does_not_reprocess_clean_name():
    db = fake_db(candidate(name=NAME))
    with patch.object(module, "_cv_image") as image:
        result = module.suggest_candidate_names(
            body=module.SuggestRequest(candidate_ids=[UUID_ONE]), db=db, user=USER
        )
    assert result["items"][0]["status"] == "ALREADY_VALID"
    image.assert_not_called()


def test_suggest_rejects_unknown_uuid_or_missing_candidate():
    db = fake_db()
    with pytest.raises(HTTPException) as invalid:
        module.suggest_candidate_names(
            body=module.SuggestRequest(candidate_ids=["not-uuid"]), db=db, user=USER
        )
    assert invalid.value.status_code == 400
    with pytest.raises(HTTPException) as missing:
        module.suggest_candidate_names(
            body=module.SuggestRequest(candidate_ids=[UUID_ONE]), db=db, user=USER
        )
    assert missing.value.status_code == 404


def test_apply_stores_auditable_old_and_new_names():
    saved = candidate(metadata=stored_proposal())
    db = fake_db(saved)
    result = module.apply_normalized_names(
        body=module.ApplyRequest(approvals=[module.NameApproval(
            candidate_id=UUID_ONE,
            expected_current_name="Computrabajo profile",
            proposed_name=NAME,
        )]), db=db, user=USER
    )
    assert result["applied"] == 1
    assert saved.name == NAME
    assert saved.metadata_["name_normalization_history"][0]["previous_name"] == "Computrabajo profile"
    db.commit.assert_called_once()


def test_apply_conflict_does_not_commit():
    db = fake_db(candidate(name="Already corrected", metadata=stored_proposal()))
    with pytest.raises(HTTPException) as err:
        module.apply_normalized_names(
            body=module.ApplyRequest(approvals=[module.NameApproval(
                candidate_id=UUID_ONE,
                expected_current_name="Computrabajo profile",
                proposed_name=NAME,
            )]), db=db, user=USER
        )
    assert err.value.status_code == 409
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_apply_rejects_a_name_without_cached_evidence():
    db = fake_db(candidate())
    with pytest.raises(HTTPException) as err:
        module.apply_normalized_names(
            body=module.ApplyRequest(approvals=[module.NameApproval(
                candidate_id=UUID_ONE,
                expected_current_name="Computrabajo profile",
                proposed_name=NAME,
            )]), db=db, user=USER
        )
    assert err.value.status_code == 409
    db.commit.assert_not_called()


def test_per_candidate_revert_restores_previous_identity():
    saved = candidate(name=NAME, metadata={
        "name_normalization_history": [{
            "change_id": UUID_TWO,
            "batch_id": UUID_ONE,
            "previous_name": "Computrabajo profile",
            "new_name": NAME,
        }]
    })
    db = fake_db(saved)
    result = module.revert_normalized_name(
        body=module.RevertRequest(candidate_id=UUID_ONE, change_id=UUID_TWO),
        db=db, user=USER,
    )
    assert result["reverted"] is True
    assert saved.name == "Computrabajo profile"
    assert not saved.metadata_["name_normalization_history"]
    assert saved.metadata_["name_normalization_last_reverted"]["reverted_by"] == "admin-test"
    db.commit.assert_called_once()


def test_revert_rejects_outdated_receipt():
    saved = candidate(name=NAME, metadata={"name_normalization_history": []})
    db = fake_db(saved)
    with pytest.raises(HTTPException) as err:
        module.revert_normalized_name(
            body=module.RevertRequest(candidate_id=UUID_ONE, change_id=UUID_TWO),
            db=db, user=USER,
        )
    assert err.value.status_code == 409


def test_revert_batch_restores_all_candidates_atomically():
    change = {"change_id": UUID_TWO, "batch_id": UUID_ONE,
              "previous_name": "Computrabajo profile", "new_name": NAME}
    first = candidate(name=NAME, metadata={"name_normalization_history": [change]})
    db = fake_db()
    db.query.return_value.order_by.return_value.with_for_update.return_value.all.return_value = [first]
    output = module.revert_name_normalization_batch(
        body=module.RevertBatchRequest(batch_id=UUID_ONE), db=db, user=USER
    )
    assert output["reverted"] == 1
    assert first.name == "Computrabajo profile"
    db.commit.assert_called_once()


def test_revert_batch_rejects_unknown_batch():
    db = fake_db()
    db.query.return_value.order_by.return_value.with_for_update.return_value.all.return_value = []
    with pytest.raises(HTTPException) as err:
        module.revert_name_normalization_batch(
            body=module.RevertBatchRequest(batch_id=UUID_ONE), db=db, user=USER
        )
    assert err.value.status_code == 404
    db.rollback.assert_called_once()


def test_history_groups_changes_by_batch():
    db = fake_db()
    db.query.return_value.all.return_value = [
        ({"name_normalization_history": [
            {"batch_id": UUID_ONE, "approved_at": "2026-10-13T10:00:00"},
        ]},),
        ({"name_normalization_history": [
            {"batch_id": UUID_ONE, "approved_at": "2026-10-13T10:00:02"},
            {"batch_id": UUID_TWO, "approved_at": "2026-10-13T10:00:01"},
        ]},),
    ]
    result = module.list_name_normalization_history(db=db, user=USER)
    assert result["items"][0]["batch_id"] == UUID_ONE
    assert result["items"][0]["count"] == 2


def test_cv_image_renders_first_pdf_page_and_hashes_document():
    raw = b"%PDF-1.7 mocked bytes"
    fake_boto = MagicMock()
    fake_boto.Session.return_value.client.return_value.get_object.return_value = {
        "Body": SimpleNamespace(read=lambda maximum: raw)
    }
    page = MagicMock()
    page.rect.width = 500
    page.rect.height = 800
    page.get_pixmap.return_value.tobytes.return_value = b"png-bytes"
    pdf = MagicMock()
    pdf.page_count = 1
    pdf.__enter__.return_value = pdf
    pdf.__getitem__.return_value = page
    fake_pymupdf = MagicMock()
    fake_pymupdf.open.return_value = pdf
    with patch.object(module, "boto3", fake_boto), \
         patch.dict(sys.modules, {"pymupdf": fake_pymupdf}), \
         patch.dict("os.environ", {"S3_BUCKET": "unit-test-bucket"}):
        session, digest, image = module._cv_image(UUID_ONE)
    assert session == fake_boto.Session.return_value
    assert digest == hashlib.sha256(raw).hexdigest()
    assert image == b"png-bytes"
