import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pathlib import Path
from collections import Counter, defaultdict
import csv, hashlib, json, re
import cv2
import numpy as np
from track_solver import _grid_lines
root = Path.cwd()
rows = []
hashes = defaultdict(list)
for path in sorted((root / 'assets').rglob('*.png')):
    match = re.fullmatch(r'(\d{8})-(small|medium)', path.stem)
    if not match:
        continue
    row = dict(path=path.relative_to(root).as_posix(), date=match[1], size=match[2], rows='', columns='', pixel_hash='', error='')
    try:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError('Unreadable PNG')
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h,w = gray.shape
        dark = (gray < 85).astype(np.uint8)
        xs = _grid_lines(dark.sum(axis=0), h*.60)
        ys = _grid_lines(dark.sum(axis=1), w*.60)
        if min(len(xs),len(ys)) < 3:
            raise ValueError('Grid detection failed')
        for lines in (xs,ys):
            gaps = np.diff(lines)
            if np.max(np.abs(gaps-np.median(gaps))) > max(2,np.median(gaps)*.12):
                raise ValueError('Uneven grid lines')
        row.update(rows=len(ys)-1, columns=len(xs)-1, pixel_hash=hashlib.sha256(str(image.shape).encode()+image.tobytes()).hexdigest())
        hashes[row['pixel_hash']].append(row['path'])
    except Exception as e:
        row['error'] = str(e)
    rows.append(row)
out = root / 'dataset-audit'
out.mkdir(exist_ok=True)
with (out/'inventory.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
summary = {'total':len(rows), 'sizes':dict(Counter(r['size'] for r in rows)), 'dimensions':dict(Counter(f"{r['size']}: {r['rows']}x{r['columns']}" for r in rows)), 'months':dict(Counter(r['path'].split('/')[1] for r in rows)), 'errors':[r for r in rows if r['error']], 'pixel_duplicate_groups':[v for v in hashes.values() if len(v)>1]}
(out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
