"""Batch update only independently verified candidate names.

CSV: candidate_id,approved_name,expected_current_name,reviewer,evidence,decision
Default is dry run; --apply updates names in one transaction with private audit.
Run in an environment with SQLAlchemy and database access. Never use generic
Computrabajo metadata or a guessed email prefix as a person's name.
"""
import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, text

INVALID = re.compile(r"computrabajo|oferta|vacante|curriculum|carnet|veh[ií]culo|disponibilidad|no tengo empleo|estoy trabajando|hoja de vida|perfil", re.I)
NAME = re.compile(r"^[^\\W\\d_]+(?:[ '-][^\\W\\d_]+){1,5}$", re.UNICODE)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--output-dir", default="/tmp")
    args = ap.parse_args()
    with open(args.input, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    approved = []
    for r in rows:
        if r.get("decision", "").strip().upper() != "APPROVE":
            continue
        name = " ".join(r.get("approved_name", "").split())
        if not (5 <= len(name) <= 80 and NAME.fullmatch(name) and not INVALID.search(name)):
            raise ValueError("Invalid verified name, candidate: " + r.get("candidate_id", "unknown"))
        if not r.get("reviewer", "").strip() or not r.get("evidence", "").strip() or not r.get("expected_current_name", "").strip():
            raise ValueError("Missing reviewer, evidence or previous name")
        UUID(r["candidate_id"])
        approved.append((r, name))
    ids = [r["candidate_id"] for r, _ in approved]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate candidate UUIDs")
    engine = create_engine(args.database_url)
    manifest = []
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            for r, name in approved:
                current = conn.execute(text("SELECT name FROM candidates WHERE id=:id FOR UPDATE"), {"id": r["candidate_id"]}).scalar_one_or_none()
                if current is None or current != r["expected_current_name"]:
                    raise ValueError("Missing or changed candidate UUID: " + r["candidate_id"])
                if current == name:
                    continue
                manifest.append({"candidate_id": r["candidate_id"], "old_name": current, "new_name": name, "reviewer": r["reviewer"], "evidence": r["evidence"]})
                if args.apply:
                    result = conn.execute(text("UPDATE candidates SET name=:new WHERE id=:id AND name=:old"), {"new": name, "id": r["candidate_id"], "old": current})
                    if result.rowcount != 1:
                        raise ValueError("Concurrent update conflict")
            if args.apply:
                target = Path(args.output_dir)
                target.mkdir(parents=True, exist_ok=True)
                path = target / ("name_changes_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ".json")
                with path.open("x", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)
                path.chmod(0o600)
                tx.commit()
                print("APPLIED:", len(manifest), "AUDIT:", path)
            else:
                tx.rollback()
                print("DRY_RUN:", len(manifest), "NOT_APPROVED:", len(rows)-len(approved), "DB_CHANGES: 0")
        except Exception:
            tx.rollback()
            raise

if __name__ == "__main__":
    main()
