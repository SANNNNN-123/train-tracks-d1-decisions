"""Audit parsed puzzles and independently check solver outputs; no training."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import json, time
from pathlib import Path
from collections import Counter
from track_solver import parse_puzzle_image, tracks

D = {'N':(-1,0,'S'),'S':(1,0,'N'),'E':(0,1,'W'),'W':(0,-1,'E')}
def check(data, grid):
    h,w=len(grid),len(grid[0])
    occupied={(r,c) for r in range(h) for c in range(w) if grid[r][c]}
    assert [sum(bool(x) for x in row) for row in grid]==data['rows'], 'Row counts'
    assert [sum(bool(grid[r][c]) for r in range(h)) for c in range(w)]==data['columns'], 'Column counts'
    expected=set()
    for shape,r,c,*_ in data['pieces']:
        r=h-1-r
        assert set(grid[r][c])==set(shape), 'Changed given'
        for direction in shape:
            dr,dc,_=D[direction]
            if not (0<=r+dr<h and 0<=c+dc<w): expected.add((r,c,direction))
    ports=set(); edges={p:[] for p in occupied}
    for r,c in occupied:
        assert grid[r][c] in {'NS','EW','NE','NW','SE','SW'}, 'Invalid track'
        for direction in grid[r][c]:
            dr,dc,opposite=D[direction]; nr,nc=r+dr,c+dc
            if not (0<=nr<h and 0<=nc<w): ports.add((r,c,direction))
            else:
                assert opposite in grid[nr][nc], 'Broken connection'
                edges[r,c].append((nr,nc))
    assert len(ports)==2 and ports==expected, 'Endpoints'
    seen=set(); todo=[next(iter(occupied))]
    while todo:
        p=todo.pop()
        if p not in seen: seen.add(p); todo.extend(edges[p])
    assert seen==occupied, 'Disconnected tracks or separate loops'

def main():
    root=Path(__file__).resolve().parents[2]
    paths=[root/r['path'] for r in __import__('csv').DictReader((root/'dataset-audit/inventory.csv').open())]
    results=[]; output=root/'dataset-audit/validation.jsonl'
    with output.open('w',encoding='utf-8') as f:
        for i,path in enumerate(paths,1):
            result={'path':path.relative_to(root).as_posix(),'status':'parse_error'}; start=time.monotonic()
            try:
                data,_=parse_puzzle_image(path); result['puzzle']=data
                result['status']='solve_error'; board=tracks.parse(data,graphical=False)
                original=board.move_from; deadline=time.monotonic()+10
                def bounded(cell,direction):
                    if board.move_count % 1000==0 and time.monotonic()>deadline: raise TimeoutError('10 second solve limit')
                    return original(cell,direction)
                board.move_from=bounded
                try: board.solve()
                except ValueError as e:
                    if str(e)!='Solved': raise
                grid=[[cell.track.name if cell.track else '' for cell in row] for row in reversed(board.layout)]
                result['status']='invalid_solution'; check(data,grid)
                result.update(status='validated',solution=grid,moves=board.move_count)
            except Exception as e: result['error']=f'{type(e).__name__}: {e}'
            result['seconds']=round(time.monotonic()-start,3); results.append(result)
            f.write(json.dumps(result)+'\n'); f.flush()
            if i%25==0: print(i,dict(Counter(r['status'] for r in results)),flush=True)
    summary={'total':len(results),'statuses':dict(Counter(r['status'] for r in results)),'failures':[{k:v for k,v in r.items() if k not in ('puzzle','solution')} for r in results if r['status']!='validated'],'limitations':['Solutions checked against extracted clues, not independently transcribed source clues.','Uniqueness has not been established.']}
    (root/'dataset-audit/validation-summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__': main()
