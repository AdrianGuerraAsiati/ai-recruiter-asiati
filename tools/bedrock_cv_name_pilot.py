"""Multimodal Bedrock pilot for historical CV name recovery. Read-only.

CSV input: candidate_id,current_name. Default 5; --limit 147 for full batch.
All model suggestions require manual confirmation against the cited page.
Never use this output as automatic authorization to overwrite candidates.name.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
from collections import Counter
from pathlib import Path
from uuid import UUID

import boto3
import pymupdf

BUCKET = "ai-recruiter-cv-890876258895-us-east-2"
REGION = "us-east-2"
DEFAULT_MODEL = "amazon.nova-pro-v1:0"
_BAD = re.compile(r"\\b(?:oferta|vacante|computrabajo|curr[ií]culum|carnet|veh[ií]culo|no tengo empleo|estoy trabajando|director financiero)\\b", re.I)

INSTRUCTIONS = """You are performing *evidence-only* identity extraction on a recruitment CV.
The document may be a job advertisement, a generated Computrabajo profile,
or a resume. Identify the CANDIDATE'S legal or displayed full personal name ONLY
when that name is literally visible in the attached page image.
Do not infer names from email usernames, vacancy titles, employer names,
references, professional roles, profile pictures or guesses.
If no explicit personal name is visible, respond with null.
Return ONLY a JSON object with:
{"full_name": string|null, "exact_visible_evidence": string|null, "page": 1}
The evidence must be the exact text span visible in the image and contain the full name.
No commentary, no markdown.
"""

def verify(data):
    if not isinstance(data, dict):
        return "", "INVALID_RESPONSE", ""
    name = " ".join(str(data.get("full_name") or "").split())
    evidence = " ".join(str(data.get("exact_visible_evidence") or "").split())
    if not name or not evidence:
        return "", "NOT_VISIBLE", ""
    if len(name) > 90 or len(name.split()) < 2 or len(name.split()) > 6 or _BAD.search(name):
        return "", "INVALID_NAME", ""
    if name.casefold() not in evidence.casefold():
        return "", "EVIDENCE_MISMATCH", ""
    return name, "PENDING_VISUAL_REVIEW", evidence[:200]

def recover(s3, bedrock, candidate_id, model):
    raw = s3.get_object(Bucket=BUCKET, Key=f"documents/cv-{candidate_id}.pdf")["Body"].read()
    with pymupdf.open(stream=raw, filetype="pdf") as document:
        if len(document) < 1:
            return "", "EMPTY_PDF", "", 0
        page = document[0]
        ratio = min(1.8, 1500 / max(page.rect.width, 1), 1500 / max(page.rect.height, 1))
        image_bytes = page.get_pixmap(matrix=pymupdf.Matrix(ratio, ratio), alpha=False).tobytes("png")
    response = bedrock.converse(
        modelId=model,
        system=[{"text": INSTRUCTIONS}],
        messages=[{"role":"user","content":[
            {"text":"Identify the candidate's personal name in this page image. Return JSON only."},
            {"image":{"format":"png","source":{"bytes":image_bytes}}}
        ]}],
        inferenceConfig={"maxTokens":250,"temperature":0},
    )
    content = response["output"]["message"]["content"]
    answer = "".join(block.get("text","") for block in content)
    answer = answer.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError:
        return "", "INVALID_JSON", "", response.get("usage",{}).get("totalTokens",0)
    name, status, evidence = verify(parsed)
    return name, status, evidence, response.get("usage",{}).get("totalTokens",0)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--limit",type=int,default=5)
    parser.add_argument("--model",default=DEFAULT_MODEL)
    parser.add_argument("--profile",default="ai-recruiter-bedrock")
    args=parser.parse_args()
    if not (1 <= args.limit <= 147):
        raise ValueError("--limit must be between 1 and 147")
    with open(args.input,encoding="utf-8-sig",newline="") as stream:
        rows=list(csv.DictReader(stream))
    if not {"candidate_id","current_name"}.issubset(rows[0] if rows else {}):
        raise ValueError("CSV requires candidate_id,current_name")
    ids=[str(UUID(row["candidate_id"])) for row in rows[:args.limit]]
    if len(ids)!=len(set(ids)):
        raise ValueError("Duplicate candidate UUID")
    session=boto3.Session(profile_name=args.profile,region_name=REGION)
    s3=session.client("s3")
    bedrock=session.client("bedrock-runtime")
    results=[]
    for row,cid in zip(rows[:args.limit],ids):
        try:
            name,status,evidence,tokens=recover(s3,bedrock,cid,args.model)
        except Exception as exc:
            name,status,evidence,tokens="","API_OR_DOCUMENT_ERROR",type(exc).__name__,0
        results.append({"candidate_id":cid,"current_name":row["current_name"],
                        "suggested_name":name,"status":status,
                        "evidence":evidence,"tokens":tokens,"decision":"PENDING_REVIEW"})
        print("PROCESSED",len(results),"STATUS",status,flush=True)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print("TOTAL",len(results),"COUNTS",dict(Counter(r["status"] for r in results)))
    print("OUTPUT_PRIVATE",path,"DB_CHANGES",0)

if __name__=="__main__":
    main()
