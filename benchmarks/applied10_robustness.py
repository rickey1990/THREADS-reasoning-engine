#!/usr/bin/env python3
import json, random, time, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] / 'source'
sys.path.insert(0,str(ROOT))
from srmh.engine import Engine
from srmh.ledger import Event
from srmh.algebra import BOOLEAN

SEEDS=[99173,130363,196613]

def E(id,s,r,o,t,**kw): return Event(id=id,subject=s,relation=r,object=o,time=t,**kw)
def W(e,s,rels,t,context='default',proof=False): return e.walk(s,rels,time=t,context=context,algebra=BOOLEAN,proof=proof)
def VS(a): return set(a.values)
def WIDS(meta):
    out=set()
    for p in (meta.get('minimal_witness') or {}).values():
        for edge in p: out.update(edge[4])
    return out

def record(stats,name,ok,detail):
    d=stats.setdefault(name,{'checks':0,'passed':0,'failures':[]}); d['checks']+=1
    if ok:d['passed']+=1
    elif len(d['failures'])<5:d['failures'].append(detail)

def run_seed(seed,stats):
    r=random.Random(seed)
    # 1 Correctable memory: random revision depth + retract latest + re-learn.
    e=Engine(functional={'pref'})
    for i in range(100):
        u=f'm{seed}_{i}'; n=r.randint(2,5); vals=[f'v{i}_{j}' for j in range(n)]; times=[10+10*j for j in range(n)]
        ids=[]
        insert=[]
        for j,(v,t) in enumerate(zip(vals,times)):
            eid=f'm{seed}_{i}_{j}'; ids.append(eid); insert.append(E(eid,u,'pref',v,t))
        r.shuffle(insert)
        for x in insert:e.ledger.add(x)
        k=r.randrange(n); qt=times[k]+1
        a,_,_=W(e,u,['pref'],qt); record(stats,'1 memory revisions',a.status=='ANSWER' and VS(a)=={vals[k]},[seed,i,'history',a.status,a.values,vals[k]])
        rt=times[-1]+5; e.ledger.add(E(f'mr{seed}_{i}',u,'pref',vals[-1],rt,operation='RETRACT',target=ids[-1]))
        a,_,_=W(e,u,['pref'],rt+1); record(stats,'1 memory revisions',a.status=='UNKNOWN',[seed,i,'retract',a.status,a.values])
        nv=f'v{i}_relearn'; e.ledger.add(E(f'mn{seed}_{i}',u,'pref',nv,rt+10)); a,_,_=W(e,u,['pref'],rt+11); record(stats,'1 memory revisions',a.status=='ANSWER' and VS(a)=={nv},[seed,i,'relearn',a.status,a.values])

    # 2 Entitlement: random depth and distractors; revoke random internal link.
    e=Engine()
    for i in range(100):
        depth=r.randint(3,7); nodes=[f'a{seed}_{i}_{j}' for j in range(depth+1)]; rels=[f'perm_r{j}' for j in range(depth)]; ids=[]
        for j,rel in enumerate(rels):
            eid=f'ae{seed}_{i}_{j}';ids.append(eid);e.ledger.add(E(eid,nodes[j],rel,nodes[j+1],10))
        for d in range(r.randint(0,25)):
            e.ledger.add(E(f'ad{seed}_{i}_{d}',f'noise{seed}_{i}_{d}',r.choice(rels),f'nv{seed}_{i}_{d}',10))
        a,_,_=W(e,nodes[0],rels,15);record(stats,'2 entitlement revocation',a.status=='ANSWER' and VS(a)=={nodes[-1]},[seed,i,'before',a.status,a.values])
        j=r.randrange(depth);e.ledger.add(E(f'ar{seed}_{i}',nodes[j],rels[j],nodes[j+1],20,operation='RETRACT',target=ids[j]))
        a,_,_=W(e,nodes[0],rels,25);record(stats,'2 entitlement revocation',a.status=='UNKNOWN',[seed,i,'after',a.status,a.values])
        a,_,_=W(e,nodes[0],rels,15);record(stats,'2 entitlement revocation',a.status=='ANSWER' and VS(a)=={nodes[-1]},[seed,i,'historic',a.status,a.values])

    # 3 Compliance: five different exact conflict shapes.
    e=Engine(functional={'decision'})
    for i in range(100):
        s=f'c{seed}_{i}';typ=r.randrange(5)
        if typ==0:
            d=f'd{i}';e.ledger.add(E(f'c{seed}_{i}a',s,'decision',d,10));e.ledger.add(E(f'c{seed}_{i}e',d,'effect','PERMIT',10));exp=('ANSWER',{'PERMIT'})
        elif typ==1:
            opts=[f'o{i}_{j}' for j in range(r.randint(2,4))]
            for j,o in enumerate(opts):e.ledger.add(E(f'c{seed}_{i}o{j}',s,'decision',o,10));e.ledger.add(E(f'c{seed}_{i}e{j}',o,'effect','REVIEW',10))
            exp=('ANSWER',{'REVIEW'})
        elif typ==2:
            opts=[f'o{i}_{j}' for j in range(r.randint(2,4))];outs={f'OUT{j}' for j in range(len(opts))}
            for j,o in enumerate(opts):e.ledger.add(E(f'c{seed}_{i}o{j}',s,'decision',o,10));e.ledger.add(E(f'c{seed}_{i}e{j}',o,'effect',f'OUT{j}',10))
            exp=('AMBIGUOUS',outs)
        elif typ==3:
            o=f'o{i}';e.ledger.add(E(f'c{seed}_{i}p',s,'decision',o,10));e.ledger.add(E(f'c{seed}_{i}n',s,'decision',o,10,positive=False));e.ledger.add(E(f'c{seed}_{i}e',o,'effect','PERMIT',10));exp=('CONTRADICTED',{'PERMIT'})
        else:
            a=f'oa{i}';b=f'ob{i}';e.ledger.add(E(f'c{seed}_{i}a',s,'decision',a,10));e.ledger.add(E(f'c{seed}_{i}an',s,'decision',a,10,positive=False));e.ledger.add(E(f'c{seed}_{i}b',s,'decision',b,10));e.ledger.add(E(f'c{seed}_{i}ae',a,'effect','REVIEW',10));e.ledger.add(E(f'c{seed}_{i}be',b,'effect','REVIEW',10));exp=('AMBIGUOUS',{'REVIEW'})
        a,_,_=W(e,s,['decision','effect'],15);record(stats,'3 compliance conflicts',a.status==exp[0] and VS(a)==exp[1],[seed,i,typ,a.status,a.values,exp])

    # 4 Workflow dependency random depth/revoke location.
    e=Engine()
    for i in range(100):
        depth=r.randint(2,10);nodes=[f'w{seed}_{i}_{j}' for j in range(depth+1)];ids=[]
        for j in range(depth):
            eid=f'we{seed}_{i}_{j}';ids.append(eid);e.ledger.add(E(eid,nodes[j],'dep',nodes[j+1],10))
        e.ledger.add(E(f'ws{seed}_{i}',nodes[-1],'state','READY',10));rels=['dep']*depth+['state']
        a,_,_=W(e,nodes[0],rels,15);record(stats,'4 workflow invalidation',a.status=='ANSWER' and VS(a)=={'READY'},[seed,i,'before',a.status,a.values])
        j=r.randrange(depth);e.ledger.add(E(f'wr{seed}_{i}',nodes[j],'dep',nodes[j+1],20,operation='RETRACT',target=ids[j]));a,_,_=W(e,nodes[0],rels,25);record(stats,'4 workflow invalidation',a.status=='UNKNOWN',[seed,i,'after',a.status,a.values])

    # 5 RAG provenance: 2-5 revisions; random historical version proof must match selected evidence.
    e=Engine(functional={'selected'})
    for i in range(100):
        q=f'q{seed}_{i}';n=r.randint(2,5); sel=[]; ent=[]; claims=[]; answers=[]
        insertion=[]
        for j in range(n):
            t=10+10*j;cl=f'cl{seed}_{i}_{j}';an=f'an{seed}_{i}_{j}';sid=f'rs{seed}_{i}_{j}';eid=f're{seed}_{i}_{j}';claims.append(cl);answers.append(an);sel.append(sid);ent.append(eid)
            insertion.extend([E(sid,q,'selected',cl,t,source=f'doc{j}'),E(eid,cl,'entails',an,t,source=f'doc{j}')])
        r.shuffle(insertion)
        for x in insertion:e.ledger.add(x)
        k=r.randrange(n);a,_,m=W(e,q,['selected','entails'],10+10*k+1,proof=True)
        record(stats,'5 RAG provenance',a.status=='ANSWER' and VS(a)=={answers[k]},[seed,i,k,'answer',a.status,a.values])
        record(stats,'5 RAG provenance',WIDS(m)=={sel[k],ent[k]},[seed,i,k,'proof',sorted(WIDS(m)),[sel[k],ent[k]]])

    # 6 Incident resilience: random 2-5 equal-length paths; remove all but one, then last.
    e=Engine()
    for i in range(100):
        root=f'inc{seed}_{i}';target=f'impact{seed}_{i}';branches=r.randint(2,5);depth=r.randint(2,5);path_edges=[]
        for b in range(branches):
            prev=root;edges=[]
            for d in range(depth-1):
                nxt=f'ib{seed}_{i}_{b}_{d}';eid=f'ie{seed}_{i}_{b}_{d}';e.ledger.add(E(eid,prev,'impacts',nxt,10));edges.append((eid,prev,nxt));prev=nxt
            eid=f'ie{seed}_{i}_{b}_last';e.ledger.add(E(eid,prev,'impacts',target,10));edges.append((eid,prev,target));path_edges.append(edges)
        rels=['impacts']*depth;a,_,_=W(e,root,rels,15);record(stats,'6 incident resilience',a.status=='ANSWER' and VS(a)=={target},[seed,i,'start',a.status,a.values])
        # break every path except last
        for b in range(branches-1):
            eid,s,o=r.choice(path_edges[b]);e.ledger.add(E(f'ir{seed}_{i}_{b}',s,'impacts',o,20+b,operation='RETRACT',target=eid))
        a,_,_=W(e,root,rels,20+branches);record(stats,'6 incident resilience',a.status=='ANSWER' and VS(a)=={target},[seed,i,'redundant',a.status,a.values])
        eid,s,o=r.choice(path_edges[-1]);e.ledger.add(E(f'ir{seed}_{i}_last',s,'impacts',o,40,operation='RETRACT',target=eid));a,_,_=W(e,root,rels,41);record(stats,'6 incident resilience',a.status=='UNKNOWN',[seed,i,'allgone',a.status,a.values])

    # 7 Lineage: random 2-8 datasets, replace random subset sources.
    e=Engine(functional={'source'})
    for i in range(100):
        rep=f'lr{seed}_{i}';n=r.randint(2,8);old=[];current=[]
        for j in range(n):
            ds=f'lds{seed}_{i}_{j}';src=f'ls{seed}_{i}_{j}';old.append(src);current.append(src);e.ledger.add(E(f'ld{seed}_{i}_{j}',rep,'derived',ds,10));e.ledger.add(E(f'lsrc{seed}_{i}_{j}',ds,'source',src,10))
        change=r.sample(range(n),r.randint(1,n))
        for j in change:
            ns=f'ln{seed}_{i}_{j}';current[j]=ns;e.ledger.add(E(f'lnE{seed}_{i}_{j}',f'lds{seed}_{i}_{j}','source',ns,20))
        a,_,_=W(e,rep,['derived','source'],15);record(stats,'7 lineage correction',a.status=='ANSWER' and VS(a)==set(old),[seed,i,'old',a.status,a.values,set(old)])
        a,_,_=W(e,rep,['derived','source'],25);record(stats,'7 lineage correction',a.status=='ANSWER' and VS(a)==set(current),[seed,i,'new',a.status,a.values,set(current)])

    # 8 Context isolation: random 2-5 tenants, update one only.
    e=Engine(functional={'plan'})
    for i in range(100):
        acct=f'acct{seed}_{i}';contexts=[f't{seed}_{i}_{j}' for j in range(r.randint(2,5))];vals=[]
        for j,c in enumerate(contexts):
            v=f'P{j}';vals.append(v);e.ledger.add(E(f'xe{seed}_{i}_{j}',acct,'plan',v,10,context=c))
        upd=r.randrange(len(contexts));nv='UPDATED';e.ledger.add(E(f'xu{seed}_{i}',acct,'plan',nv,20,context=contexts[upd]))
        for j,c in enumerate(contexts):
            a,_,_=W(e,acct,['plan'],25,context=c);ex=nv if j==upd else vals[j];record(stats,'8 context isolation',a.status=='ANSWER' and VS(a)=={ex},[seed,i,c,a.status,a.values,ex])
        a,_,_=W(e,acct,['plan'],25);record(stats,'8 context isolation',a.status=='UNKNOWN',[seed,i,'default',a.status,a.values])

    # 9 Supply recall: random number components, recall position, safe/risky split.
    e=Engine(functional={'supplier'})
    for i in range(100):
        prod=f'p{seed}_{i}';n=r.randint(5,40);risky=r.random()<.55;pos=r.randrange(n) if risky else -1;rid=None
        for j in range(n):
            comp=f'pc{seed}_{i}_{j}';sup=f'ps{seed}_{i}_{j}';e.ledger.add(E(f'pe{seed}_{i}_{j}',prod,'contains',comp,10));e.ledger.add(E(f'pp{seed}_{i}_{j}',comp,'supplier',sup,10))
            if j==pos:
                rid=f'pr{seed}_{i}';e.ledger.add(E(rid,sup,'recall','RECALLED',10))
        a,_,_=W(e,prod,['contains','supplier','recall'],15)
        record(stats,'9 recall tracing',(a.status=='ANSWER' and VS(a)=={'RECALLED'}) if risky else a.status=='UNKNOWN',[seed,i,'initial',risky,a.status,a.values])
        if risky:
            e.ledger.add(E(f'pw{seed}_{i}',f'ps{seed}_{i}_{pos}','recall','RECALLED',20,operation='RETRACT',target=rid));a,_,_=W(e,prod,['contains','supplier','recall'],25);record(stats,'9 recall tracing',a.status=='UNKNOWN',[seed,i,'withdraw',a.status,a.values])

    # 10 Agent recovery: random plan revisions and next-step revisions, queried against constructed history.
    e=Engine(functional={'plan','next'})
    for i in range(100):
        ag=f'ag{seed}_{i}';events=[];checkpoints=[];t=5;plans=r.randint(1,4)
        for p in range(plans):
            plan=f'ap{seed}_{i}_{p}';events.append(E(f'apE{seed}_{i}_{p}',ag,'plan',plan,t));t+=5
            steps=r.randint(1,4)
            for s in range(steps):
                step=f'as{seed}_{i}_{p}_{s}';events.append(E(f'asE{seed}_{i}_{p}_{s}',plan,'next',step,t));checkpoints.append((t+1,step));t+=5
        r.shuffle(events)
        for x in events:e.ledger.add(x)
        # choose up to three temporal checkpoints; construction itself supplies exact expected next step.
        for qt,step in r.sample(checkpoints,min(3,len(checkpoints))):
            # Need derive which plan is current at qt, and latest next-step on that plan at qt.
            plan_events=[x for x in events if x.subject==ag and x.relation=='plan' and x.time<=qt]
            cp=max(plan_events,key=lambda x:x.time).object
            next_events=[x for x in events if x.subject==cp and x.relation=='next' and x.time<=qt]
            expected=max(next_events,key=lambda x:x.time).object if next_events else None
            a,_,_=W(e,ag,['plan','next'],qt)
            record(stats,'10 agent recovery',a.status=='ANSWER' and VS(a)=={expected},[seed,i,qt,a.status,a.values,expected])


def main():
    stats={};t=time.perf_counter()
    for s in SEEDS:run_seed(s,stats)
    results=[]
    for name,d in stats.items():
        d['failed']=d['checks']-d['passed'];d['pass_rate']=d['passed']/d['checks'];results.append({'name':name,**d});print(f"{name}: {d['passed']}/{d['checks']}")
        if d['failures']:print(' first:',d['failures'][0])
    out={'seeds':SEEDS,'results':results,'checks':sum(x['checks'] for x in results),'passed':sum(x['passed'] for x in results),'elapsed_s':time.perf_counter()-t}
    (Path(__file__).resolve().parents[1] / 'results' / 'applied10' / 'applied10_robustness_reproduced.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    return 0 if out['checks']==out['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
