"""Render pre-decision board images and build puzzle-level HF split datasets."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import csv, json, hashlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'dataset-audit'
OUT=ROOT/'decision-dataset'
SHAPES=['NS','EW','NE','NW','SE','SW']

def draw_piece(draw, box, shape, color):
    x0,y0,x1,y1=box; cx=(x0+x1)//2;cy=(y0+y1)//2
    ports={'N':(cx,y0),'S':(cx,y1),'W':(x0,cy),'E':(x1,cy)}
    for d in shape:
        draw.line((cx,cy,*ports[d]),fill=color,width=max(3,(x1-x0)//22))

def main():
    splits={r['path']:r for r in csv.DictReader((AUDIT/'puzzle-splits.csv').open(encoding='utf-8'))}
    records=[json.loads(x) for x in (AUDIT/'validated-puzzles.jsonl').read_text().splitlines()]
    manifest=[];counts={}
    for record in records:
        rel=record['path']; meta=splits[rel]; src=ROOT/rel
        img=Image.open(src).convert('RGB'); raw=cv2.imread(str(src)); gray=cv2.cvtColor(raw,cv2.COLOR_BGR2GRAY);dark=(gray<85).astype(np.uint8)
        from track_solver import _grid_lines
        xs=_grid_lines(dark.sum(0),raw.shape[0]*.60);ys=_grid_lines(dark.sum(1),raw.shape[1]*.60)
        h,w=int(meta['rows']),int(meta['columns']); solution=record['solution']; givens={(h-1-r,c):s for s,r,c,*_ in record['puzzle']['pieces']}
        unknown=[(r,c) for r in range(h) for c in range(w) if (r,c) not in givens]
        puzzle_id=meta['puzzle_id']; folder=OUT/'images'/meta['split']/puzzle_id;folder.mkdir(parents=True,exist_ok=True)
        # Precompute cell rectangles and preserve the original grid/clues.
        boxes={(r,c):(xs[c],ys[r],xs[c+1],ys[r+1]) for r in range(h) for c in range(w)}
        actions=[]
        for step,(r,c) in enumerate(unknown):
            board=img.copy();d=ImageDraw.Draw(board)
            # Hide all puzzle pieces, then redraw givens and only prior correct actions.
            for rr in range(h):
                for cc in range(w):
                    x0,y0,x1,y1=boxes[rr,cc];d.rectangle((x0+2,y0+2,x1-2,y1-2),fill='white')
            for rr in range(h):
                for cc in range(w):
                    x0,y0,x1,y1=boxes[rr,cc];d.rectangle((x0,y0,x1,y1),outline='#666',width=1)
            for (rr,cc),shape in givens.items(): draw_piece(d,boxes[rr,cc],shape,'#2463a5')
            for pr,pc in unknown[:step]: draw_piece(d,boxes[pr,pc],solution[pr][pc],'#222222')
            # Mark target cell in amber without encoding its answer.
            x0,y0,x1,y1=boxes[r,c];d.rectangle((x0+2,y0+2,x1-2,y1-2),outline='#e69500',width=3)
            path=folder/f'{step:03}_{r+1:02}_{c+1:02}.png';board.save(path,optimize=True)
            answer=solution[r][c] or 'empty';row_id=f'{puzzle_id}-r{r+1:02}-c{c+1:02}'
            state={'task':'Complete one continuous track satisfying every row and column clue.','coordinates':'Rows top to bottom; columns left to right; both start at 1. Track shapes name connected sides N/E/S/W.','rows':h,'columns':w,'target_cell':{'row':r+1,'column':c+1},'past_actions':actions.copy()}
            question={'type':'choice','instructions':'Which track shape belongs in the target cell? Choose empty or the connected sides.','criteria':{'empty':'No track','NS':'Track connects north and south','EW':'Track connects east and west','NE':'Track connects north and east','NW':'Track connects north and west','SE':'Track connects south and east','SW':'Track connects south and west'}}
            manifest.append({'id':row_id,'puzzle_id':puzzle_id,'step_index':step,'images':[str(path.relative_to(OUT)).replace('\\','/')],'state':state,'question':question,'label':answer,'difficulty':meta['difficulty'],'rows':h,'columns':w,'source_date':f'{meta["date"][4:8]}-{meta["date"][2:4]}-{meta["date"][:2]}','split':meta['split']})
            actions.append({'row':r+1,'column':c+1,'value':answer})
        counts[meta['split']]=counts.get(meta['split'],0)+len(unknown)
    OUT.mkdir(exist_ok=True)
    (OUT/'records.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in manifest),encoding='utf-8')
    (OUT/'dataset-summary.json').write_text(json.dumps({'rows':len(manifest),'decision_images':len(manifest),'split_rows':counts,'puzzles':len(records),'image_format':'PNG','image_paths_relative_to_dataset_root':True},indent=2))
    print(json.dumps({'rows':len(manifest),'split_rows':counts,'puzzles':len(records)},indent=2))
if __name__=='__main__':main()

