import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from collections import defaultdict
from audit_uniqueness import second_solution,canonical
from validate_puzzles import D,check
h=w=4; groups={}; found=None

def visit(path):
    global found
    r,c=path[-1]
    if (r,c)==(3,3):
        grid=[['']*w for _ in range(h)]
        for i,(rr,cc) in enumerate(path):
            ds=[]
            if i==0: ds.append('N')
            else:
                pr,pc=path[i-1]; ds.append(next(d for d,(dr,dc,_) in D.items() if (rr+dr,cc+dc)==(pr,pc)))
            if i==len(path)-1: ds.append('S')
            else:
                nr,nc=path[i+1];ds.append(next(d for d,(dr,dc,_) in D.items() if (rr+dr,cc+dc)==(nr,nc)))
            grid[rr][cc]=next(s for s in ['NS','EW','NE','NW','SE','SW'] if set(s)==set(ds))
        data={'rows':[sum(bool(s) for s in row) for row in grid],'columns':[sum(bool(grid[r][c]) for r in range(h)) for c in range(w)],'pieces':[[grid[0][0],3,0,'s'],[grid[3][3],0,3,'e']]}
        key=str(data)
        if key in groups and groups[key]!=grid: found={'puzzle':data,'solution':grid};return
        groups[key]=grid;return
    for dr,dc,_ in D.values():
        q=(r+dr,c+dc)
        if 0<=q[0]<h and 0<=q[1]<w and q not in path and found is None: visit(path+[q])
visit([(0,0)])
assert found is not None
check(found['puzzle'],found['solution'])
r=second_solution(found)
assert r['status']=='multiple',r
check(found['puzzle'],r['alternative'])
assert r['alternative']!=found['solution']
# Fix every occupied tile: this path must then be unique.
data=found['puzzle']; data['pieces']=[[s,h-1-r,c] for r,row in enumerate(found['solution']) for c,s in enumerate(row) if s]
assert second_solution(found)['status']=='unique'
print('Independent enumerator fixture: multiple solutions detected; fully fixed path unique.')
