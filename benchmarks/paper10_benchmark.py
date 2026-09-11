#!/usr/bin/env python3
import argparse, gc, itertools, json, math, os, platform, random, resource, sys, time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'source'
sys.path.insert(0, str(ROOT))

from srmh import Event, Graph, MAX_MIN, COUNT, MIN_PLUS, BOOLEAN, join
from srmh.engine import Engine
from srmh.search import ProgramSearch, Operator
from tests.oracles import temporal_oracle

ALGS=(MAX_MIN, COUNT, MIN_PLUS, BOOLEAN)
SEED=20260906


def add(e, eid, s, r, o, t=0, *, positive=True, operation='ASSERT', target=None,
        confidence=1.0, context='default'):
    e.ledger.add(Event(str(eid), str(s), str(r), str(o), float(t), operation=operation,
                       target=target, positive=positive, confidence=float(confidence),
                       context=str(context), source='paper10'))


def rss_mb():
    # Linux ru_maxrss is KiB.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def timed(name, fn):
    gc.collect()
    t0=time.perf_counter(); c0=time.process_time()
    try:
        ok, detail = fn()
        err=None
    except Exception as ex:
        ok=False; detail={}; err=repr(ex)
    return {
        'name': name, 'ok': bool(ok), 'wall_seconds': time.perf_counter()-t0,
        'cpu_seconds': time.process_time()-c0, 'max_rss_mb_process': rss_mb(),
        'error': err, 'detail': detail,
    }


def enumerate_walks(edges, start, rels, alg):
    paths=[(start, alg.one)]
    for r in rels:
        nxt=[]
        for s0, val in paths:
            for s, rr, o, w in edges:
                if s==s0 and rr==r:
                    nv=alg.extend(val,w)
                    if nv != alg.zero: nxt.append((o,nv))
        paths=nxt
    out={}
    for o,v in paths:
        out[o]=alg.merge(out.get(o,alg.zero),v)
    return {k:v for k,v in out.items() if v!=alg.zero}


def t01_semiring_oracle():
    rr=random.Random(SEED+1); total=0; failures=[]; per={}
    for alg in ALGS:
        passed=0
        for i in range(2500):
            n=8; depth=5; rels=[f'r{d}' for d in range(depth)]; g=Graph(); edges=[]
            for r in rels:
                for s in range(n):
                    for _ in range(rr.randint(1,3)):
                        o=rr.randrange(n)
                        if alg.name=='max_min': w=rr.choice([.1,.25,.5,.75,1.0])
                        elif alg.name=='boolean': w=bool(rr.getrandbits(1))
                        elif alg.name=='min_plus': w=rr.randint(1,9)
                        else: w=1
                        g.add(f'n{s}',r,f'n{o}',w); edges.append((f'n{s}',r,f'n{o}',w))
            got,_=g.propagate({'n0':alg.one},rels,alg)
            exp=enumerate_walks(edges,'n0',rels,alg)
            if alg.name=='max_min':
                ok=set(got)==set(exp) and all(abs(got[k]-exp[k])<1e-12 for k in exp)
            else: ok=got==exp
            total += 1
            if ok: passed+=1
            elif len(failures)<5: failures.append({'alg':alg.name,'case':i,'got':got,'exp':exp})
        per[alg.name]={'passed':passed,'total':2500}
    return not failures and total==10000, {'cases':total,'per_algebra':per,'failures':failures}


def t02_depth_scaling():
    points=[]; ok=True
    for n in (1000,10000,50000,100000,200000):
        e=Engine(); t=time.perf_counter()
        for i in range(n): add(e,i,f'n{i}','r',f'n{i+1}')
        build=time.perf_counter()-t
        t=time.perf_counter(); a,f,m=e.walk('n0',['r']*n,algebra=BOOLEAN); query=time.perf_counter()-t
        good=a.status=='ANSWER' and a.values==(f'n{n}',) and f=={f'n{n}':True} and m['max_frontier']==1
        ok &= good
        points.append({'hops':n,'build_s':build,'query_s':query,'events':len(e.ledger),'correct':good})
        del e; gc.collect()
    return ok, {'points':points}


def t03_distractor_scaling():
    e=Engine(); depth=128; rels=[f'r{i}' for i in range(depth)]
    for i,r in enumerate(rels): add(e,f'p{i}',f'n{i}',r,f'n{i+1}')
    milestones=[0,10000,100000,500000,1000000]; points=[]; added=0; ok=True
    for target in milestones:
        tbuild=time.perf_counter()
        for i in range(added,target):
            r=rels[i%depth]; add(e,f'd{i}',f'ds{i}',r,f'do{i}')
        build=time.perf_counter()-tbuild; added=target
        tq=time.perf_counter(); a,f,m=e.walk('n0',rels,algebra=BOOLEAN); query=time.perf_counter()-tq
        good=a.status=='ANSWER' and a.values==(f'n{depth}',) and m['max_frontier']==1
        ok &= good
        points.append({'distractors':target,'total_events':len(e.ledger),'incremental_build_s':build,'query_s':query,'correct':good})
    return ok, {'depth':depth,'points':points}


def status_from_events(events):
    pos={e.object for e in events if e.positive}; neg={e.object for e in events if not e.positive}
    if pos & neg: st='CONTRADICTED'
    elif len(pos)>1: st='AMBIGUOUS'
    elif pos: st='ANSWER'
    elif neg: st='NEGATED'
    else: st='UNKNOWN'
    return st, tuple(sorted(pos))


def t04_temporal_replay():
    rr=random.Random(SEED+4); e=Engine(['f']); bysub=defaultdict(list); all_events=[]
    nsubjects=100; per_subject=500; eid=0
    for sidx in range(nsubjects):
        s=f's{sidx}'
        known_ids=[]
        for t in range(1,per_subject+1):
            p=rr.random(); obj=f'v{rr.randrange(25)}'
            eid+=1
            if p < .68:
                ev=Event(f'e{eid}',s,'f',obj,float(t),positive=True,source='paper10'); known_ids.append(ev.id)
            elif p < .84:
                ev=Event(f'e{eid}',s,'f',obj,float(t),positive=False,source='paper10')
            else:
                # Mostly untargeted retractions; occasional valid targeted one.
                target=rr.choice(known_ids) if known_ids and rr.random()<.25 else None
                ev=Event(f'e{eid}',s,'f',obj,float(t),operation='RETRACT',target=target,source='paper10')
            bysub[s].append(ev); all_events.append(ev)
    shuffled=all_events[:]; rr.shuffle(shuffled)
    t=time.perf_counter()
    for ev in shuffled: e.ledger.add(ev)
    insert_s=time.perf_counter()-t
    failures=[]; q=5000; t=time.perf_counter(); before=e.state_counts()
    for i in range(q):
        s=f's{rr.randrange(nsubjects)}'; cutoff=rr.randrange(0,per_subject+2)
        ids=temporal_oracle(bysub[s], {'f'}, s, 'f', cutoff)
        idmap={ev.id:ev for ev in bysub[s]}; active=[idmap[x] for x in ids]
        exp=status_from_events(active)
        got=e.ledger.lookup(s,'f',cutoff)
        if (got.status,got.values)!=exp and len(failures)<8:
            failures.append({'subject':s,'cutoff':cutoff,'expected':exp,'got':(got.status,got.values)})
    query_s=time.perf_counter()-t
    # Engine transport on an independent subset.
    eng_bad=[]
    for i in range(1000):
        s=f's{rr.randrange(nsubjects)}'; cutoff=rr.randrange(0,per_subject+2)
        l=e.ledger.lookup(s,'f',cutoff); a,_,_=e.walk(s,['f'],time=cutoff)
        if (a.status,a.values)!=(l.status,l.values) and len(eng_bad)<8:
            eng_bad.append({'subject':s,'cutoff':cutoff,'ledger':(l.status,l.values),'engine':(a.status,a.values)})
    nonmut=(before==e.state_counts())
    return not failures and not eng_bad and nonmut, {'events':len(all_events),'oracle_queries':q,'engine_queries':1000,'insert_s':insert_s,'oracle_query_s':query_s,'oracle_failures':failures,'engine_failures':eng_bad,'query_nonmutation':nonmut}


def t05_revision_invalidation():
    e=Engine(['r']); chains=1000; depth=20; mid=10; old_end={}; alt_end={}; mode={}; eid=0
    # Base histories at t=1.
    for c in range(chains):
        cur=f'c{c}_0'
        for d in range(depth):
            nxt=f'c{c}_{d+1}'; eid+=1; add(e,eid,cur,'r',nxt,t=1); cur=nxt
        old_end[c]=cur
    # Revisions at t=2.
    for c in range(chains):
        subj=f'c{c}_{mid}'
        if c < 400:
            mode[c]='unchanged'; alt_end[c]=old_end[c]
        elif c < 700:
            mode[c]='retracted'
            # retract the active middle edge exactly
            target=str(c*depth + mid + 1); eid+=1
            add(e,eid,subj,'r',f'c{c}_{mid+1}',t=2,operation='RETRACT',target=target)
            alt_end[c]=None
        else:
            mode[c]='superseded'
            # New functional successor and a parallel tail with the same remaining hop count.
            alt=f'a{c}_{mid+1}'; eid+=1; add(e,eid,subj,'r',alt,t=2)
            cur=alt
            for d in range(mid+1,depth):
                nxt=f'a{c}_{d+1}'; eid+=1; add(e,eid,cur,'r',nxt,t=2); cur=nxt
            alt_end[c]=cur
    failures=[]; rels=['r']*depth; t=time.perf_counter()
    for c in range(chains):
        start=f'c{c}_0'; old,_,_=e.walk(start,rels,time=1,algebra=BOOLEAN); now,_,_=e.walk(start,rels,time=3,algebra=BOOLEAN)
        if old.status!='ANSWER' or old.values!=(old_end[c],):
            failures.append({'chain':c,'phase':'historical','got':(old.status,old.values),'expected':old_end[c]})
        if mode[c]=='unchanged': exp=('ANSWER',(old_end[c],))
        elif mode[c]=='retracted': exp=('UNKNOWN',())
        else: exp=('ANSWER',(alt_end[c],))
        if (now.status,now.values)!=exp:
            failures.append({'chain':c,'phase':'current','got':(now.status,now.values),'expected':exp})
        if len(failures)>=8: break
    qtime=time.perf_counter()-t
    return not failures, {'chains':chains,'depth':depth,'events':len(e.ledger),'historical_and_current_queries':chains*2,'query_s':qtime,'failures':failures,'groups':{'unchanged':400,'retracted':300,'superseded':300}}


def expected_world(first_conf, pos, neg, alg):
    base=alg.extend(alg.one, first_conf if alg.name=='max_min' else 1)
    best={}
    for obj,conf in pos: best[obj]=max(best.get(obj,-1),conf)
    fr={}; ta={}
    for obj,conf in best.items():
        v=alg.extend(base, conf if alg.name=='max_min' else 1)
        if v!=alg.zero: fr[obj]=v; ta[obj]=obj in neg
    if fr: st='CONTRADICTED' if any(ta.values()) else 'ANSWER'
    else: st='NEGATED' if neg else 'UNKNOWN'
    return st,fr,ta


def outkey(w):
    st,fr,ta=w
    return (st,tuple(sorted((o,v,bool(ta.get(o,False))) for o,v in fr.items())))


def t06_possible_world_fuzz():
    rr=random.Random(SEED+6); failures=[]; passed=0; cases=40000; per=defaultdict(lambda:[0,0])
    for i in range(cases):
        alg=ALGS[i%4]; per[alg.name][1]+=1; e=Engine(['f']); worlds=[]; n=rr.choice([2,2,3])
        for j in range(n):
            node=f'a{j}'; fc=rr.choice([.25,.5,.75,1.0]); add(e,f'f{i}-{j}','s','f',node,confidence=fc)
            pos=[]; neg=set()
            for obj in ('z0','z1'):
                typ=rr.randrange(5)
                if typ==1:
                    add(e,f'n{i}-{j}-{obj}',node,'r',obj,positive=False); neg.add(obj)
                elif typ==2:
                    c=rr.choice([.3,.6,.9,1.0]); add(e,f'p{i}-{j}-{obj}',node,'r',obj,confidence=c); pos.append((obj,c))
                elif typ==3:
                    c=rr.choice([.3,.6,.9,1.0]); add(e,f'p{i}-{j}-{obj}',node,'r',obj,confidence=c); add(e,f'n{i}-{j}-{obj}',node,'r',obj,positive=False); pos.append((obj,c)); neg.add(obj)
                elif typ==4:
                    c1=rr.choice([.3,.6,.9,1.0]); c2=rr.choice([.3,.6,.9,1.0]); add(e,f'p1{i}-{j}-{obj}',node,'r',obj,confidence=c1); add(e,f'p2{i}-{j}-{obj}',node,'r',obj,confidence=c2); pos += [(obj,c1),(obj,c2)]
            worlds.append(expected_world(fc,pos,neg,alg))
        uniq={outkey(w):w for w in worlds}
        if len(uniq)==1:
            st,fr,ta=next(iter(uniq.values())); exp=(st,tuple(sorted(fr)),fr)
        else:
            exp=('AMBIGUOUS',tuple(sorted({o for _,fr,_ in uniq.values() for o in fr})),{})
        a,f,m=e.walk('s',['f','r'],algebra=alg)
        ok=(a.status,a.values,f)==exp
        if exp[0]=='AMBIGUOUS':
            real={tuple(sorted(fr.items())) for _,fr,_ in uniq.values()}
            ok &= all(tuple(sorted(pf.items())) in real for pf in (m.get('possible_frontiers') or ()))
        if ok: passed+=1; per[alg.name][0]+=1
        elif len(failures)<8: failures.append({'case':i,'alg':alg.name,'expected':exp,'got':(a.status,a.values,f),'possible_statuses':m.get('possible_statuses'),'possible_frontiers':m.get('possible_frontiers')})
    # Deep reconvergence control: 1,000 independent two-way functional choices,
    # each immediately reconverging. Exact simplification should avoid 2^1000 state growth.
    nchoices=1000; re=Engine([f'f{k}' for k in range(nchoices)]); cur='s'; relprog=[]; eid=0
    for k in range(nchoices):
        a=f'a{k}'; b=f'b{k}'; nxt=f'n{k}'; fk=f'f{k}'; rk=f'c{k}'
        eid+=1; add(re,eid,cur,fk,a); eid+=1; add(re,eid,cur,fk,b)
        eid+=1; add(re,eid,a,rk,nxt); eid+=1; add(re,eid,b,rk,nxt)
        relprog.extend([fk,rk]); cur=nxt
    tr=time.perf_counter(); ra,rf,rm=re.walk('s',relprog,algebra=BOOLEAN); recon_s=time.perf_counter()-tr
    recon_ok=(ra.status=='ANSWER' and ra.values==(cur,) and rf=={cur:True} and rm['possible_outcomes']==1 and rm['max_frontier']<=2)
    return passed==cases and recon_ok, {'cases':cases,'passed':passed,'per_algebra':{k:{'passed':v[0],'total':v[1]} for k,v in per.items()},'failures':failures,
        'reconvergence':{'choices':nchoices,'relations':len(relprog),'events':len(re.ledger),'seconds':recon_s,'max_frontier':rm['max_frontier'],'possible_outcomes':rm['possible_outcomes'],'correct':recon_ok}}


def t07_representation_invariance():
    rr=random.Random(SEED+7); cases=1000; failures=[]
    for i in range(cases):
        depth=6; nodes=[f'n{k}' for k in range(20)]; rels=[f'r{d}' for d in range(depth)]; facts=[]; eid=0
        for r in rels:
            for s in nodes:
                for _ in range(rr.randint(0,2)):
                    eid+=1; facts.append((f'e{eid}',s,r,rr.choice(nodes)))
        # guarantee at least one path
        cur='n0'; guaranteed=[]
        for d,r in enumerate(rels):
            nxt=f'g{i}_{d}'; eid+=1; facts.append((f'e{eid}',cur,r,nxt)); guaranteed.append(nxt); cur=nxt
        e1=Engine(); order=facts[:]; rr.shuffle(order)
        for ev in order: add(e1,*ev)
        a1,f1,_=e1.walk('n0',rels,algebra=BOOLEAN)
        # bijective opaque renaming of every symbol class
        ents=sorted({s for _,s,_,o in facts}|{o for _,s,_,o in facts}|{'n0'})
        rnames=sorted(set(rels)); emap={x:f'X{i}_{k}_{rr.randrange(10**9):09d}' for k,x in enumerate(ents)}; rmap={x:f'Q{i}_{k}_{rr.randrange(10**9):09d}' for k,x in enumerate(rnames)}
        e2=Engine(); renamed=[(f'R{j}',emap[s],rmap[r],emap[o]) for j,(_,s,r,o) in enumerate(facts)]; rr.shuffle(renamed)
        for ev in renamed: add(e2,*ev)
        a2,f2,_=e2.walk(emap['n0'],[rmap[r] for r in rels],algebra=BOOLEAN)
        mapped_values=tuple(sorted(emap[v] for v in a1.values)); mapped_front={emap[k]:v for k,v in f1.items()}
        if not (a2.status==a1.status and a2.values==mapped_values and f2==mapped_front):
            if len(failures)<8: failures.append({'case':i,'original':(a1.status,a1.values,f1),'renamed':(a2.status,a2.values,f2),'expected_values':mapped_values})
    return not failures, {'cases':cases,'failures':failures}


def t08_proof_validity():
    rr=random.Random(SEED+8); cases=2000; failures=[]
    # half random ordinary proofs, half repeated functional choice proofs
    for i in range(cases):
        if i%2==0:
            depth=rr.randint(3,8); e=Engine(); rels=[f'r{d}' for d in range(depth)]; cur='s'; expected=[]
            for d,r in enumerate(rels):
                # guaranteed path plus distractors
                nxt=f'p{i}_{d}'; eid=f'g{i}_{d}'; add(e,eid,cur,r,nxt); expected.append(eid)
                for j in range(3): add(e,f'd{i}_{d}_{j}',cur,r,f'x{i}_{d}_{j}')
                cur=nxt
            a,_,m=e.walk('s',rels,algebra=BOOLEAN,proof=True); target=cur; mw=(m['minimal_witness'] or {}).get(target,())
            evmap={ev.id:ev for ev in e.ledger.events()}
            good=a.status=='ANSWER' and target in a.values and len(mw)==depth
            prev='s'
            for d,edge in enumerate(mw):
                pd,s,dd,o,ids=edge; good &= (pd==d and dd==d+1 and s==prev and bool(ids))
                good &= any((x in evmap and evmap[x].subject==s and evmap[x].relation==rels[d] and evmap[x].object==o) for x in ids)
                prev=o
            good &= prev==target
        else:
            # same functional cell is revisited; witness must make the same choice both times
            e=Engine(['f']); suffix=str(i)
            add(e,'fa'+suffix,'s','f','a'+suffix); add(e,'fb'+suffix,'s','f','b'+suffix)
            add(e,'ar'+suffix,'a'+suffix,'r','u'+suffix); add(e,'br'+suffix,'b'+suffix,'r','v'+suffix)
            add(e,'ab'+suffix,'u'+suffix,'back','s'); add(e,'bb'+suffix,'v'+suffix,'back','s')
            add(e,'az'+suffix,'a'+suffix,'q','z'+suffix); add(e,'bz'+suffix,'b'+suffix,'q','z'+suffix)
            a,_,m=e.walk('s',['f','r','back','f','q'],algebra=BOOLEAN,proof=True); target='z'+suffix; mw=(m['minimal_witness'] or {}).get(target,())
            choices=[o for _,s,_,o,_ in mw if s=='s' and o in {'a'+suffix,'b'+suffix}]
            good=a.status=='ANSWER' and a.values==(target,) and len(mw)==5 and len(choices)==2 and len(set(choices))==1
        if not good and len(failures)<8: failures.append({'case':i,'answer':(a.status,a.values),'witness':mw})
    return not failures, {'cases':cases,'failures':failures}


def sat_oracle(nvars, clauses):
    sols=[]
    for bits in itertools.product((0,1),repeat=nvars):
        if all(any((bits[v] if sign else 1-bits[v]) for v,sign in c) for c in clauses): sols.append(bits)
    return sols


def clause_table(c):
    vs=sorted({v for v,_ in c}); rows=[]
    for bits in itertools.product((0,1),repeat=len(vs)):
        d=dict(zip(vs,bits))
        if any(d[v] if sign else 1-d[v] for v,sign in c): rows.append({f'x{v}':d[v] for v in vs})
    return rows


def nqueens(n):
    tables=[]
    for a,b in itertools.combinations(range(n),2):
        tables.append([{f'q{a}':x,f'q{b}':y} for x in range(n) for y in range(n) if x!=y and abs(x-y)!=b-a])
    t=time.perf_counter(); got=join(tables); return len(got),time.perf_counter()-t


def t09_smt_csp():
    rr=random.Random(SEED+9); failures=[]; stats={}
    # 3-SAT exact model sets
    sat_pass=0; t=time.perf_counter()
    for i in range(100):
        n=8; clauses=[]
        for _ in range(20):
            vs=rr.sample(range(n),3); clauses.append(tuple((v,bool(rr.getrandbits(1))) for v in vs))
        got=join([clause_table(c) for c in clauses]); gs={tuple(row[f'x{k}'] for k in range(n)) for row in got}; ex=set(sat_oracle(n,clauses))
        if gs==ex: sat_pass+=1
        elif len(failures)<5: failures.append({'kind':'3sat','case':i,'got_n':len(gs),'exp_n':len(ex)})
    stats['3sat_8var_20clause']={'passed':sat_pass,'total':100,'seconds':time.perf_counter()-t}
    # 3-color exact sets
    col_pass=0; t=time.perf_counter()
    for i in range(100):
        n=7; edges={(j,j+1) for j in range(n-1)}
        while len(edges)<10:
            a,b=sorted(rr.sample(range(n),2)); edges.add((a,b))
        tabs=[[{f'v{a}':x,f'v{b}':y} for x in range(3) for y in range(3) if x!=y] for a,b in edges]
        got=join(tabs); gs={tuple(row[f'v{k}'] for k in range(n)) for row in got}; ex={x for x in itertools.product(range(3),repeat=n) if all(x[a]!=x[b] for a,b in edges)}
        if gs==ex: col_pass+=1
        elif len(failures)<5: failures.append({'kind':'3color','case':i,'got_n':len(gs),'exp_n':len(ex)})
    stats['graph_3color_n7']={'passed':col_pass,'total':100,'seconds':time.perf_counter()-t}
    # pigeonhole 5 into 4: unsat
    holes=range(4); tabs=[]
    for a,b in itertools.combinations(range(5),2): tabs.append([{f'p{a}':x,f'p{b}':y} for x in holes for y in holes if x!=y])
    t=time.perf_counter(); ph=join(tabs); stats['pigeonhole_5_into_4']={'unsat':ph==[],'seconds':time.perf_counter()-t};
    if ph: failures.append({'kind':'pigeonhole','models':len(ph)})
    q8,t8=nqueens(8); q9,t9=nqueens(9); stats['nqueens_8']={'solutions':q8,'expected':92,'seconds':t8}; stats['nqueens_9']={'solutions':q9,'expected':352,'seconds':t9}
    if q8!=92: failures.append({'kind':'queens8','got':q8});
    if q9!=352: failures.append({'kind':'queens9','got':q9})
    return not failures, {'stats':stats,'failures':failures}


def t10_program_induction():
    rr=random.Random(SEED+10); cases=500; correct=0; wrong=0; abstain=0; complete=0; failures=[]
    base_ops=[('A',lambda x:(x+1)%101),('B',lambda x:(x-1)%101),('C',lambda x:(2*x)%101),('D',lambda x:(3*x+1)%101),('E',lambda x:(-x)%101)]
    for i in range(cases):
        # rename operators opaquely each case
        names=[f'Q{i}_{rr.randrange(10**9):09d}' for _ in base_ops]
        ops=[Operator(n,fn) for n,(_,fn) in zip(names,base_ops)]; search=ProgramSearch(ops)
        L=rr.randint(1,4); target=tuple(rr.choice(names) for _ in range(L))
        train=rr.sample(range(0,60),8); held=rr.sample(range(60,101),4)
        examples=[(x,search.execute(target,x)) for x in train]
        result=search.fit(examples,max_depth=4,max_states=10000,max_programs=50000)
        complete += int(result.complete)
        for x in held:
            pred=search.predict(result,x); exp=search.execute(target,x)
            if pred.status=='ANSWER' and pred.values==(exp,): correct+=1
            elif pred.status in ('UNKNOWN','AMBIGUOUS'): abstain+=1
            else:
                wrong+=1
                if len(failures)<8: failures.append({'case':i,'target':target,'x':x,'expected':exp,'got':(pred.status,pred.values),'programs':len(result.programs),'complete':result.complete})
    total=cases*4
    # For this exact finite library, any confident wrong held-out prediction is a failure; abstention is reported separately.
    return wrong==0 and correct>0, {'problems':cases,'heldout_predictions':total,'correct':correct,'wrong':wrong,'abstained':abstain,'fit_complete_problems':complete,'failures':failures}

TESTS={
'01_semiring_oracle':t01_semiring_oracle,
'02_depth_scaling':t02_depth_scaling,
'03_distractor_scaling':t03_distractor_scaling,
'04_temporal_replay':t04_temporal_replay,
'05_revision_invalidation':t05_revision_invalidation,
'06_possible_world_fuzz':t06_possible_world_fuzz,
'07_representation_invariance':t07_representation_invariance,
'08_proof_validity':t08_proof_validity,
'09_smt_csp':t09_smt_csp,
'10_program_induction':t10_program_induction,
}

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--test',choices=['all']+list(TESTS),default='all'); ap.add_argument('--out'); args=ap.parse_args()
    names=list(TESTS) if args.test=='all' else [args.test]
    results=[]
    for name in names:
        r=timed(name,TESTS[name]); results.append(r); print(json.dumps(r,default=str),flush=True)
    payload={'seed':SEED,'environment':{'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),'processor':platform.processor()},'passed':sum(r['ok'] for r in results),'total':len(results),'results':results}
    if args.out:
        with open(args.out,'w') as f: json.dump(payload,f,indent=2,default=str)
    if args.test=='all': print(json.dumps(payload,indent=2,default=str))
