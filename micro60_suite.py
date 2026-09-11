#!/usr/bin/env python3
import argparse, json, math, os, random, sys, time, traceback
from dataclasses import asdict, dataclass
from pathlib import Path

@dataclass
class CaseResult:
    ok: bool
    expected: object
    actual: object
    note: str = ""


def add_event(engine, eid, s, r, o, t=0, *, positive=True, operation='ASSERT', target=None, confidence=1.0, context='default'):
    from srmh import Event
    engine.ledger.add(Event(str(eid), str(s), str(r), str(o), float(t), operation=operation,
                            target=target, positive=positive, confidence=confidence, context=context))


def norm_answer(ans, frontier=None):
    out = {'status': ans.status, 'values': tuple(ans.values)}
    if frontier is not None:
        out['frontier'] = tuple(sorted(frontier.items(), key=lambda x: repr(x[0])))
    return out


def walk_result(engine, start, rels, **kwargs):
    a, f, meta = engine.walk(start, rels, **kwargs)
    return a, f, meta


def make_labels(rng, prefix, n):
    # Opaque deterministic IDs so lexical semantics cannot help.
    return [f"{prefix}_{rng.getrandbits(48):012x}_{i}" for i in range(n)]


def exact_answer(status, values=()):
    return {'status': status, 'values': tuple(sorted(values))}


def check_answer(ans, status, values=()):
    exp = exact_answer(status, values)
    act = {'status': ans.status, 'values': tuple(sorted(ans.values))}
    return CaseResult(exp == act, exp, act)


def cat01(rng, i):
    from srmh.engine import Engine
    e=Engine(); a,b=make_labels(rng,'n',2); r=make_labels(rng,'r',1)[0]
    add_event(e,i,a,r,b); ans,_,_=walk_result(e,a,[r]); return check_answer(ans,'ANSWER',[b])

def cat02(rng,i):
    from srmh.engine import Engine
    e=Engine(); a,b=make_labels(rng,'n',2); r,q=make_labels(rng,'r',2)
    add_event(e,i,a,r,b); ans,_,_=walk_result(e,a,[q]); return check_answer(ans,'UNKNOWN',[])

def cat03(rng,i):
    from srmh.engine import Engine
    e=Engine(); a,b=make_labels(rng,'n',2); r=make_labels(rng,'r',1)[0]
    add_event(e,f'{i}t',a,r,b)
    for j in range(25):
        x,y=make_labels(rng,'d',2); add_event(e,f'{i}d{j}',x,r,y)
    ans,_,_=walk_result(e,a,[r]); return check_answer(ans,'ANSWER',[b])

def chain_case(rng,i,length,mixed=False,repeated=False):
    from srmh.engine import Engine
    e=Engine(); nodes=make_labels(rng,'n',length+1)
    if repeated: rels=[make_labels(rng,'r',1)[0]]*length
    elif mixed: rels=make_labels(rng,'r',length)
    else: rels=make_labels(rng,'r',length)
    for j,r in enumerate(rels): add_event(e,f'{i}-{j}',nodes[j],r,nodes[j+1])
    ans,_,_=walk_result(e,nodes[0],rels); return check_answer(ans,'ANSWER',[nodes[-1]])

def cat04(rng,i): return chain_case(rng,i,2)
def cat05(rng,i): return chain_case(rng,i,3)
def cat06(rng,i): return chain_case(rng,i,rng.randint(2,10),mixed=True)
def cat07(rng,i): return chain_case(rng,i,rng.randint(2,12),repeated=True)
def cat08(rng,i): return chain_case(rng,i,rng.randint(3,8),mixed=True)

def cat09(rng,i):
    from srmh.engine import Engine
    e=Engine(); start,good,target=make_labels(rng,'n',3); r1,r2=make_labels(rng,'r',2)
    add_event(e,f'{i}g1',start,r1,good); add_event(e,f'{i}g2',good,r2,target)
    for j in range(10):
        d=make_labels(rng,'d',1)[0]; add_event(e,f'{i}d{j}',start,r1,d)
        if j%2==0: add_event(e,f'{i}x{j}',d,make_labels(rng,'x',1)[0],make_labels(rng,'y',1)[0])
    ans,_,_=walk_result(e,start,[r1,r2]); return check_answer(ans,'ANSWER',[target])

def cat10(rng,i):
    from srmh.engine import Engine
    e=Engine(); start,a,b,z=make_labels(rng,'n',4); r1,r2=make_labels(rng,'r',2)
    for k,o in enumerate((a,b)): add_event(e,f'{i}a{k}',start,r1,o); add_event(e,f'{i}b{k}',o,r2,z)
    ans,_,_=walk_result(e,start,[r1,r2]); return check_answer(ans,'ANSWER',[z])

def cat11(rng,i):
    from srmh.engine import Engine
    e=Engine(); a,b,c=make_labels(rng,'n',3); r=make_labels(rng,'r',1)[0]
    add_event(e,f'{i}0',a,r,b); add_event(e,f'{i}1',b,r,a); add_event(e,f'{i}2',a,r,c)
    ans,_,_=walk_result(e,a,[r,r]); return check_answer(ans,'ANSWER',[a]) if False else check_answer(ans,'ANSWER',[a])

def cat12(rng,i):
    from srmh.engine import Engine
    e=Engine(); a=make_labels(rng,'n',1)[0]; r=make_labels(rng,'r',1)[0]
    add_event(e,i,a,r,a); ans,_,_=walk_result(e,a,[r,r,r]); return check_answer(ans,'ANSWER',[a])

def cat13(rng,i):
    from srmh.engine import Engine
    from srmh.algebra import COUNT
    e=Engine(); a,b=make_labels(rng,'n',2); r=make_labels(rng,'r',1)[0]
    # Multiple observations of the same relation/object are evidence copies, not graph multiedges.
    for j in range(5): add_event(e,f'{i}-{j}',a,r,b,confidence=0.5+j*.05)
    ans,f,_=walk_result(e,a,[r],algebra=COUNT)
    exp={'status':'ANSWER','value':1}; act={'status':ans.status,'value':f.get(b)}
    return CaseResult(exp==act,exp,act)

def cat14(rng,i):
    from srmh.engine import Engine
    e=Engine(); a,b=make_labels(rng,'n',2); r=make_labels(rng,'r',1)[0]; add_event(e,i,a,r,b)
    for j in range(20): x,y=make_labels(rng,'d',2); add_event(e,f'{i}d{j}',x,r,y)
    ans,_,_=walk_result(e,a,[r]); return check_answer(ans,'ANSWER',[b])

def cat15(rng,i):
    from srmh.engine import Engine
    e=Engine(); start=make_labels(rng,'s',1)[0]; r=make_labels(rng,'r',1)[0]; vals=make_labels(rng,'v',50)
    for j,v in enumerate(vals): add_event(e,f'{i}-{j}',start,r,v)
    ans,_,_=walk_result(e,start,[r]); return check_answer(ans,'ANSWER',vals)

def cat16(rng,i): return chain_case(rng,i,rng.randint(20,80),mixed=True)

def cat17(rng,i):
    from srmh.engine import Engine
    e=Engine(); nodes=make_labels(rng,'n',5); rels=make_labels(rng,'r',4)
    for j,r in enumerate(rels): add_event(e,f'{i}g{j}',nodes[j],r,nodes[j+1])
    for j in range(500):
        x,y=make_labels(rng,'d',2); r=rels[rng.randrange(len(rels))]; add_event(e,f'{i}d{j}',x,r,y)
    ans,_,_=walk_result(e,nodes[0],rels); return check_answer(ans,'ANSWER',[nodes[-1]])

def cat18(rng,i):
    from srmh.engine import Engine
    e=Engine(); s=make_labels(rng,'s',1)[0]; r=make_labels(rng,'r',1)[0]; vals=make_labels(rng,'v',rng.randint(2,8))
    for j,v in enumerate(vals): add_event(e,f'{i}-{j}',s,r,v)
    ans,_,_=walk_result(e,s,[r]); return check_answer(ans,'ANSWER',vals)

def cat19(rng,i):
    from srmh.engine import Engine
    e=Engine(); s,g,z=make_labels(rng,'n',3); r1,r2=make_labels(rng,'r',2)
    add_event(e,f'{i}g',s,r1,g); add_event(e,f'{i}z',g,r2,z)
    for j in range(8): d=make_labels(rng,'d',1)[0]; add_event(e,f'{i}d{j}',s,r1,d)
    ans,_,_=walk_result(e,s,[r1,r2]); return check_answer(ans,'ANSWER',[z])

def cat20(rng,i): return cat10(rng,i)

def cat21(rng,i):
    from srmh.algebra import Graph, BOOLEAN
    g=Graph(); nodes=make_labels(rng,'n',4); rels=make_labels(rng,'r',3)
    for j,r in enumerate(rels): g.add(nodes[j],r,nodes[j+1],True)
    f,_=g.propagate({nodes[0]:True},rels,BOOLEAN)
    exp={nodes[-1]:True}; return CaseResult(f==exp,exp,f)

def cat22(rng,i):
    from srmh.engine import Engine
    from srmh.algebra import COUNT
    e=Engine(); s,z=make_labels(rng,'n',2); r1,r2=make_labels(rng,'r',2); mids=make_labels(rng,'m',rng.randint(2,8))
    for j,m in enumerate(mids): add_event(e,f'{i}a{j}',s,r1,m); add_event(e,f'{i}b{j}',m,r2,z)
    ans,f,_=walk_result(e,s,[r1,r2],algebra=COUNT)
    exp={'status':'ANSWER','count':len(mids)}; act={'status':ans.status,'count':f.get(z)}
    return CaseResult(exp==act,exp,act)

def cat23(rng,i):
    from srmh.engine import Engine
    from srmh.algebra import COUNT
    e=Engine(); s,m,z=make_labels(rng,'n',3); r1,r2,r3=make_labels(rng,'r',3); branches=make_labels(rng,'b',rng.randint(2,8))
    for j,b in enumerate(branches): add_event(e,f'{i}a{j}',s,r1,b); add_event(e,f'{i}b{j}',b,r2,m)
    add_event(e,f'{i}z',m,r3,z)
    ans,f,_=walk_result(e,s,[r1,r2,r3],algebra=COUNT)
    exp={'status':'ANSWER','count':len(branches)}; act={'status':ans.status,'count':f.get(z)}
    return CaseResult(exp==act,exp,act)

def cat24(rng,i):
    from srmh.algebra import Graph, MIN_PLUS
    g=Graph(); s,a,b,z=make_labels(rng,'n',4); r1,r2=make_labels(rng,'r',2)
    w1,w2,w3,w4=[rng.randint(1,20) for _ in range(4)]
    g.add(s,r1,a,w1); g.add(a,r2,z,w2); g.add(s,r1,b,w3); g.add(b,r2,z,w4)
    f,_=g.propagate({s:0},[r1,r2],MIN_PLUS); expected={z:min(w1+w2,w3+w4)}
    return CaseResult(f==expected,expected,f)

def cat25(rng,i):
    from srmh.algebra import Graph, MIN_PLUS
    g=Graph(); s,a,b,z=make_labels(rng,'n',4); r1,r2=make_labels(rng,'r',2); x,y=rng.randint(1,10),rng.randint(1,10)
    g.add(s,r1,a,x); g.add(a,r2,z,y); g.add(s,r1,b,y); g.add(b,r2,z,x)
    f,_=g.propagate({s:0},[r1,r2],MIN_PLUS); expected={z:x+y}; return CaseResult(f==expected,expected,f)

def cat26(rng,i):
    from srmh.engine import Engine
    from srmh.algebra import MAX_MIN
    e=Engine(); nodes=make_labels(rng,'n',4); rels=make_labels(rng,'r',3); cs=[rng.uniform(.1,1) for _ in range(3)]
    for j,r in enumerate(rels): add_event(e,f'{i}-{j}',nodes[j],r,nodes[j+1],confidence=cs[j])
    ans,f,_=walk_result(e,nodes[0],rels,algebra=MAX_MIN); expected=min(cs); actual=f.get(nodes[-1])
    return CaseResult(ans.status=='ANSWER' and abs(actual-expected)<1e-12, {'status':'ANSWER','support':expected},{'status':ans.status,'support':actual})

def cat27(rng,i):
    from srmh.engine import Engine
    from srmh.algebra import MAX_MIN
    e=Engine(); s,a,b,z=make_labels(rng,'n',4); r1,r2=make_labels(rng,'r',2); c=[rng.uniform(.1,1) for _ in range(4)]
    add_event(e,f'{i}0',s,r1,a,confidence=c[0]); add_event(e,f'{i}1',a,r2,z,confidence=c[1]); add_event(e,f'{i}2',s,r1,b,confidence=c[2]); add_event(e,f'{i}3',b,r2,z,confidence=c[3])
    ans,f,_=walk_result(e,s,[r1,r2],algebra=MAX_MIN); expected=max(min(c[0],c[1]),min(c[2],c[3])); actual=f.get(z)
    return CaseResult(ans.status=='ANSWER' and abs(actual-expected)<1e-12,{'support':expected},{'status':ans.status,'support':actual})

def cat28(rng,i):
    from srmh.engine import Engine
    e=Engine(); s=make_labels(rng,'s',1)[0]; ans,f,_=walk_result(e,s,[])
    exp={'status':'ANSWER','frontier':{s:1.0}}; act={'status':ans.status,'frontier':f}; return CaseResult(exp==act,exp,act)

def cat29(rng,i):
    from srmh.algebra import Graph, MAX_MIN
    g=Graph(); r=make_labels(rng,'r',1)[0]; f,_=g.propagate({},[r,r],MAX_MIN); return CaseResult(f=={}, {}, f)

def cat30(rng,i):
    from srmh.engine import Engine
    e=Engine(); length=[1000,5000,10000,25000,50000][i%5]; r=make_labels(rng,'r',1)[0]
    # Compact deterministic node IDs to avoid RNG overhead dominating.
    for j in range(length): add_event(e,f'e{j}',f'n{j}',r,f'n{j+1}')
    ans,_,meta=walk_result(e,'n0',[r]*length); return check_answer(ans,'ANSWER',[f'n{length}'])

def cat31(rng,i):
    from srmh.engine import Engine
    e=Engine(['f']); s=make_labels(rng,'s',1)[0]; a,b=make_labels(rng,'v',2); r='f'
    add_event(e,f'{i}a',s,r,a,1); add_event(e,f'{i}b',s,r,b,2); ans,_,_=walk_result(e,s,[r],time=2); return check_answer(ans,'ANSWER',[b])

def cat32(rng,i):
    from srmh.engine import Engine
    e=Engine(['f']); s=make_labels(rng,'s',1)[0]; a,b=make_labels(rng,'v',2); add_event(e,f'{i}a',s,'f',a,1); add_event(e,f'{i}b',s,'f',b,3)
    ans,_,_=walk_result(e,s,['f'],time=2); return check_answer(ans,'ANSWER',[a])

def cat33(rng,i):
    from srmh.engine import Engine
    e=Engine(); s,o=make_labels(rng,'n',2); r='r'; add_event(e,f'{i}a',s,r,o,1); add_event(e,f'{i}x',s,r,o,2,operation='RETRACT')
    ans,_,_=walk_result(e,s,[r],time=3); return check_answer(ans,'UNKNOWN',[])

def cat34(rng,i):
    from srmh.engine import Engine
    e=Engine(); s,o=make_labels(rng,'n',2); r='r'; add_event(e,f'{i}a',s,r,o,1); add_event(e,f'{i}x',s,r,o,2,operation='RETRACT'); add_event(e,f'{i}b',s,r,o,3)
    ans,_,_=walk_result(e,s,[r],time=4); return check_answer(ans,'ANSWER',[o])

def cat35(rng,i):
    from srmh.engine import Engine
    e=Engine(['f']); s=make_labels(rng,'s',1)[0]; vals=make_labels(rng,'v',5)
    for j,v in enumerate(vals,1): add_event(e,f'{i}-{j}',s,'f',v,j)
    ans,_,_=walk_result(e,s,['f'],time=6); return check_answer(ans,'ANSWER',[vals[-1]])

def cat36(rng,i):
    from srmh.engine import Engine
    from srmh import Event
    e=Engine(['f']); s=make_labels(rng,'s',1)[0]; vals=make_labels(rng,'v',6); events=[Event(f'{i}-{j}',s,'f',v,float(j)) for j,v in enumerate(vals,1)]; rng.shuffle(events)
    for ev in events: e.ledger.add(ev)
    ans,_,_=walk_result(e,s,['f'],time=7); return check_answer(ans,'ANSWER',[vals[-1]])

def cat37(rng,i):
    from srmh.engine import Engine
    e=Engine(['f']); s=make_labels(rng,'s',1)[0]; a,b=make_labels(rng,'v',2); add_event(e,f'{i}a',s,'f',a,1); add_event(e,f'{i}b',s,'f',b,1)
    ans,_,_=walk_result(e,s,['f'],time=1); return check_answer(ans,'AMBIGUOUS',[a,b])

def cat38(rng,i):
    from srmh.engine import Engine
    e=Engine(['f']); s=make_labels(rng,'s',1)[0]; a,b=make_labels(rng,'v',2); add_event(e,f'{i}a',s,'f',a,1); before=walk_result(e,s,['f'],time=1)[0]; add_event(e,f'{i}b',s,'f',b,10); after=walk_result(e,s,['f'],time=1)[0]
    exp=exact_answer('ANSWER',[a]); act={'before': {'status':before.status,'values':tuple(before.values)}, 'after': {'status':after.status,'values':tuple(after.values)}}
    ok=act['before']==exp and act['after']==exp; return CaseResult(ok,{'before':exp,'after':exp},act)

def cat39(rng,i):
    from srmh.engine import Engine
    e=Engine(['f']); a,b,c,d=make_labels(rng,'n',4); r1,r2=make_labels(rng,'r',2)
    # At t=1 path is a->b->d; at t=3 first leg superseded to c and c->d exists.
    add_event(e,f'{i}1',a,r1,b,1); add_event(e,f'{i}2',b,r2,d,1); add_event(e,f'{i}3',a,r1,c,3); add_event(e,f'{i}4',c,r2,d,2)
    # mark r1 functional via dedicated engine? rebuild because chosen rel random
    e.ledger.functional=frozenset([r1])
    ans1,_,_=walk_result(e,a,[r1,r2],time=2); ans2,_,_=walk_result(e,a,[r1,r2],time=4)
    exp=exact_answer('ANSWER',[d]); act={'t2':{'status':ans1.status,'values':tuple(ans1.values)},'t4':{'status':ans2.status,'values':tuple(ans2.values)}}
    return CaseResult(act['t2']==exp and act['t4']==exp,{'t2':exp,'t4':exp},act)

def cat40(rng,i):
    from srmh.engine import Engine
    e=Engine(['f']); s,a,b=make_labels(rng,'n',3); add_event(e,f'{i}a',s,'f',a,5); add_event(e,f'{i}b',s,'f',b,10)
    for j in range(100): x,y=make_labels(rng,'d',2); add_event(e,f'{i}d{j}',x,'f',y,rng.randint(0,20))
    ans,_,_=walk_result(e,s,['f'],time=7); return check_answer(ans,'ANSWER',[a])

def cat41(rng,i):
    from srmh.engine import Engine
    e=Engine(); s,o=make_labels(rng,'n',2); r='r'; add_event(e,i,s,r,o,1,positive=False); ans,_,_=walk_result(e,s,[r],time=2); return check_answer(ans,'NEGATED',[])

def cat42(rng,i):
    from srmh.engine import Engine
    e=Engine(); s,o=make_labels(rng,'n',2); r='r'; add_event(e,f'{i}p',s,r,o,1,positive=True); add_event(e,f'{i}n',s,r,o,1,positive=False); ans,_,_=walk_result(e,s,[r],time=2); return check_answer(ans,'CONTRADICTED',[o])

def cat43(rng,i):
    from srmh.engine import Engine
    e=Engine(); root,bad,good,z,x=make_labels(rng,'n',5); r1,r2=make_labels(rng,'r',2)
    add_event(e,f'{i}1',root,r1,bad); add_event(e,f'{i}2',root,r1,good)
    add_event(e,f'{i}3',bad,r2,x,positive=True); add_event(e,f'{i}4',bad,r2,x,positive=False)
    add_event(e,f'{i}5',good,r2,z,positive=True)
    # Contradiction is on a branch that produces x; to make it irrelevant to the requested final value, add a third relation only z can traverse.
    r3=make_labels(rng,'r',1)[0]; end=make_labels(rng,'end',1)[0]; add_event(e,f'{i}6',z,r3,end)
    ans,_,_=walk_result(e,root,[r1,r2,r3]); return check_answer(ans,'ANSWER',[end])

def cat44(rng,i):
    from srmh.engine import Engine
    e=Engine(); s,a,z=make_labels(rng,'n',3); r1,r2=make_labels(rng,'r',2); add_event(e,f'{i}1',s,r1,a); add_event(e,f'{i}2',a,r2,z,positive=True); add_event(e,f'{i}3',a,r2,z,positive=False)
    ans,_,_=walk_result(e,s,[r1,r2]); return check_answer(ans,'CONTRADICTED',[z])

def cat45(rng,i):
    from srmh.engine import Engine
    e=Engine(['f']); s,a,b=make_labels(rng,'n',3); add_event(e,f'{i}1',s,'f',a,1); add_event(e,f'{i}2',s,'f',b,2); add_event(e,f'{i}3',s,'f',b,3,positive=False)
    ans,_,_=walk_result(e,s,['f'],time=4); return check_answer(ans,'CONTRADICTED',[b])

def ambig_base(rng,i,mode):
    from srmh.engine import Engine
    e=Engine(['f']); s,a,b=make_labels(rng,'n',3); add_event(e,f'{i}a',s,'f',a,1); add_event(e,f'{i}b',s,'f',b,1); r='m'
    if mode=='converge':
        z=make_labels(rng,'z',1)[0]; add_event(e,f'{i}1',a,r,z); add_event(e,f'{i}2',b,r,z); expected=('ANSWER',[z])
    elif mode=='diverge':
        z1,z2=make_labels(rng,'z',2); add_event(e,f'{i}1',a,r,z1); add_event(e,f'{i}2',b,r,z2); expected=('AMBIGUOUS',[z1,z2])
    elif mode=='one_dies':
        z=make_labels(rng,'z',1)[0]; add_event(e,f'{i}1',a,r,z); expected=('AMBIGUOUS',[z])
    elif mode=='all_die': expected=('UNKNOWN',[])
    ans,_,_=walk_result(e,s,['f',r]); return check_answer(ans,*expected)

def cat46(rng,i): return ambig_base(rng,i,'converge')
def cat47(rng,i): return ambig_base(rng,i,'diverge')
def cat48(rng,i): return ambig_base(rng,i,'one_dies')
def cat49(rng,i): return ambig_base(rng,i,'all_die')

def cat50(rng,i):
    from srmh.engine import Engine
    e=Engine(['f1','f2']); s,a,b,c,d,z=make_labels(rng,'n',6)
    add_event(e,f'{i}1',s,'f1',a,1); add_event(e,f'{i}2',s,'f1',b,1)
    add_event(e,f'{i}3',a,'f2',c,1); add_event(e,f'{i}4',a,'f2',d,1); add_event(e,f'{i}5',b,'f2',c,1); add_event(e,f'{i}6',b,'f2',d,1)
    add_event(e,f'{i}7',c,'r',z,1); add_event(e,f'{i}8',d,'r',z,1)
    ans,_,_=walk_result(e,s,['f1','f2','r']); return check_answer(ans,'ANSWER',[z])

def cat51(rng,i):
    from srmh.engine import Engine
    from srmh import Event
    s=make_labels(rng,'s',1)[0]; vals=make_labels(rng,'v',5); events=[Event(f'{i}-{j}',s,'f',v,float(j)) for j,v in enumerate(vals,1)]
    outputs=[]
    for k in range(4):
        e=Engine(['f']); shuffled=list(events); rng.shuffle(shuffled)
        for ev in shuffled:e.ledger.add(ev)
        a,_,_=walk_result(e,s,['f'],time=6); outputs.append((a.status,a.values))
    exp=('ANSWER',(vals[-1],)); return CaseResult(all(o==exp for o in outputs),[exp]*4,outputs)

def cat52(rng,i):
    from srmh.engine import Engine
    rels=make_labels(rng,'r',4); nodes=make_labels(rng,'n',5)
    e1=Engine();
    for j,r in enumerate(rels): add_event(e1,f'{i}a{j}',nodes[j],r,nodes[j+1])
    a1,_,_=walk_result(e1,nodes[0],rels)
    # bijective opaque rename
    nodes2=make_labels(rng,'X',5); rels2=make_labels(rng,'Q',4); e2=Engine()
    for j,r in enumerate(rels2): add_event(e2,f'{i}b{j}',nodes2[j],r,nodes2[j+1])
    a2,_,_=walk_result(e2,nodes2[0],rels2)
    ok=a1.status=='ANSWER' and a1.values==(nodes[-1],) and a2.status=='ANSWER' and a2.values==(nodes2[-1],)
    return CaseResult(ok,{'orig':nodes[-1],'renamed':nodes2[-1]},{'orig':a1.values,'renamed':a2.values,'statuses':(a1.status,a2.status)})

def cat53(rng,i):
    from srmh.engine import Engine
    size=[0,10,100,1000,5000][i%5]; e=Engine(); nodes=make_labels(rng,'n',4); rels=make_labels(rng,'r',3)
    for j,r in enumerate(rels): add_event(e,f'{i}g{j}',nodes[j],r,nodes[j+1])
    for j in range(size): x,y=make_labels(rng,'d',2); add_event(e,f'{i}d{j}',x,rels[j%3],y)
    t=time.perf_counter(); ans,_,_=walk_result(e,nodes[0],rels); dt=time.perf_counter()-t
    cr=check_answer(ans,'ANSWER',[nodes[-1]]); cr.note=f'distractors={size};query_s={dt:.6f}'; return cr

def cat54(rng,i):
    from srmh.engine import Engine
    # Counterfactual supplied as an explicit hypothetical event set in a separate engine.
    s,a,b,z1,z2=make_labels(rng,'n',5); r1,r2=make_labels(rng,'r',2)
    base=Engine(['f']); add_event(base,f'{i}1',s,'f',a,1); add_event(base,f'{i}2',a,r2,z1,1); add_event(base,f'{i}3',b,r2,z2,1)
    actual=walk_result(base,s,['f',r2],time=2)[0]
    cf=Engine(['f']); add_event(cf,f'{i}1',s,'f',a,1); add_event(cf,f'{i}4',s,'f',b,2); add_event(cf,f'{i}2',a,r2,z1,1); add_event(cf,f'{i}3',b,r2,z2,1)
    hypothetical=walk_result(cf,s,['f',r2],time=3)[0]
    ok=(actual.status,actual.values)==('ANSWER',(z1,)) and (hypothetical.status,hypothetical.values)==('ANSWER',(z2,))
    return CaseResult(ok,{'actual':z1,'counterfactual':z2},{'actual':(actual.status,actual.values),'counterfactual':(hypothetical.status,hypothetical.values)})

def cat55(rng,i):
    from srmh.engine import Engine
    e=Engine(); s=make_labels(rng,'s',1)[0]; z=make_labels(rng,'z',1)[0]; r1,r2=make_labels(rng,'r',2); mids=make_labels(rng,'m',rng.randint(3,7))
    for j,m in enumerate(mids): add_event(e,f'{i}a{j}',s,r1,m); add_event(e,f'{i}b{j}',m,r2,z)
    ans,_,meta=walk_result(e,s,[r1,r2],proof=True)
    # Keep the full layered DAG, but require an independently usable minimal witness.
    proof_edges=meta.get('minimal_witness_edges')
    exp={'status':'ANSWER','value':z,'minimal_witness_edges':2}; act={'status':ans.status,'value':ans.values,'minimal_witness_edges':proof_edges,'full_proof_nodes':meta.get('proof_nodes')}
    return CaseResult(ans.status=='ANSWER' and ans.values==(z,) and proof_edges==2,exp,act)

def cat56(rng,i):
    from srmh.engine import Engine
    e=Engine(); a,b,c,d,u,v=make_labels(rng,'n',6); r1,r2,r3=make_labels(rng,'r',3)
    add_event(e,f'{i}1',a,r1,b,1); add_event(e,f'{i}2',b,r2,c,1); add_event(e,f'{i}3',c,r3,d,1); add_event(e,f'{i}u',u,r1,v,1)
    before=walk_result(e,a,[r1,r2,r3],time=1)[0]; add_event(e,f'{i}x',b,r2,c,2,operation='RETRACT'); after=walk_result(e,a,[r1,r2,r3],time=3)[0]; unaffected=walk_result(e,u,[r1],time=3)[0]
    ok=(before.status,before.values)==('ANSWER',(d,)) and after.status=='UNKNOWN' and (unaffected.status,unaffected.values)==('ANSWER',(v,))
    return CaseResult(ok,{'before':d,'after':'UNKNOWN','unaffected':v},{'before':(before.status,before.values),'after':(after.status,after.values),'unaffected':(unaffected.status,unaffected.values)})

def cat57(rng,i):
    from srmh.engine import Engine
    from srmh import Event
    s=make_labels(rng,'s',1)[0]; vals=make_labels(rng,'v',5); events=[Event(f'{i}-{j}',s,'f',v,float(j)) for j,v in enumerate(vals,1)]
    chronological=Engine(['f']); replay=Engine(['f'])
    for ev in events: chronological.ledger.add(ev)
    shuffled=list(events); rng.shuffle(shuffled)
    for ev in shuffled: replay.ledger.add(ev)
    outs1=[];outs2=[]
    for t in range(1,6):
        a1,_,_=walk_result(chronological,s,['f'],time=t); a2,_,_=walk_result(replay,s,['f'],time=t); outs1.append((a1.status,a1.values));outs2.append((a2.status,a2.values))
    return CaseResult(outs1==outs2,outs1,outs2)

def cat58(rng,i):
    from srmh.engine import Engine
    # Relation names and combinations are newly generated every case; no training or macro examples.
    e=Engine(); rel_pool=make_labels(rng,'r',8); rels=[rng.choice(rel_pool) for _ in range(6)]; nodes=make_labels(rng,'n',7)
    for j,r in enumerate(rels): add_event(e,f'{i}-{j}',nodes[j],r,nodes[j+1])
    ans,_,_=walk_result(e,nodes[0],rels); return check_answer(ans,'ANSWER',[nodes[-1]])

def cat59(rng,i):
    from srmh.algebra import join
    # Exact intersection encoded as natural join over shared variable ?x.
    universe=make_labels(rng,'e',12); target=rng.choice(universe)
    red=set(rng.sample(universe,5)); red.add(target)
    metal=set(rng.sample(universe,5)); metal.add(target)
    owned=set(rng.sample(universe,5)); owned.add(target)
    # Force target to be unique intersection.
    for x in list((red&metal&owned)-{target}): owned.discard(x)
    tables=[[{'?x':x,'red':True} for x in red],[{'?x':x,'metal':True} for x in metal],[{'?x':x,'owned':True} for x in owned]]
    rows=join(tables); vals={row['?x'] for row in rows}; exp={target}; return CaseResult(vals==exp,sorted(exp),sorted(vals))

def cat60(rng,i):
    from srmh.engine import Engine
    e=Engine(); s,g1,g2,z=make_labels(rng,'n',4); rels=make_labels(rng,'r',3); add_event(e,f'{i}g0',s,rels[0],g1); add_event(e,f'{i}g1',g1,rels[1],g2); add_event(e,f'{i}g2',g2,rels[2],z)
    # Structurally similar decoys match the first two relation steps and fail only on the final one.
    for j in range(100):
        a,b=make_labels(rng,'d',2); add_event(e,f'{i}d{j}a',s,rels[0],a); add_event(e,f'{i}d{j}b',a,rels[1],b)
        if j%3==0: add_event(e,f'{i}d{j}c',b,make_labels(rng,'wrong',1)[0],make_labels(rng,'w',1)[0])
    ans,_,_=walk_result(e,s,rels); return check_answer(ans,'ANSWER',[z])

CATEGORIES = {
1:("Direct fact retrieval",cat01,100), 2:("Missing fact / UNKNOWN",cat02,100), 3:("One-hop distractor filtering",cat03,100),
4:("Two-hop composition",cat04,100), 5:("Three-hop composition",cat05,100), 6:("Variable-length composition",cat06,100),
7:("Repeated-relation chains",cat07,100), 8:("Mixed-relation chains",cat08,100), 9:("Branch-and-select",cat09,100),
10:("Reconverging paths",cat10,100), 11:("Cycles",cat11,100), 12:("Self-loops",cat12,100), 13:("Duplicate evidence edges",cat13,100),
14:("Disconnected components",cat14,100), 15:("High branching factor",cat15,100), 16:("Deep narrow chains",cat16,100),
17:("Needle-in-haystack graph",cat17,100), 18:("Multiple correct destinations",cat18,100), 19:("Dead-end branches",cat19,100), 20:("Diamond graphs",cat20,100),
21:("Boolean reachability",cat21,100), 22:("Exact COUNT",cat22,100), 23:("COUNT with reconvergence",cat23,100), 24:("MIN_PLUS shortest path",cat24,100),
25:("Equal-cost shortest paths",cat25,100), 26:("MAX_MIN support propagation",cat26,100), 27:("Competing MAX_MIN paths",cat27,100),
28:("Zero-hop identity",cat28,100), 29:("Empty frontier propagation",cat29,100), 30:("Very long hop test",cat30,5),
31:("Simple supersession",cat31,100), 32:("Historical lookup",cat32,100), 33:("Retraction",cat33,100), 34:("Retract then reassert",cat34,100),
35:("Multiple supersessions",cat35,100), 36:("Out-of-order insertion",cat36,100), 37:("Same-time functional conflict",cat37,100),
38:("Future-event isolation",cat38,100), 39:("Temporal multi-hop reasoning",cat39,100), 40:("Temporal distractors",cat40,100),
41:("Explicit negation",cat41,100), 42:("Positive + negative contradiction",cat42,100), 43:("Irrelevant contradiction branch",cat43,100),
44:("Contradiction on required path",cat44,100), 45:("Negative evidence after supersession",cat45,100),
46:("Ambiguous branches converge",cat46,100), 47:("Ambiguous branches diverge",cat47,100), 48:("One ambiguous branch dies",cat48,100),
49:("All ambiguous branches die",cat49,100), 50:("Multiple independent ambiguities",cat50,100),
51:("Permutation invariance",cat51,100), 52:("Entity renaming invariance",cat52,100), 53:("Distractor scaling curve",cat53,25),
54:("Counterfactual state substitution",cat54,100), 55:("Minimal-proof recovery",cat55,100), 56:("Exact dependency invalidation",cat56,100),
57:("Historical replay invariance",cat57,100), 58:("Combinatorial recombination",cat58,100), 59:("Constraint intersection",cat59,100),
60:("Adversarial irrelevant similarity",cat60,100),
}


def run(root, outpath, only=None):
    sys.path.insert(0,str(Path(root).resolve()))
    selected=[x for x in range(1,61) if only is None or x in only]
    report={'root':str(Path(root).resolve()),'seed_policy':'1000003 + category*10007 + case','categories':{},'started':time.time()}
    total=passed=0
    for idx in selected:
        name,fn,count=CATEGORIES[idx]
        cpass=0; failures=[]; t0=time.perf_counter(); notes=[]
        for i in range(count):
            rng=random.Random(1000003 + idx*10007 + i)
            try:
                r=fn(rng,i)
            except Exception as ex:
                r=CaseResult(False,'no exception',{'exception':type(ex).__name__,'message':str(ex),'traceback':traceback.format_exc(limit=5)})
            total+=1
            if r.ok: passed+=1;cpass+=1
            elif len(failures)<5: failures.append({'case':i,'expected':r.expected,'actual':r.actual,'note':r.note})
            if r.note: notes.append(r.note)
        report['categories'][str(idx)]={'name':name,'cases':count,'passed':cpass,'failed':count-cpass,'seconds':time.perf_counter()-t0,'examples':failures,'notes':notes[:10]}
        print(f'{idx:02d} {name:<38} {cpass:>3}/{count:<3}  {report["categories"][str(idx)]["seconds"]:.3f}s')
    report['total_cases']=total;report['passed']=passed;report['failed']=total-passed;report['seconds']=time.time()-report['started']
    Path(outpath).write_text(json.dumps(report,indent=2,sort_keys=False))
    print(f'\nTOTAL {passed}/{total} passed; {total-passed} failed; {report["seconds"]:.2f}s')
    return 0 if passed==total else 1

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('root');ap.add_argument('--out',required=True);ap.add_argument('--only',nargs='*',type=int)
    args=ap.parse_args();raise SystemExit(run(args.root,args.out,set(args.only) if args.only else None))
