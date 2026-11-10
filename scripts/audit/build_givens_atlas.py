import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import json, sys
from pathlib import Path
from collections import Counter
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from track_solver import _grid_lines

def main():
    audit=ROOT/'dataset-audit'
    records=[json.loads(x) for x in (audit/'validated-puzzles.jsonl').read_text().splitlines()]
    entries=[]
    for rec in records:
        path=ROOT/rec['path']; img=cv2.imread(str(path))
        if img is None: raise ValueError(f"Unreadable {path}")
        h,w=img.shape[:2]; gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY); dark=(gray<85).astype(np.uint8)
        xs=_grid_lines(dark.sum(0),h*.60); ys=_grid_lines(dark.sum(1),w*.60)
        for piece in rec['puzzle']['pieces']:
            dirs,sr,c,*_=piece; ir=len(ys)-2-sr
            x0,x1=xs[c],xs[c+1];y0,y1=ys[ir],ys[ir+1]
            crop=cv2.cvtColor(cv2.resize(img[y0:y1,x0:x1],(96,96),interpolation=cv2.INTER_CUBIC),cv2.COLOR_BGR2RGB)
            entries.append((rec['path'],ir+1,c+1,dirs,Image.fromarray(crop)))
    per_page=180; cols=10; cellw=170; cellh=135
    pages=[]
    for pi,start in enumerate(range(0,len(entries),per_page),1):
        page=entries[start:start+per_page]; out=Image.new('RGB',(cols*cellw,((len(page)+cols-1)//cols)*cellh),'white'); draw=ImageDraw.Draw(out)
        for j,(path,row,col,shape,crop) in enumerate(page):
            x=(j%cols)*cellw;y=(j//cols)*cellh;out.paste(crop,(x+35,y))
            draw.text((x+3,y+98),f'{start+j}: {shape} at r{row} c{col}',fill='black')
            draw.text((x+3,y+115),Path(path).name,fill='black')
        dest=audit/f'givens-atlas-{pi:02}.jpg';out.save(dest,quality=92);pages.append(dest.name)
    index={'total_given_pieces':len(entries),'pages':pages,'entries':[{'index':i,'path':p,'image_row':r,'column':c,'extracted_shape':s} for i,(p,r,c,s,_) in enumerate(entries)]}
    (audit/'givens-atlas-index.json').write_text(json.dumps(index,indent=2))
    print(json.dumps({'given_pieces':len(entries),'pages':pages,'shape_counts':dict(Counter(e[3] for e in entries))},indent=2))
if __name__=='__main__':main()
