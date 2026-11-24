"""Human audit of the derived ground-truth labels (answers "how good is the test set?").

Step 1 - build an audit page for 100 random held-out images (fixed seed):
    python -m evaluation.label_audit build --root ~/datasets/sh17 --n 100
    open evaluation/data/label_audit.html          # works offline in any browser

For each photo the auditor directly selects the visible PPE status, then uses
"Download CSV", and saves it as evaluation/data/label_audit_results.csv.

Step 2 - score the audit:
    python -m evaluation.label_audit score

Reports per-hazard label accuracy with 95% Wilson intervals and Cohen's kappa
between the dataset-derived labels and the auditor. A single auditor cannot
measure inter-annotator agreement among *new* annotations (that needs >= 3
people); this audit instead measures agreement between the published dataset
labels and an independent domain expert.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import random
from pathlib import Path

from PIL import Image

from .metrics import cohen_kappa, wilson_ci
from .sh17 import HAZARDS, find_layout, gt_hazards, label_path, read_boxes

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"
SHOW = {
    "head": "#e8710a",
    "helmet": "#2e7d32",
    "person": "#1f3a5f",
    "hands": "#c62828",
    "gloves": "#00897b",
    "face": "#795548",
    "glasses": "#0277bd",
    "face-guard": "#0277bd",
}
# First choice: present on everyone visible. Second: missing on at least one.
CHOICES = {
    "no_hard_hat": ("Hard hat", "No hard hat"),
    "no_eye_protection": ("Glasses", "No glasses"),
    "no_gloves": ("Gloves", "No gloves"),
}


def thumb_b64(path: Path, side: int = 640) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((side, side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def build(root: str, n: int, seed: int) -> None:
    lay = find_layout(root)
    manifest = DATA / "sh17_test_manifest.csv"
    with manifest.open() as f:
        images = [r["image"] for r in csv.DictReader(f)]
    picks = random.Random(seed).sample(images, min(n, len(images)))
    items = []
    for name in picks:
        boxes = read_boxes(label_path(lay, name))
        items.append(
            {
                "image": name,
                "src": thumb_b64(lay.images / name),
                "gt": gt_hazards(boxes),
                "boxes": [
                    {"l": b.label, "x": b.x1, "y": b.y1, "w": b.x2 - b.x1, "h": b.y2 - b.y1}
                    for b in boxes
                    if b.label in SHOW
                ],
            }
        )
    html = (
        TEMPLATE.replace("__DATA__", json.dumps(items))
        .replace("__COLORS__", json.dumps(SHOW))
        .replace("__Q__", json.dumps(CHOICES))
        .replace("__HAZ__", json.dumps(HAZARDS))
    )
    out = DATA / "label_audit.html"
    out.write_text(html)
    print(f"Wrote {out} with {len(items)} images (seed {seed}). Open it in a browser.")


def score() -> None:
    path = DATA / "label_audit_results.csv"
    if not path.is_file():
        raise SystemExit(f"Save the CSV downloaded from the audit page as {path}")
    with path.open() as f:
        rows = list(csv.DictReader(f))
    out = {"images": len({r["image"] for r in rows}), "hazards": {}}
    for h in CHOICES:
        rs = [r for r in rows if r["hazard"] == h and r["verdict"] in ("agree", "disagree")]
        derived = [r["derived"] == "1" for r in rs]
        expert = [d if r["verdict"] == "agree" else not d for d, r in zip(derived, rs, strict=True)]
        agree = sum(r["verdict"] == "agree" for r in rs)
        fp = sum(1 for d, e in zip(derived, expert, strict=True) if d and not e)  # label says hazard, expert says no
        fn = sum(1 for d, e in zip(derived, expert, strict=True) if not d and e)  # label missed a hazard
        out["hazards"][h] = {
            "n": len(rs),
            "agree": agree,
            "accuracy": agree / len(rs) if rs else None,
            "accuracy_ci95": wilson_ci(agree, len(rs)),
            "kappa": cohen_kappa(derived, expert),
            "false_positive_labels": fp,
            "missed_hazard_labels": fn,
        }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "label_audit.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><title>SH17 photo audit</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font:15px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f4f6f8;color:#1d2733}
header{position:sticky;top:0;background:#1f3a5f;color:#fff;padding:10px 16px;display:flex;gap:16px;align-items:center;z-index:9}
button{font:inherit;border-radius:6px;border:1px solid #c5cdd6;background:#fff;padding:6px 12px;cursor:pointer}
button.on{background:#1f3a5f;color:#fff;border-color:#1f3a5f}
.item{display:grid;grid-template-columns:minmax(0,640px) 1fr;gap:16px;background:#fff;margin:14px;padding:14px;border-radius:10px;border:1px solid #dde2e8}
@media(max-width:900px){.item{grid-template-columns:1fr}}
.wrap{position:relative} .wrap img{width:100%;display:block;border-radius:6px} .wrap svg{position:absolute;inset:0;width:100%;height:100%}
.q{border:1px solid #dde2e8;border-radius:8px;padding:10px;margin:8px 0} .tag{font-weight:700;padding:1px 8px;border-radius:5px}
.yes{background:#fde3d0;color:#8a3b00} .no{background:#e6f4e7;color:#1f5f22} .legend span{margin-right:10px;font-size:13px}
</style></head><body>
<header><strong>SH17 photo audit</strong><span id="prog"></span><button id="dl">Download CSV</button>
<label style="font-size:13px"><input type="checkbox" id="boxes" checked> show boxes</label></header>
<p style="margin:14px">Pick what you see. If anyone is missing an item, choose “No”. Can’t tell? Skip it. Goggles and face shields count as glasses.
Answers are kept in this browser tab only, so download the CSV when finished (or periodically).</p>
<div id="list"></div>
<script>
const DATA=__DATA__, COLORS=__COLORS__, choices=__Q__, HAZ=__HAZ__; const ans={};
try{Object.assign(ans, JSON.parse(localStorage.getItem('sh17audit')||'{}'))}catch(e){}
const list=document.getElementById('list');
function save(){try{localStorage.setItem('sh17audit',JSON.stringify(ans))}catch(e){} prog()}
const activeHazards = Object.keys(choices);
function prog(){const total=DATA.length*activeHazards.length;
 const done=DATA.reduce((count,it)=>count+activeHazards.filter(h=>ans[it.image+'|'+h]).length,0);document.getElementById('prog').textContent=`${done}/${total} answered`}
DATA.forEach((it,i)=>{const d=document.createElement('div');d.className='item';
 const rects=it.boxes.map(b=>`<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" fill="none" stroke="${COLORS[b.l]}" style="stroke-width:2px" vector-effect="non-scaling-stroke"><title>${b.l}</title></rect>`).join('');
 d.innerHTML=`<div class="wrap"><img src="data:image/jpeg;base64,${it.src}"><svg class="bx" viewBox="0 0 1 1" preserveAspectRatio="none">${rects}</svg></div>
 <div><div class="small">#${i+1} · ${it.image}</div><div class="legend">${Object.entries(COLORS).map(([k,v])=>`<span style="color:${v}">■ ${k}</span>`).join('')}</div>
 ${activeHazards.map(h => {
   const key = it.image + '|' + h;
   const buttons = choices[h].map((label, index) => {
     const missing = index === 1;
     const verdict = missing === it.gt[h] ? 'agree' : 'disagree';
     const selected = ans[key] === verdict;
     return `<button class="${selected ? 'on' : ''}" aria-pressed="${selected}" data-k="${key}" data-v="${verdict}">${label}</button>`;
   });
   return `<div class="q">${buttons.join(' ')}</div>`;
 }).join('')}</div>`;
 list.appendChild(d)});
list.addEventListener('click',e=>{const b=e.target.closest('button[data-k]');if(!b)return;ans[b.dataset.k]=b.dataset.v;
 b.parentElement.querySelectorAll('button').forEach(x=>{x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',String(x===b))});save()});
document.getElementById('boxes').addEventListener('change',e=>document.querySelectorAll('svg.bx').forEach(s=>s.style.display=e.target.checked?'':'none'));
document.getElementById('dl').onclick=()=>{const rows=['image,hazard,derived,verdict'];
 DATA.forEach(it=>HAZ.forEach(h=>rows.push(`${it.image},${h},${it.gt[h]?1:0},${ans[it.image+'|'+h]||''}`)));
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([rows.join('\n')],{type:'text/csv'}));a.download='label_audit_results.csv';a.click()};
prog();
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--root", required=True)
    b.add_argument("--n", type=int, default=100)
    b.add_argument("--seed", type=int, default=7)
    sub.add_parser("score")
    args = ap.parse_args()
    build(args.root, args.n, args.seed) if args.cmd == "build" else score()


if __name__ == "__main__":
    main()
