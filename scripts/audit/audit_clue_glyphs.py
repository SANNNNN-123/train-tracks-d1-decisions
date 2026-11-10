import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import json,hashlib
from pathlib import Path
from collections import defaultdict
import cv2,numpy as np
from PIL import Image,ImageDraw
from track_solver import _grid_lines
p=Path('dataset-audit'); groups={}
for line in (p/'validated-puzzles.jsonl').read_text().splitlines():
    r=json.loads(line); gray=cv2.imread(r['path'],cv2.IMREAD_GRAYSCALE); h,w=gray.shape
    dark=(gray<85).astype(np.uint8); xs=_grid_lines(dark.sum(0),h*.60); ys=_grid_lines(dark.sum(1),w*.60)
    top=max(0,ys[0]-int((ys[1]-ys[0])*.96)); right=min(w,xs[-1]+int((xs[1]-xs[0])*.98))
    crops=[('column',i,gray[top:ys[0]-2,xs[i]+2:xs[i+1]-2],n) for i,n in enumerate(r['puzzle']['columns'])]+[('row',i,gray[ys[i]+2:ys[i+1]-2,xs[-1]+2:right],n) for i,n in enumerate(r['puzzle']['rows'])]
    for axis,i,crop,n in crops:
        # Group exact binary glyphs; no font template or OCR is used here.
        mask=(crop<135).astype(np.uint8); points=cv2.findNonZero(mask); x,y,ww,hh=cv2.boundingRect(points); glyph=mask[y:y+hh,x:x+ww]
        key=hashlib.sha256(str(glyph.shape).encode()+glyph.tobytes()).hexdigest()
        if key not in groups: groups[key]={'glyph':glyph,'labels':set(),'refs':[]}
        groups[key]['labels'].add(n);groups[key]['refs'].append([r['path'],axis,i+1])
ordered=sorted(groups.items(),key=lambda kv:(min(kv[1]['labels']),kv[0]))
print('Exact glyph groups:',len(ordered),'conflicts:',sum(len(g['labels'])>1 for _,g in ordered))
manifest=[]
for page,start in enumerate(range(0,len(ordered),120),1):
    subset=ordered[start:start+120]; canvas=Image.new('RGB',(1200,((len(subset)+11)//12)*95),'white'); draw=ImageDraw.Draw(canvas)
    for j,(key,g) in enumerate(subset):
        x=(j%12)*100;y=(j//12)*95
        im=Image.fromarray((255-g['glyph']*255).astype('uint8')).convert('RGB');im.thumbnail((65,58));canvas.paste(im,(x+10,y+3))
        draw.text((x+3,y+62),f"#{start+j} = {','.join(map(str,sorted(g['labels'])))}",fill='black')
        draw.text((x+3,y+77),f"n={len(g['refs'])}",fill='black')
        manifest.append({'index':start+j,'hash':key,'labels':sorted(g['labels']),'references':g['refs'],'page':page})
    canvas.save(p/f'clue-atlas-{page}.png')
(p/'clue-groups.json').write_text(json.dumps(manifest))
