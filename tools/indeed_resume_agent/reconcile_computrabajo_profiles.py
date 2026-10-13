"""Read-only identity reconciliation against signed-in Computrabajo browser.

Requires the existing interactive agent session on Windows, not Lightsail.
Input CSV: candidate_id,external_id,current_name.
No database writes and no CV downloads.
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import Counter
from pathlib import Path
from uuid import UUID

from .computrabajo_browser import ComputrabajoBrowserUse, valid_computrabajo_candidate_name
from .config import load_config


def run(input_path: str, output_path: str, max_pages: int) -> None:
    with open(input_path, newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    required = {"candidate_id", "external_id", "current_name"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Expected CSV columns: candidate_id,external_id,current_name")
    targets = {}
    for row in rows:
        UUID(row["candidate_id"])
        key = row["external_id"].strip().casefold()
        if not key or key in targets:
            raise ValueError("Missing or duplicated external_id in input")
        targets[key] = row
    browser = ComputrabajoBrowserUse(load_config())
    try:
        discovered = browser.discover_all_candidates(max_pages=max_pages)
        provider = {}
        for item in discovered.get("candidates", []):
            key = str(item.get("external_id") or "").strip().casefold()
            if key:
                provider.setdefault(key, []).append(item)
        results = []
        for key, row in targets.items():
            matches = provider.get(key, [])
            name, status, evidence = "", "NOT_FOUND", ""
            if len(matches) > 1:
                status = "DUPLICATE_PROVIDER_ID"
            elif len(matches) == 1:
                try:
                    name = browser.read_candidate_profile_name(matches[0]["detail_url"])
                    if valid_computrabajo_candidate_name(name):
                        status, evidence = "REVIEW_PROFILE_NAME", "authenticated_profile_h1"
                    else:
                        name, status = "", "INVALID_PROFILE_NAME"
                except (ValueError, RuntimeError, TimeoutError) as exc:
                    status = "PROFILE_ERROR"
                    evidence = type(exc).__name__
            results.append({
                "candidate_id":row["candidate_id"],
                "external_id":row["external_id"],
                "current_name":row["current_name"],
                "suggested_name":name,
                "status":status,
                "evidence":evidence,
                "decision":"PENDING_REVIEW",
            })
        dest = Path(output_path)
        dest.parent.mkdir(parents=True,exist_ok=True)
        fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd,"w",encoding="utf-8",newline="") as stream:
            writer = csv.DictWriter(stream,fieldnames=list(results[0]))
            writer.writeheader()
            writer.writerows(results)
        print("TARGETS",len(targets),"DISCOVERED",len(provider),"PARTIAL",discovered.get("partial"))
        print("RESULTS",dict(Counter(r["status"] for r in results)))
        print("REPORT",dest,"DB_UPDATES",0)
    finally:
        browser.close()


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--max-pages",type=int,default=500)
    args=parser.parse_args()
    run(args.input,args.output,args.max_pages)


if __name__=="__main__":
    main()
