"""Prepare final human-review queue from historical CV recovery.

Never approves records automatically; never changes PostgreSQL.
Separates explicit name labels from mere top-of-page matches.
"""
import argparse
import csv
import os
from collections import Counter
from pathlib import Path

def review_tier(row):
    status=row.get("validation","")
    where=row.get("pdf_independent_check","")
    reason=row.get("reason","")
    if status=="REJECT":
        return "REJECTED", "previous_validation_rejected"
    if status=="UNRESOLVED":
        return "NEEDS_SOURCE_PROFILE", "no_model_identity"
    if reason=="duplicate_name_across_candidate_ids":
        return "MANUAL_DUPLICATE", reason
    if reason=="evidence_contains_job_or_non_candidate_context":
        return "MANUAL_CONTEXT", reason
    if where=="HEADER_TEXT_MATCH":
        return "PRIORITY_VISUAL_CONFIRMATION", "explicit_header_match"
    if where=="TOP_SECTION_MATCH":
        return "PRIORITY_VISUAL_CONFIRMATION", "top_section_only_not_proof"
    return "MANUAL_REVIEW", where or "missing_pdf_check"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    with open(args.input,encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows or not {"candidate_id","current_name","suggested_name","evidence","pdf_independent_check"}.issubset(rows[0]):
        raise ValueError("Expected bedrock_crosscheck_PRIVATE.csv")
    output=[]
    for row in rows:
        tier,reason=review_tier(row)
        output.append({
            "candidate_id":row["candidate_id"],
            "expected_current_name":row["current_name"],
            "suggested_name":row["suggested_name"],
            "evidence":row["evidence"],
            "pdf_independent_check":row["pdf_independent_check"],
            "review_tier":tier,
            "reason":reason,
            "approved_name":"",
            "reviewer":"",
            "decision":"PENDING_REVIEW",
        })
    dest=Path(args.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    print("TOTAL",len(output))
    print("TIERS",dict(Counter(r["review_tier"] for r in output)))
    print("REPORT_PRIVATE",dest)
    print("AUTO_APPROVALS 0 DB_CHANGES 0")

if __name__=="__main__":
    main()
