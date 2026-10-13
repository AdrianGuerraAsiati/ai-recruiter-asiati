"""Read-only batch review of suspected candidate names from S3 PDFs."""
import csv
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID
import boto3
import pymupdf
from botocore.exceptions import ClientError

EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
LABEL = re.compile(r"^(?:nombre(?:\s+completo)?|nombres?\s+y\s+apellidos?|apellidos?\s+y\s+nombres?)\s*[:\-]\s*(.+)$", re.I)
BAD = re.compile(r"\b(?:oferta|vacante|computrabajo|curr[ií]culum|hoja de vida|carnet|veh[ií]culo|disponibilidad|experiencia|perfil|director financiero|no tengo empleo|estoy trabajando|referencias|educaci[oó]n|formaci[oó]n|habilidades)\b", re.I)
NAME = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+){1,5}$", re.UNICODE)
BUCKET = "ai-recruiter-cv-890876258895-us-east-2"

def plausible(s):
    return 5 <= len(s) <= 80 and bool(NAME.fullmatch(s)) and not BAD.search(s) and not EMAIL.search(s)

def classify(data):
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        lines = [" ".join(line.split()) for p in list(doc)[:3] for line in p.get_text().splitlines()]
    lines = [x for x in lines if x]
    labels = [m.group(1) for x in lines[:150] if (m := LABEL.match(x)) and plausible(m.group(1))]
    uniq = {v.casefold(): v for v in labels}
    if len(uniq) == 1:
        return next(iter(uniq.values())), "EXPLICIT_NAME_FIELD", "explicit_label"
    if len(uniq) > 1:
        return "", "CONFLICT", "different_explicit_labels"
    near = []
    for i, line in enumerate(lines[:100]):
        if EMAIL.search(line):
            near.extend(x for x in lines[max(0,i-4):i] if plausible(x))
    uniq = {v.casefold(): v for v in near}
    if len(uniq) == 1:
        return next(iter(uniq.values())), "REVIEW_EMAIL_CONTEXT", "near_email"
    return "", "UNRESOLVED", "insufficient_evidence"

def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: recover_names_once.py INPUT OUTPUT")
    source, target = sys.argv[1:]
    with open(source, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    ids = [str(UUID(r["candidate_id"])) for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate candidate UUID")
    s3 = boto3.Session(profile_name="ai-recruiter-bedrock",region_name="us-east-2").client("s3")
    results = []
    for i, (row, cid) in enumerate(zip(rows,ids),1):
        try:
            data = s3.get_object(Bucket=BUCKET, Key=f"documents/cv-{cid}.pdf")["Body"].read()
            suggestion, status, evidence = classify(data)
        except (ClientError, ValueError, RuntimeError, OSError) as exc:
            suggestion,status,evidence = "","DOCUMENT_ERROR",type(exc).__name__
        results.append(dict(candidate_id=cid,current_name=row.get("current_name",""),suggested_name=suggestion,status=status,evidence_type=evidence,decision="PENDING_REVIEW"))
        if i%25==0:
            print("PROCESADOS:",i,flush=True)
    fields=["candidate_id","current_name","suggested_name","status","evidence_type","decision"]
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8",newline="") as f:
        out=csv.DictWriter(f,fieldnames=fields)
        out.writeheader()
        out.writerows(results)
    print("TOTAL:",len(results))
    for k,n in sorted(Counter(r["status"] for r in results).items()):
        print(k+":",n)
    print("CAMBIOS EN POSTGRESQL: 0")
    print("REPORTE PRIVADO:",target)

if __name__=="__main__":
    main()
