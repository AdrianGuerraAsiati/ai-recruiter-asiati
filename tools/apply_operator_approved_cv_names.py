"""Apply the 43 CV names explicitly approved by the operator.

Input is the private name_final_review_PRIVATE.csv on the Lightsail instance.
Hard-fails if identities changed or the expected count is not exactly 43.
A pg_dump is required before changes. Atomic transaction + rollback manifest.
"""
import argparse
import csv
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

REPO = "ai_recruiter"
SAFE = re.compile(r"^[^\\W\\d_]+(?:[ '\\-][^\\W\\d_]+){1,6}$", re.UNICODE)
BANNED = re.compile(r"computrabajo|oferta|vacante|no tengo empleo|carnet de conducir|director financiero", re.I)

def quote(v):
    return "'" + str(v).replace("'", "''") + "'"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--audit-dir",required=True)
    p.add_argument("--apply",action="store_true")
    args=p.parse_args()
    audit=Path(args.audit_dir)
    audit.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    with open(args.input,encoding="utf-8-sig",newline="") as f:
        rows=[r for r in csv.DictReader(f) if r.get("review_tier")=="PRIORITY_VISUAL_CONFIRMATION"]
    if len(rows)!=43:
        raise RuntimeError("Expected exactly 43 previously reviewed priority cases")
    seen=set()
    changes=[]
    for row in rows:
        cid=str(UUID(row["candidate_id"]))
        name=" ".join(row["suggested_name"].split())
        old=row["expected_current_name"]
        if cid in seen or not name or not old or not SAFE.fullmatch(name) or BANNED.search(name) or name==old:
            raise RuntimeError("Unsafe duplicate, invalid or unchanged name for ID "+cid)
        seen.add(cid)
        changes.append((cid,old,name))
    values=",\n".join("("+",".join(quote(v) for v in c)+")" for c in changes)
    # SQL is generated from locally validated values, with single-quote escaping.
    sql=f"""BEGIN;
CREATE TEMP TABLE adn360_name_corrections (candidate_id uuid PRIMARY KEY, old_name text NOT NULL, new_name text NOT NULL) ON COMMIT DROP;
INSERT INTO adn360_name_corrections VALUES {values};
DO $$
DECLARE missing integer;
BEGIN
SELECT count(*) INTO missing FROM adn360_name_corrections x LEFT JOIN candidates c
  ON c.id=x.candidate_id AND c.name=x.old_name
WHERE c.id IS NULL;
IF missing <> 0 THEN RAISE EXCEPTION 'ABORT: % candidate IDs or original names do not match database',missing; END IF;
END $$;
CREATE TEMP TABLE adn360_name_applied ON COMMIT DROP AS
WITH changed AS (
UPDATE candidates c SET name=x.new_name
FROM adn360_name_corrections x
WHERE c.id=x.candidate_id AND c.name=x.old_name
RETURNING c.id
) SELECT id FROM changed;
DO $$
DECLARE total integer;
BEGIN
SELECT count(*) INTO total FROM adn360_name_applied;
IF total <> 43 THEN RAISE EXCEPTION 'ABORT: expected 43 updates but found %',total; END IF;
END $$;
COMMIT;
"""
    manifest=audit/f"name_update_43_{stamp}_PRIVATE.json"
    with manifest.open("x",encoding="utf-8") as f:
        json.dump([{"candidate_id":i,"old_name":o,"new_name":n,"approved_by":"operator_bulk_approval_in_conversation"} for i,o,n in changes],f,ensure_ascii=False,indent=2)
    manifest.chmod(0o600)
    print("PREPARED",len(changes),"PRIVATE_MANIFEST",manifest)
    if not args.apply:
        print("DRY_RUN_ONLY; DB_CHANGES 0")
        return
    # Keep a separate database dump before modifying any candidate.
    backup=audit/f"ai_recruiter_before_names_{stamp}.dump"
    with backup.open("xb") as out:
        subprocess.run(["sudo","-u","postgres","pg_dump","-Fc","-d",REPO],stdout=out,check=True)
    backup.chmod(0o600)
    subprocess.run(["pg_restore","--list",str(backup)],stdout=subprocess.DEVNULL,check=True)
    proc=subprocess.run(["sudo","-u","postgres","psql","-X","-v","ON_ERROR_STOP=1","-d",REPO],input=sql,text=True,capture_output=True)
    if proc.returncode:
        raise RuntimeError("Transaction failed; no committed updates. "+proc.stderr[-800:])
    print("APPLIED 43; DB_BACKUP",backup,"ROLLBACK_MANIFEST",manifest)
if __name__=="__main__":main()
