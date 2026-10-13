"""Offline quality gates for historical Bedrock name suggestions.

Reads existing CSV; no AWS calls, no DB writes, and no automatic approvals.
Output retains reviewer-ready evidence and flags high-risk candidates.
"""
import argparse
import csv
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from uuid import UUID

BANNED = re.compile(r"\b(?:oferta|vacante|computrabajo|carnet|licencia|curriculum|currículo|hoja de vida|puesto|cargo|empleo|disponibilidad|referencias|referencia laboral|reclutador|director financiero|recursos humanos|selecci[oó]n|perfil profesional)\b", re.I)
NAME = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+){1,6}$", re.UNICODE)

def normalize(s):
    s=unicodedata.normalize("NFKD",s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()

def assess(row, repeated):
    proposed=" ".join(row.get("suggested_name","").split())
    evidence=" ".join(row.get("evidence","").split())
    if row.get("status")!="PENDING_VISUAL_REVIEW" or not proposed:
        return "UNRESOLVED","model_did_not_supply_evidenced_name"
    if not (5 <= len(proposed) <= 90 and NAME.fullmatch(proposed)) or BANNED.search(proposed):
        return "REJECT","invalid_or_non_person_name"
    if normalize(proposed) not in normalize(evidence):
        return "REJECT","evidence_does_not_contain_name"
    if evidence and BANNED.search(evidence):
        return "REVIEW","evidence_contains_job_or_non_candidate_context"
    if repeated[normalize(proposed)] > 1:
        return "REVIEW","duplicate_name_across_candidate_ids"
    return "REVIEW","requires_original_page_visual_confirmation"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    with open(args.input,encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    required={"candidate_id","current_name","suggested_name","status","evidence"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Missing required audit columns")
    ids=[str(UUID(r["candidate_id"])) for r in rows]
    if len(ids)!=len(set(ids)):
        raise ValueError("Duplicate candidate IDs")
    repeated=Counter(normalize(r.get("suggested_name","")) for r in rows if r.get("suggested_name","").strip())
    enriched=[]
    for row in rows:
        verdict,reason=assess(row,repeated)
        enriched.append({
            "candidate_id":row["candidate_id"],"current_name":row["current_name"],
            "suggested_name":row["suggested_name"],"status":row["status"],
            "evidence":row["evidence"],"validation":verdict,
            "reason":reason,"approved_name":"","reviewer":"","decision":"PENDING_REVIEW",
        })
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(enriched[0]))
        writer.writeheader()
        writer.writerows(enriched)
    print("TOTAL",len(enriched),"VALIDATION",dict(Counter(r["validation"] for r in enriched)))
    print("REASONS",dict(Counter(r["reason"] for r in enriched)))
    print("REPORT_PRIVATE",target,"APPROVED_AUTOMATICALLY",0,"DB_CHANGES",0)

if __name__=="__main__":
    main()
