"""Independent MILP search for a second solution, plus symmetry duplicate audit."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import json,time
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import coo_matrix
from validate_puzzles import check,D
SHAPES=['','NS','EW','NE','NW','SE','SW']

def second_solution(record, seconds=60):
    data=record['puzzle']; known=record['solution']; h,w=len(known),len(known[0]); n=h*w*7
    def ix(r,c,s): return (r*w+c)*7+s
    lower=np.zeros(n); upper=np.ones(n)
    givens={(h-1-r,c):shape for shape,r,c,*_ in data['pieces']}
    terms=[]; lows=[]; highs=[]
    def add(items,lo,hi): terms.append(items); lows.append(lo); highs.append(hi)
    for r in range(h):
        for c in range(w):
            add([(ix(r,c,s),1) for s in range(7)],1,1)
            for s,shape in enumerate(SHAPES):
                if (r,c) in givens and set(shape)!=set(givens[r,c]): upper[ix(r,c,s)]=0
                for d in shape:
                    dr,dc,_=D[d]
                    if not (0<=r+dr<h and 0<=c+dc<w) and d not in givens.get((r,c),''):
                        upper[ix(r,c,s)]=0
            for d in ['S','E']:
                dr,dc,opp=D[d]; nr,nc=r+dr,c+dc
                if nr<h and nc<w:
                    add([(ix(r,c,s),1) for s,shape in enumerate(SHAPES) if d in shape]+[(ix(nr,nc,s),-1) for s,shape in enumerate(SHAPES) if opp in shape],0,0)
    for r,count in enumerate(data['rows']): add([(ix(r,c,s),1) for c in range(w) for s in range(1,7)],count,count)
    for c,count in enumerate(data['columns']): add([(ix(r,c,s),1) for r in range(h) for s in range(1,7)],count,count)
    add([(ix(r,c,SHAPES.index(known[r][c])),1) for r in range(h) for c in range(w)],-np.inf,h*w-1)
    start=time.monotonic(); cuts=0
    while time.monotonic()-start<seconds:
        rr=[];cc=[];vv=[]
        for i,term in enumerate(terms):
            for j,v in term: rr.append(i);cc.append(j);vv.append(v)
        matrix=coo_matrix((vv,(rr,cc)),shape=(len(terms),n)).tocsc()
        result=milp(np.zeros(n),integrality=np.ones(n),bounds=Bounds(lower,upper),constraints=LinearConstraint(matrix,lows,highs),options={'time_limit':max(.1,seconds-(time.monotonic()-start))})
        if result.status==2: return {'status':'unique','cuts':cuts}
        if result.status!=0: return {'status':'unresolved','message':result.message,'cuts':cuts}
        grid=[[SHAPES[int(np.argmax(result.x[(r*w+c)*7:(r*w+c+1)*7]))] for c in range(w)] for r in range(h)]
        occupied={(r,c) for r in range(h) for c in range(w) if grid[r][c]}; components=[]
        while occupied:
            todo=[next(iter(occupied))]; comp=set()
            while todo:
                r,c=todo.pop()
                if (r,c) not in occupied: continue
                occupied.remove((r,c));comp.add((r,c))
                for d in grid[r][c]:
                    dr,dc,_=D[d]; p=(r+dr,c+dc)
                    if p in occupied: todo.append(p)
            components.append(comp)
        if len(components)==1:
            check(data,grid); return {'status':'multiple','alternative':grid,'cuts':cuts}
        for comp in components:
            # Only closed components can be forbidden by their selected tile pattern.
            boundary=any(not(0<=r+D[d][0]<h and 0<=c+D[d][1]<w) for r,c in comp for d in grid[r][c])
            if not boundary:
                add([(ix(r,c,SHAPES.index(grid[r][c])),1) for r,c in comp],-np.inf,len(comp)-1);cuts+=1
    return {'status':'unresolved','message':'Audit time budget exceeded','cuts':cuts}

def canonical(data):
    h,w=len(data['rows']),len(data['columns'])
    pieces={(h-1-r,c):shape for shape,r,c,*_ in data['pieces']}
    forms=[]
    for reflect in (False,True):
        rows=list(data['rows']); cols=list(data['columns']); p=dict(pieces); hh,ww=h,w
        if reflect:
            cols.reverse(); p={(r,ww-1-c):''.join({'E':'W','W':'E','N':'N','S':'S'}[d] for d in s) for (r,c),s in p.items()}
        for _ in range(4):
            forms.append(json.dumps([rows,cols,sorted((r,c,''.join(sorted(s))) for (r,c),s in p.items())]))
            p={(c,hh-1-r):''.join({'N':'E','E':'S','S':'W','W':'N'}[d] for d in s) for (r,c),s in p.items()}
            rows,cols=cols,list(reversed(rows)); hh,ww=ww,hh
    return min(forms)

def main():
    folder=Path('dataset-audit'); records=[json.loads(x) for x in (folder/'validated-puzzles.jsonl').read_text().splitlines()]
    groups=defaultdict(list)
    for r in records: groups[canonical(r['puzzle'])].append(r['path'])
    (folder/'symmetry-duplicates.json').write_text(json.dumps([v for v in groups.values() if len(v)>1],indent=2))
    results=[]
    with (folder/'uniqueness.jsonl').open('w') as f:
        for i,r in enumerate(records,1):
            start=time.monotonic(); check(r['puzzle'],r['solution']); answer=second_solution(r)
            answer.update(path=r['path'],seconds=round(time.monotonic()-start,3)); results.append(answer)
            f.write(json.dumps(answer)+'\n'); f.flush()
            if i%25==0: print(i,dict(Counter(x['status'] for x in results)),flush=True)
    summary={'total':len(results),'statuses':dict(Counter(x['status'] for x in results)),'symmetry_duplicate_groups':sum(len(v)>1 for v in groups.values())}
    (folder/'uniqueness-summary.json').write_text(json.dumps(summary,indent=2)); print(summary)
if __name__=='__main__': main()
