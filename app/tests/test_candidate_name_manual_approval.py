from unittest.mock import MagicMock
from fastapi import HTTPException
import pytest
from app.domains.candidates import name_normalization_router as names

UUID = "f8f50fc2-7cb4-4efe-b7bb-80c5fcb64ebd"

def db_with_candidate():
    from types import SimpleNamespace
    candidate=SimpleNamespace(id=UUID,name="computrabajo profile",metadata_={})
    db=MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.one_or_none.return_value=candidate
    return db,candidate

def test_admin_manual_name_requires_reason_and_preserves_audit():
    db,candidate=db_with_candidate()
    body=names.ApplyRequest(approvals=[names.NameApproval(candidate_id=UUID,expected_current_name=candidate.name, proposed_name="María Fernanda Torres",source="manual", review_reason="Validado en el encabezado del CV original.")])
    result=names.apply_normalized_names(body=body,db=db,user={"sub":"admin"})
    assert result["applied"]==1
    assert candidate.name=="María Fernanda Torres"
    event=candidate.metadata_["name_normalization_history"][0]
    assert event["source"]=="manual"
    assert event["review_reason"]=="Validado en el encabezado del CV original."
    db.commit.assert_called_once()

def test_manual_name_rejects_missing_reason():
    db,candidate=db_with_candidate()
    body=names.ApplyRequest(approvals=[names.NameApproval(candidate_id=UUID,expected_current_name=candidate.name,proposed_name="María Fernanda Torres",source="manual")])
    with pytest.raises(HTTPException) as error:
        names.apply_normalized_names(body=body,db=db,user={"sub":"admin"})
    assert error.value.status_code==422
    db.commit.assert_not_called()
    db.rollback.assert_called_once()

def test_manual_name_rejects_vacancy_title():
    db,candidate=db_with_candidate()
    body=names.ApplyRequest(approvals=[names.NameApproval(candidate_id=UUID,expected_current_name=candidate.name,proposed_name="Oferta Director financiero",source="manual",review_reason="Validado contra documento original.")])
    with pytest.raises(HTTPException) as error:
        names.apply_normalized_names(body=body,db=db,user={"sub":"admin"})
    assert error.value.status_code==422
    db.commit.assert_not_called()
