#!/usr/bin/env python3
import csv
import re
import subprocess
from pathlib import Path
from uuid import UUID

source=Path('/home/ubuntu/adn360-name-audit/name_final_review_PRIVATE.csv')
with source.open(encoding='utf-8-sig',newline='') as f:
    rows=[r for r in csv.DictReader(f) if r['review_tier']=='PRIORITY_VISUAL_CONFIRMATION']
if len(rows)!=43: raise SystemExit('Expected 43 names')
print('READY',len(rows),'No DB updates')
