"""Read-only batch CV name recovery.

Input CSV: candidate_id (optionally current_name). AWS profile must have GetObject.
Produces a private CSV with suggested names, evidence and review status.
No PostgreSQL writes; never approves names solely by a heuristic.
"""
import argparse
import csv
import os
from pathlib import Path
from uuid import UUID

import boto3
from botocore.exceptions import ClientError

from app.domains.candidates.cv_name_detection import detect_cv_name


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--bucket", required=True)
    p.add_argument("--profile", default="ai-recruiter-bedrock")
    p.add_argument("--region", default="us-east-2")
    args = p.parse_args()
    path = Path(args.output)
    if path.exists():
        raise FileExistsError("Use a new output filename, existing audit will not be overwritten")
    with open(args.input, newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != len({row["candidate_id"] for row in rows}):
        raise ValueError("Duplicate candidate IDs")
    s3 = boto3.Session(profile_name=args.profile, region_name=args.region).client("s3")
    results = []
    for index, row in enumerate(rows, 1):
        candidate_id = str(UUID(row["candidate_id"]))
        try:
            key = f"documents/cv-{candidate_id}.pdf"
            raw = s3.get_object(Bucket=args.bucket, Key=key)["Body"].read()
            evidence = detect_cv_name(raw, "cv.pdf")
            status, name, source = evidence.status, evidence.name or "", evidence.evidence
        except (ClientError, ValueError, OSError) as exc:
            status, name, source = "DOCUMENT_ERROR", "", type(exc).__name__
        results.append({
            "candidate_id": candidate_id,
            "current_name": row.get("current_name", ""),
            "suggested_name": name,
            "status": status,
            "evidence_type": source,
            "decision": "PENDING_REVIEW",
        })
        if index % 25 == 0:
            print("Processed:", index, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys() if results else [
            "candidate_id", "current_name", "suggested_name", "status", "evidence_type", "decision"])
        writer.writeheader()
        writer.writerows(results)
    from collections import Counter
    print("TOTAL:", len(results), "RESULTS:", dict(Counter(r["status"] for r in results)))
    print("PRIVATE_REPORT:", path, "DATABASE_CHANGES: 0")


if __name__ == "__main__":
    main()
