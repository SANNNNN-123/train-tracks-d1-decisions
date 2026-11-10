import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import json,time,sys
from pathlib import Path
from track_solver import parse_puzzle_image, tracks
from validate_puzzles import check
p=Path(sys.argv[1]); data,_=parse_puzzle_image(p)
b=tracks.parse(data,graphical=False); b.move_max=10000000
start=time.monotonic(); original=b.move_from

def bounded(cell,direction):
    if b.move_count%1000==0 and time.monotonic()-start>120: raise TimeoutError('120 second limit')
    return original(cell,direction)
b.move_from=bounded
r={'path':p.as_posix(),'puzzle':data,'status':'solve_error'}
try:
    try: b.solve()
    except ValueError as e:
        if str(e)!='Solved': raise
    grid=[[c.track.name if c.track else '' for c in row] for row in reversed(b.layout)]
    check(data,grid); r.update(status='validated',solution=grid,moves=b.move_count)
except Exception as e: r['error']=str(e)
r['seconds']=round(time.monotonic()-start,3)
Path('dataset-audit/retry-' + p.stem + '.json').write_text(json.dumps(r,indent=2))
print(r['status'],r.get('error'),r['seconds'],flush=True)

