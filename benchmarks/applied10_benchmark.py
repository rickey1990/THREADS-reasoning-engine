#!/usr/bin/env python3
import json, random, time, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'source'
sys.path.insert(0, str(ROOT))
from srmh.engine import Engine
from srmh.ledger import Event
from srmh.algebra import BOOLEAN

SEED = 260906
rng = random.Random(SEED)


def ev(i, s, r, o, t, *, context='default', operation='ASSERT', target=None, positive=True, source='generated'):
    return Event(id=i, subject=s, relation=r, object=o, time=t, context=context,
                 operation=operation, target=target, positive=positive, source=source)

def walk(e, s, rels, t, *, context='default', proof=False):
    return e.walk(s, rels, time=t, context=context, algebra=BOOLEAN, proof=proof)

def valset(ans):
    return set(ans.values)

def witness_ids(meta):
    out = set()
    mw = meta.get('minimal_witness') or {}
    for path in mw.values():
        for edge in path:
            out.update(edge[4])
    return out

class Score:
    def __init__(self, name, claim):
        self.name=name; self.claim=claim; self.cases=0; self.checks=0; self.passed=0; self.failures=[]; self.elapsed=0.0
    def check(self, ok, detail):
        self.checks += 1
        if ok: self.passed += 1
        elif len(self.failures) < 10: self.failures.append(detail)
    def result(self):
        return {
            'name': self.name, 'claim': self.claim, 'cases': self.cases,
            'checks': self.checks, 'passed': self.passed,
            'failed': self.checks-self.passed, 'pass_rate': self.passed/self.checks if self.checks else 0,
            'elapsed_s': self.elapsed, 'failures': self.failures,
        }

def test1_memory():
    sc=Score('Correctable AI/customer memory','Current and historical memory remain exact through correction, retraction, and re-learning.')
    t0=time.perf_counter(); e=Engine(functional={'preference'})
    for i in range(100):
        u=f'user{i}'; a=f'channel_old_{i}'; b=f'channel_new_{i}'; c=f'channel_relearned_{i}'
        e1=f'm{i}_1'; e2=f'm{i}_2'; e3=f'm{i}_3'; e4=f'm{i}_4'
        e.ledger.add(ev(e1,u,'preference',a,10))
        e.ledger.add(ev(e2,u,'preference',b,20))
        e.ledger.add(ev(e3,u,'preference',b,30,operation='RETRACT',target=e2))
        e.ledger.add(ev(e4,u,'preference',c,40))
        for qt,st,v in [(15,'ANSWER',{a}),(25,'ANSWER',{b}),(35,'UNKNOWN',set()),(45,'ANSWER',{c})]:
            ans,_,_=walk(e,u,['preference'],qt)
            sc.check(ans.status==st and valset(ans)==v, {'case':i,'time':qt,'got':[ans.status,ans.values],'expected':[st,sorted(v)]})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

def test2_entitlements():
    sc=Score('Access control and entitlement revocation','A revoked grant immediately breaks authorization while the earlier authorized state remains historically queryable.')
    t0=time.perf_counter(); e=Engine()
    for i in range(100):
        u=f'employee{i}'; role=f'role{i}'; perm=f'perm{i}'; resource=f'resource{i}'
        ids=[f'a{i}_role',f'a{i}_grant',f'a{i}_scope']
        e.ledger.add(ev(ids[0],u,'has_role',role,10))
        e.ledger.add(ev(ids[1],role,'grants',perm,10))
        e.ledger.add(ev(ids[2],perm,'scope',resource,10))
        # unrelated corporate ACL facts
        for j in range(12):
            e.ledger.add(ev(f'a{i}_d{j}',f'other{i}_{j}','has_role',f'orole{i}_{j}',10))
        ans,_,_=walk(e,u,['has_role','grants','scope'],15)
        sc.check(ans.status=='ANSWER' and valset(ans)=={resource},{'case':i,'phase':'before','got':[ans.status,ans.values]})
        e.ledger.add(ev(f'a{i}_revoke',role,'grants',perm,20,operation='RETRACT',target=ids[1]))
        ans_now,_,_=walk(e,u,['has_role','grants','scope'],25)
        ans_old,_,_=walk(e,u,['has_role','grants','scope'],15)
        sc.check(ans_now.status=='UNKNOWN' and not ans_now.values,{'case':i,'phase':'revoked','got':[ans_now.status,ans_now.values]})
        sc.check(ans_old.status=='ANSWER' and valset(ans_old)=={resource},{'case':i,'phase':'history','got':[ans_old.status,ans_old.values]})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

def test3_compliance():
    sc=Score('Compliance conflict and abstention','The engine distinguishes definite policy outcomes, contradictions, convergent alternatives, and genuine unresolved conflicts without guessing.')
    t0=time.perf_counter(); e=Engine(functional={'decision'})
    for i in range(100):
        case=i%4; s=f'case{i}'
        if case==0:
            d=f'allow{i}'; e.ledger.add(ev(f'c{i}a',s,'decision',d,10)); e.ledger.add(ev(f'c{i}b',d,'effect','PERMIT',10)); exp=('ANSWER',{'PERMIT'})
        elif case==1:
            a=f'pathA{i}'; b=f'pathB{i}'
            e.ledger.add(ev(f'c{i}a',s,'decision',a,10)); e.ledger.add(ev(f'c{i}b',s,'decision',b,10))
            e.ledger.add(ev(f'c{i}c',a,'effect','REVIEW',10)); e.ledger.add(ev(f'c{i}d',b,'effect','REVIEW',10)); exp=('ANSWER',{'REVIEW'})
        elif case==2:
            a=f'pathA{i}'; b=f'pathB{i}'
            e.ledger.add(ev(f'c{i}a',s,'decision',a,10)); e.ledger.add(ev(f'c{i}b',s,'decision',b,10))
            e.ledger.add(ev(f'c{i}c',a,'effect','PERMIT',10)); e.ledger.add(ev(f'c{i}d',b,'effect','BLOCK',10)); exp=('AMBIGUOUS',{'PERMIT','BLOCK'})
        else:
            a=f'allow{i}'
            e.ledger.add(ev(f'c{i}a',s,'decision',a,10,positive=True)); e.ledger.add(ev(f'c{i}n',s,'decision',a,10,positive=False))
            e.ledger.add(ev(f'c{i}e',a,'effect','PERMIT',10)); exp=('CONTRADICTED',{'PERMIT'})
        ans,_,_=walk(e,s,['decision','effect'],15)
        sc.check(ans.status==exp[0] and valset(ans)==exp[1],{'case':i,'got':[ans.status,ans.values],'expected':[exp[0],sorted(exp[1])]})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

def test4_workflow():
    sc=Score('Workflow dependency invalidation','A broken prerequisite invalidates dependent completion, but pre-change history remains exact.')
    t0=time.perf_counter(); e=Engine()
    for i in range(100):
        nodes=[f'w{i}_{j}' for j in range(6)]; ids=[]
        for j in range(5):
            eid=f'w{i}_e{j}'; ids.append(eid); e.ledger.add(ev(eid,nodes[j],'depends_on',nodes[j+1],10))
        e.ledger.add(ev(f'w{i}_state',nodes[-1],'state','READY',10))
        rels=['depends_on']*5+['state']
        a,_,_=walk(e,nodes[0],rels,15); sc.check(a.status=='ANSWER' and valset(a)=={'READY'},{'case':i,'phase':'before','got':[a.status,a.values]})
        e.ledger.add(ev(f'w{i}_ret',nodes[2],'depends_on',nodes[3],20,operation='RETRACT',target=ids[2]))
        n,_,_=walk(e,nodes[0],rels,25); h,_,_=walk(e,nodes[0],rels,15)
        sc.check(n.status=='UNKNOWN' and not n.values,{'case':i,'phase':'after','got':[n.status,n.values]})
        sc.check(h.status=='ANSWER' and valset(h)=={'READY'},{'case':i,'phase':'history','got':[h.status,h.values]})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

def test5_rag_provenance():
    sc=Score('RAG / AI answer provenance','A corrected retrieved claim changes the answer and the minimal witness cites only the evidence supporting that temporal answer.')
    t0=time.perf_counter(); e=Engine(functional={'selected_claim'})
    for i in range(100):
        q=f'question{i}'; old=f'claim_old{i}'; new=f'claim_new{i}'; oa=f'answer_old{i}'; na=f'answer_new{i}'
        ids={'sel_old':f'r{i}_so','ent_old':f'r{i}_eo','sel_new':f'r{i}_sn','ent_new':f'r{i}_en'}
        e.ledger.add(ev(ids['sel_old'],q,'selected_claim',old,10,source='doc_old'))
        e.ledger.add(ev(ids['ent_old'],old,'entails',oa,10,source='doc_old'))
        e.ledger.add(ev(ids['sel_new'],q,'selected_claim',new,20,source='doc_new'))
        e.ledger.add(ev(ids['ent_new'],new,'entails',na,20,source='doc_new'))
        # noisy retrieval corpus not connected to this query
        for j in range(8):
            e.ledger.add(ev(f'r{i}_d{j}',f'noise_claim{i}_{j}','entails',f'noise_answer{i}_{j}',15,source='noise'))
        old_ans,_,old_meta=walk(e,q,['selected_claim','entails'],15,proof=True)
        new_ans,_,new_meta=walk(e,q,['selected_claim','entails'],25,proof=True)
        sc.check(old_ans.status=='ANSWER' and valset(old_ans)=={oa},{'case':i,'phase':'old_answer','got':[old_ans.status,old_ans.values]})
        sc.check(new_ans.status=='ANSWER' and valset(new_ans)=={na},{'case':i,'phase':'new_answer','got':[new_ans.status,new_ans.values]})
        sc.check(witness_ids(old_meta)=={ids['sel_old'],ids['ent_old']},{'case':i,'phase':'old_proof','ids':sorted(witness_ids(old_meta))})
        sc.check(witness_ids(new_meta)=={ids['sel_new'],ids['ent_new']},{'case':i,'phase':'new_proof','ids':sorted(witness_ids(new_meta))})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

def test6_incident():
    sc=Score('Incident dependency / resilience analysis','Redundant impact paths preserve an affected conclusion after one path is removed, then disappear when all supporting paths are removed.')
    t0=time.perf_counter(); e=Engine()
    for i in range(100):
        root=f'incident{i}'; a=f'svcA{i}'; b=f'svcB{i}'; c=f'svcC{i}'; d=f'svcD{i}'; target=f'customer_impact{i}'
        ids={}
        for key,s,o in [('ra',root,a),('rb',root,b),('ac',a,c),('bd',b,d),('ct',c,target),('dt',d,target)]:
            ids[key]=f'i{i}_{key}'; e.ledger.add(ev(ids[key],s,'impacts',o,10))
        for j in range(12): e.ledger.add(ev(f'i{i}_noise{j}',f'noise{i}_{j}','impacts',f'noise{i}_{j+1}',10))
        rels=['impacts']*3
        x,_,_=walk(e,root,rels,15); sc.check(x.status=='ANSWER' and valset(x)=={target},{'case':i,'phase':'both','got':[x.status,x.values]})
        e.ledger.add(ev(f'i{i}_r1',b,'impacts',d,20,operation='RETRACT',target=ids['bd']))
        y,_,_=walk(e,root,rels,25); sc.check(y.status=='ANSWER' and valset(y)=={target},{'case':i,'phase':'one_path','got':[y.status,y.values]})
        e.ledger.add(ev(f'i{i}_r2',a,'impacts',c,30,operation='RETRACT',target=ids['ac']))
        z,_,_=walk(e,root,rels,35); sc.check(z.status=='UNKNOWN' and not z.values,{'case':i,'phase':'none','got':[z.status,z.values]})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

def test7_lineage():
    sc=Score('Data lineage and source correction','A report traces to all exact sources, and a source correction changes only the affected lineage while historical lineage remains intact.')
    t0=time.perf_counter(); e=Engine(functional={'sourced_from'})
    for i in range(100):
        report=f'report{i}'; datasets=[f'ds{i}_{j}' for j in range(3)]; oldsrc=[f'source{i}_{j}' for j in range(3)]; newsrc=f'source{i}_replacement'
        for j,ds in enumerate(datasets):
            e.ledger.add(ev(f'l{i}_d{j}',report,'derived_from',ds,10)); e.ledger.add(ev(f'l{i}_s{j}',ds,'sourced_from',oldsrc[j],10))
        e.ledger.add(ev(f'l{i}_new',datasets[1],'sourced_from',newsrc,20))
        old,_,_=walk(e,report,['derived_from','sourced_from'],15)
        new,_,_=walk(e,report,['derived_from','sourced_from'],25)
        sc.check(old.status=='ANSWER' and valset(old)==set(oldsrc),{'case':i,'phase':'history','got':[old.status,old.values]})
        expected={oldsrc[0],newsrc,oldsrc[2]}
        sc.check(new.status=='ANSWER' and valset(new)==expected,{'case':i,'phase':'current','got':[new.status,new.values],'expected':sorted(expected)})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

def test8_contexts():
    sc=Score('Multi-tenant / environment isolation','Identical entity IDs in different contexts retain independent histories and updates with no state leakage.')
    t0=time.perf_counter(); e=Engine(functional={'plan'})
    for i in range(100):
        account=f'account{i}'; ca=f'tenantA_{i}'; cb=f'tenantB_{i}'
        e.ledger.add(ev(f'x{i}_a1',account,'plan','GOLD',10,context=ca)); e.ledger.add(ev(f'x{i}_b1',account,'plan','BASIC',10,context=cb)); e.ledger.add(ev(f'x{i}_a2',account,'plan','ENTERPRISE',20,context=ca))
        q=[(ca,15,'ANSWER',{'GOLD'}),(ca,25,'ANSWER',{'ENTERPRISE'}),(cb,25,'ANSWER',{'BASIC'}),('default',25,'UNKNOWN',set())]
        for ctx,qt,st,vals in q:
            ans,_,_=walk(e,account,['plan'],qt,context=ctx)
            sc.check(ans.status==st and valset(ans)==vals,{'case':i,'context':ctx,'time':qt,'got':[ans.status,ans.values]})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

def test9_supply_chain():
    sc=Score('Supply-chain recall tracing','A recalled supplier is found through many product components; safe products abstain, and a withdrawn recall stops propagating immediately.')
    t0=time.perf_counter(); e=Engine(functional={'supplied_by'})
    for i in range(100):
        product=f'product{i}'; risky=i<50; recall_id=None
        for j in range(20):
            comp=f'component{i}_{j}'; supplier=f'supplier{i}_{j}'
            e.ledger.add(ev(f's{i}_c{j}',product,'contains',comp,10)); e.ledger.add(ev(f's{i}_p{j}',comp,'supplied_by',supplier,10))
            if risky and j==13:
                recall_id=f's{i}_recall'; e.ledger.add(ev(recall_id,supplier,'recall','RECALLED',10,source='regulator'))
        ans,_,_=walk(e,product,['contains','supplied_by','recall'],15)
        if risky:
            sc.check(ans.status=='ANSWER' and valset(ans)=={'RECALLED'},{'case':i,'phase':'risk','got':[ans.status,ans.values]})
            e.ledger.add(ev(f's{i}_withdraw',f'supplier{i}_13','recall','RECALLED',20,operation='RETRACT',target=recall_id,source='regulator'))
            now,_,_=walk(e,product,['contains','supplied_by','recall'],25)
            hist,_,_=walk(e,product,['contains','supplied_by','recall'],15)
            sc.check(now.status=='UNKNOWN' and not now.values,{'case':i,'phase':'withdrawn','got':[now.status,now.values]})
            sc.check(hist.status=='ANSWER' and valset(hist)=={'RECALLED'},{'case':i,'phase':'history','got':[hist.status,hist.values]})
        else:
            sc.check(ans.status=='UNKNOWN' and not ans.values,{'case':i,'phase':'safe','got':[ans.status,ans.values]})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

def test10_agent_resume():
    sc=Score('Agent plan/state recovery','An agent can resume from the exact next action at multiple historical points after plan replacement, step advancement, retraction, and re-learning.')
    t0=time.perf_counter(); e=Engine(functional={'current_plan','next_step'})
    for i in range(100):
        agent=f'agent{i}'; p0=f'plan{i}_0'; p1=f'plan{i}_1'; s0=f'step{i}_0'; s1=f'step{i}_1'; s2=f'step{i}_2'; s3=f'step{i}_3'
        events=[
            ev(f'g{i}_p0',agent,'current_plan',p0,5), ev(f'g{i}_s0',p0,'next_step',s0,10),
            ev(f'g{i}_p1',agent,'current_plan',p1,20), ev(f'g{i}_s1',p1,'next_step',s1,20),
            ev(f'g{i}_s2',p1,'next_step',s2,30),
            ev(f'g{i}_ret',p1,'next_step',s2,40,operation='RETRACT',target=f'g{i}_s2'),
            ev(f'g{i}_s3',p1,'next_step',s3,50),
        ]
        rng.shuffle(events)
        for x in events: e.ledger.add(x)
        for qt,st,vals in [(15,'ANSWER',{s0}),(25,'ANSWER',{s1}),(35,'ANSWER',{s2}),(45,'UNKNOWN',set()),(55,'ANSWER',{s3})]:
            ans,_,_=walk(e,agent,['current_plan','next_step'],qt)
            sc.check(ans.status==st and valset(ans)==vals,{'case':i,'time':qt,'got':[ans.status,ans.values],'expected':[st,sorted(vals)]})
        sc.cases+=1
    sc.elapsed=time.perf_counter()-t0; return sc.result()

TESTS=[test1_memory,test2_entitlements,test3_compliance,test4_workflow,test5_rag_provenance,test6_incident,test7_lineage,test8_contexts,test9_supply_chain,test10_agent_resume]

def main():
    results=[]; total0=time.perf_counter()
    for fn in TESTS:
        r=fn(); results.append(r); print(f"{r['name']}: {r['passed']}/{r['checks']} ({r['elapsed_s']:.3f}s)")
        if r['failures']:
            print('  first failure:', r['failures'][0])
    out={'seed':SEED,'engine_source':str(ROOT),'results':results,'total_checks':sum(r['checks'] for r in results),'total_passed':sum(r['passed'] for r in results),'elapsed_s':time.perf_counter()-total0}
    (Path(__file__).resolve().parents[1] / 'results' / 'applied10' / 'applied10_reproduced.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    return 0 if out['total_checks']==out['total_passed'] else 1

if __name__=='__main__': raise SystemExit(main())
