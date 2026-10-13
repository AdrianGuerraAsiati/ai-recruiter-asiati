"""Cross-check Bedrock proposals against independent PDF text geometry.

Read-only: never writes to DB. Do not automatically approve based on text.
Input CSV from validate_bedrock_cv_names.py.
"""
import argparse
import csv
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path
from uuid import UUID

import boto3
import pymupdf

BUCKET="ai-recruiter-cv-890876258895-us-east-2"

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or "").casefold())
    return re.sub(r"\s+"," ","".join(c for c in s if not unicodedata.combining(c))).strip()

def check_name(raw, name):
    key=norm(name)
    if not key:
        return "NO_PROPOSAL",""
    with pymupdf.open(stream=raw,filetype="pdf") as doc:
        if len(doc)<1:
            return "EMPTY_DOCUMENT",""
        page=doc[0]
        lines=[]
        for block in page.get_text("dict").get("blocks",[]):
            if "lines" not in block:
                continue
            for line in block["lines"]:
                txt=" ".join(span.get("text","") for span in line.get("spans",[])).strip()
                if txt:
                    y=min(span.get("bbox",[0,99999])[1] for span in line.get("spans",[]))
                    lines.append((norm(txt),float(y),txt))
        matches=[(t,y,raw_text) for t,y,raw_text in lines if key in t]
        if not matches:
            return "NOT_FOUND_IN_EXTRACTABLE_TEXT","visual_review_needed"
        first=min(matches,key=lambda m:m[1])
        height=max(float(page.rect.height),1.0)
        is_top=(first[1]/height)<=0.30
        exact=any(t==key or t.startswith("nombre completo: "+key) or t.startswith("nombre: "+key) for t,y,_ in matches)
        if is_top and exact:
            return "HEADER_TEXT_MATCH","top_30_percent_and_explicit"
        if is_top:
            return "TOP_SECTION_MATCH","top_30_percent"
        return "BODY_TEXT_MATCH","not_in_header"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--profile",default="ai-recruiter-bedrock")
    args=ap.parse_args()
    with open(args.input,encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    required={"candidate_id","suggested_name","validation","status","evidence","current_name"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Missing CSV columns")
    uuids=[str(UUID(r["candidate_id"])) for r in rows]
    if len(set(uuids))!=len(uuids):
        raise ValueError("Duplicate UUIDs")
    s3=boto3.Session(profile_name=args.profile,region_name="us-east-2").client("s3")
    out=[]
    for index,(row,cid) in enumerate(zip(rows,uuids),1):
        match="SKIPPED"
        detail=""
        if row["validation"]=="REVIEW" and row["suggested_name"].strip():
            try:
                data=s3.get_object(Bucket=BUCKET,Key=f"documents/cv-{cid}.pdf")["Body"].read()
                match,detail=check_name(data,row["suggested_name"])
            except Exception as exc:
                match,detail="DOCUMENT_ERROR",type(exc).__name__
        enriched=dict(row)
        enriched["pdf_independent_check"]=match
        enriched["pdf_check_detail"]=detail
        enriched["decision"]="PENDING_REVIEW"
        out.append(enriched)
        if index%25==0:
            print("PROCESSED",index,flush=True)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print("TOTAL",len(out),"PDF_CHECKS",dict(Counter(r["pdf_independent_check"] for r in out)))
    print("REPORT_PRIVATE",path,"AUTO_APPROVED",0,"DB_CHANGES",0)

if __name__=="__main__":
    main()
