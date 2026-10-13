"""Generate a PRIVATE offline HTML review of CV identities.

Run in the API container with an AWS profile. This exports only the 43
PRIORITY_VISUAL_CONFIRMATION cases into a self-contained HTML file.
Reviewers record decisions in browser and download a CSV locally.
No HTTP server, upload, database mutation or automatic approvals.
"""
import argparse
import base64
import csv
import html
import json
import os
from pathlib import Path
from uuid import UUID

import boto3
import pymupdf

BUCKET = "ai-recruiter-cv-890876258895-us-east-2"

PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ADN360 | Revisión de nombres</title><style>
body{font:15px system-ui;background:#f4f6fa;color:#182536;margin:0}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #dce2e9;padding:14px 24px;display:flex;align-items:center;gap:20px;z-index:2}
h1{font-size:21px;margin:0}button{background:#143d64;color:white;border:0;border-radius:8px;padding:10px 14px;cursor:pointer}
button.secondary{background:#dbe5ee;color:#15334d}
main{max-width:1160px;margin:24px auto;padding:0 16px}
article{background:white;border:1px solid #dce2e9;border-radius:12px;padding:18px;display:grid;grid-template-columns:minmax(300px,1fr) minmax(280px,0.85fr);gap:24px;margin-bottom:18px}
img{display:block;width:100%;height:auto;border:1px solid #ddd;border-radius:6px}
label{display:block;margin-top:12px;font-size:13px;color:#526171}
input,textarea,select{box-sizing:border-box;width:100%;padding:10px;border:1px solid #cbd5e1;border-radius:6px;font:inherit}
textarea{min-height:76px}
.meta{font-size:12px;word-break:break-all;color:#5a697b}
.note{color:#8b5317;background:#fff5dc;padding:10px;border-radius:7px}
@media(max-width:740px){article{grid-template-columns:1fr}}
</style></head><body><header><h1>ADN360 · Validación visual</h1><span id="status"></span>
<button id="export">Exportar decisiones CSV</button></header><main id="cases"></main>
<script id="data" type="application/json">__DATA__</script><script>
const records=JSON.parse(document.getElementById('data').textContent);
const root=document.getElementById('cases');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
records.forEach((r,i)=>{
 const a=document.createElement('article');
 a.innerHTML='<div><img loading="lazy" alt="Primera página del CV" src="data:image/jpeg;base64,'+r.image+'"></div><div>'+
 '<div class="meta">Caso '+(i+1)+' de '+records.length+' · '+esc(r.candidate_id)+'</div>'+
 '<label>Nombre actual</label><input readonly value="'+esc(r.current_name)+'">'+
 '<label>Propuesta de Bedrock</label><input readonly value="'+esc(r.suggested_name)+'">'+
 '<label>Evidencia devuelta</label><textarea readonly>'+esc(r.evidence)+'</textarea>'+
 '<p class="note">Verifica que sea el titular del CV, no un reclutador, contacto o referencia.</p>'+
 '<label>Nombre aprobado (editar si es necesario)</label><input class="approved" value="'+esc(r.suggested_name)+'">'+
 '<label>Decisión</label><select class="decision"><option value="PENDING_REVIEW">Pendiente</option><option value="APPROVE">Aprobar</option><option value="REJECT">Rechazar</option></select>'+
 '<label>Revisor</label><input class="reviewer" placeholder="Nombre o identificador del revisor">'+
 '<label>Observaciones / fundamento</label><textarea class="comments" placeholder="Describe la evidencia visual"></textarea></div>';
 root.appendChild(a);
});
const update=()=>document.getElementById('status').textContent=Array.from(document.querySelectorAll('.decision')).filter(e=>e.value!=='PENDING_REVIEW').length+' / '+records.length+' revisados';
document.addEventListener('change',update);
document.getElementById('export').addEventListener('click',()=>{
 const fields=['candidate_id','expected_current_name','approved_name','reviewer','evidence','decision','comments'];
 const quote=s=>'"'+String(s??'').replace(/"/g,'""')+'"';
 const lines=[fields.map(quote).join(',')];
 Array.from(root.children).forEach((a,i)=>{
  const r=records[i],q=s=>a.querySelector(s).value.trim();
  const decision=q('.decision'),reviewer=q('.reviewer'),approved=q('.approved'),comments=q('.comments');
  if(decision==='APPROVE'&&(!reviewer||!approved||!comments)){alert('Caso '+(i+1)+': completa revisor, nombre y fundamento.');throw Error('Incomplete review');}
  lines.push([r.candidate_id,r.current_name,decision==='APPROVE'?approved:'',reviewer,r.evidence,decision,comments].map(quote).join(','));
 });
 const blob=new Blob(['\\ufeff'+lines.join('\\r\\n')],{type:'text/csv;charset=utf-8'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='adn360_approved_name_reviews_PRIVATE.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
update();
</script></body></html>"""

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--input",required=True)
 p.add_argument("--output",required=True)
 p.add_argument("--profile",default="ai-recruiter-bedrock")
 args=p.parse_args()
 with open(args.input,encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
 selected=[r for r in rows if r.get("review_tier")=="PRIORITY_VISUAL_CONFIRMATION"]
 if not selected: raise ValueError("No priority cases")
 s3=boto3.Session(profile_name=args.profile,region_name="us-east-2").client("s3")
 data=[]
 for idx,r in enumerate(selected,1):
  cid=str(UUID(r["candidate_id"]))
  raw=s3.get_object(Bucket=BUCKET,Key=f"documents/cv-{cid}.pdf")["Body"].read()
  with pymupdf.open(stream=raw,filetype="pdf") as pdf:
   page=pdf[0]
   scale=min(1.6,1200/max(float(page.rect.width),float(page.rect.height),1))
   jpg=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False).tobytes("jpeg",jpg_quality=75)
  data.append({"candidate_id":cid,"current_name":r["expected_current_name"],"suggested_name":r["suggested_name"],"evidence":r["evidence"],"image":base64.b64encode(jpg).decode("ascii")})
  if idx%10==0: print("RENDERED",idx,flush=True)
 target=Path(args.output)
 target.parent.mkdir(parents=True,exist_ok=True)
 safe=json.dumps(data,ensure_ascii=False).replace("<","\\u003c")
 fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,"w",encoding="utf-8") as f:f.write(PAGE.replace("__DATA__",safe))
 print("READY",len(data),"PRIVATE_HTML",target,"DATABASE_UPDATES",0)
if __name__=="__main__":main()
