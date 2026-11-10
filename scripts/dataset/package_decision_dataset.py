import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import json,io,csv
from pathlib import Path
from collections import Counter
from PIL import Image as PILImage,ImageDraw
import cv2,numpy as np
from datasets import Dataset,Features,Image,List,Value
from track_solver import _grid_lines
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'decision-dataset'; HUB=OUT/'huggingface';HUB.mkdir(exist_ok=True)
records=[json.loads(x) for x in (OUT/'records.jsonl').read_text().splitlines()]
solutions={Path(x['path']).stem:x for x in map(json.loads,(ROOT/'dataset-audit/validated-puzzles.jsonl').read_text().splitlines())}
splits={r['puzzle_id']:r['split'] for r in csv.DictReader((ROOT/'dataset-audit/puzzle-splits.csv').open())}
seen=set();cache={};counts=Counter()
RULES='Connect the two boundary endpoints with one continuous track. Preserve given pieces. Each clue counts occupied cells in its row or column. Tracks must connect reciprocally, cannot branch or cross, and cannot form separate loops. Blue tracks are givens; black tracks are previous placements; X means confirmed empty; blank means unassigned; amber outlines the target. Coordinates are printed on the left and bottom.'

def rows_for(split):
    for row in records:
        if row['split']!=split:continue
        pid=row['puzzle_id'];record=solutions[pid];p=record['puzzle'];sol=record['solution'];h=len(sol);w=len(sol[0])
        givens={(h-1-r,c) for s,r,c,*_ in p['pieces']};unknown=[(r,c) for r in range(h) for c in range(w) if (r,c) not in givens]
        step=row['step_index'];r,c=unknown[step]
        assert row['id'] not in seen;seen.add(row['id'])
        assert splits[pid]==split and row['label']==(sol[r][c] or 'empty')
        assert row['state']['target_cell']=={'row':r+1,'column':c+1}
        expected=[{'row':rr+1,'column':cc+1,'value':sol[rr][cc] or 'empty'} for rr,cc in unknown[:step]]
        assert row['state']['past_actions']==expected
        if pid not in cache:
            raw=cv2.imread(str(ROOT/record['path']));gray=cv2.cvtColor(raw,cv2.COLOR_BGR2GRAY);dark=(gray<85).astype(np.uint8)
            cache[pid]=(_grid_lines(dark.sum(0),raw.shape[0]*.60),_grid_lines(dark.sum(1),raw.shape[1]*.60))
        xs,ys=cache[pid]
        with PILImage.open(OUT/row['images'][0]) as src:im=src.convert('RGB')
        d=ImageDraw.Draw(im)
        for a in expected:
            if a['value']=='empty':
                rr,cc=a['row']-1,a['column']-1;cx=(xs[cc]+xs[cc+1])//2;cy=(ys[rr]+ys[rr+1])//2
                d.line((cx-6,cy-6,cx+6,cy+6),fill='#555555',width=2);d.line((cx-6,cy+6,cx+6,cy-6),fill='#555555',width=2)
        canvas=PILImage.new('RGB',(im.width+30,im.height+30),'white');canvas.paste(im,(30,0));d=ImageDraw.Draw(canvas)
        for rr in range(h):d.text((3,(ys[rr]+ys[rr+1])//2-6),str(rr+1),fill='#2463a5')
        for cc in range(w):d.text((30+(xs[cc]+xs[cc+1])//2-3,im.height+5),str(cc+1),fill='#2463a5')
        b=io.BytesIO();canvas.save(b,format='PNG')
        row=dict(row);row['state']=dict(row['state'],task=RULES);row['images']=[{'bytes':b.getvalue(),'path':None}]
        counts[split]+=1
        if counts[split]%2000==0:print(split,counts[split],flush=True)
        yield row

for split in ['train','validation','test_small','test_medium']:
    ds=Dataset.from_generator(rows_for,gen_kwargs={'split':split},cache_dir=str(OUT/'export-cache'))
    ds=ds.cast_column('images',List(Image()))
    # The image bytes are embedded, so the upload does not depend on local file paths.
    dest=HUB/'data'/f'{split}.parquet';dest.parent.mkdir(exist_ok=True)
    ds.to_parquet(str(dest));print('saved',split,len(ds),flush=True)
assert len(seen)==41761
summary={'rows':len(seen),'split_rows':dict(counts),'puzzles':608,'validation':'All IDs, labels, target cells, teacher histories, split assignments and PNG decodes checked; image bytes embedded.'}
(HUB/'validation.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))
