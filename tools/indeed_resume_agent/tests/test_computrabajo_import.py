from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools.indeed_resume_agent.computrabajo_import import (
    load_manifest, prepare_candidate, upload_candidate, upload_manifest,
)


def test_single_candidate_uses_provider_and_external_identity(tmp_path):
    cv = tmp_path / "resume.pdf"
    cv.write_bytes(b"%PDF-1.5\nexample")
    payload = prepare_candidate(external_id="123", candidate_name="Example",
        job_title="Developer", source_account="asiati", file_path=str(cv))
    api = Mock()
    api.ingest_source_candidate.return_value = {"existing": False, "status": "RECEIVED"}
    assert upload_candidate(api, payload)["existing"] is False
    assert api.ingest_source_candidate.call_args.kwargs["provider"] == "COMPUTRABAJO"
    assert api.ingest_source_candidate.call_args.kwargs["external_id"] == "123"


@pytest.mark.parametrize("payload", [b"", b"<html>not PDF</html>", b"PKinvalid"])
def test_reject_invalid_pdf(tmp_path, payload):
    cv = tmp_path / "resume.pdf"
    cv.write_bytes(payload)
    with pytest.raises(ValueError):
        prepare_candidate(external_id="1", candidate_name="A", job_title="B",
            source_account="asiati", file_path=str(cv))


def test_batch_reports_existing_and_failures_independently(tmp_path):
    good = tmp_path / "a.pdf"
    good.write_bytes(b"%PDF-1.7\ntest")
    manifest = tmp_path / "candidates.csv"
    with manifest.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["external_id", "candidate_name", "job_title", "file"])
        writer.writeheader()
        writer.writerow(dict(external_id="1", candidate_name="A", job_title="Role", file="a.pdf"))
        writer.writerow(dict(external_id="2", candidate_name="B", job_title="Role", file="missing.pdf"))
    assert len(load_manifest(str(manifest))) == 2
    api = Mock()
    api.ingest_source_candidate.return_value = {"existing": True}
    report = upload_manifest(api, csv_path=str(manifest), source_account="asiati")
    assert report["existing"] == 1
    assert report["failed"] == 1
    assert report["created"] == 0


def test_manifest_reject_duplicate_external_ids(tmp_path):
    manifest = tmp_path / "batch.csv"
    manifest.write_text("external_id,candidate_name,job_title,file\n1,A,Role,a.pdf\n1,B,Role,b.pdf\n")
    with pytest.raises(ValueError, match="duplicados"):
        load_manifest(str(manifest))
