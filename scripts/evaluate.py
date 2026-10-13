"""Same questions and labels across live ablations; bypass all service caching."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import statistics
import time
import httpx

def score(documents, expected, k):
    rank = next((i for i,doc in enumerate(documents,1)
                 if any(term in doc['content'] for term in expected)),0)
    return {'hit_at_k':bool(rank and rank<=k),'reciprocal_rank':1/rank if rank else 0}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8050')
    parser.add_argument('--cases',type=Path,default=Path('evals/cases.json'))
    parser.add_argument('--output',type=Path,default=Path('reports/live-ablation.json'))
    parser.add_argument('--web',action='store_true')
    args=parser.parse_args()
    cases=json.loads(args.cases.read_text(encoding='utf-8-sig'))
    modes={'vector':(['vector'],False),'fusion':(['vector','hyde','kg'],False),
        'rerank':(['vector','hyde','kg'],True)}
    if args.web:
        modes['web_rerank']=(['vector','hyde','kg','web'],True)
    report={'source':'live_http_ablation','created_at':datetime.now(timezone.utc).isoformat(),
        'case_sha256':hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        'top_k':5,'cache_bypassed':True,'label_method':'content substring, inherited 5-case initial set',
        'limitations':['Single RS-12 manual; no generalization claim.','LLM rewriting is nondeterministic.',
            'Single run per mode; timings are descriptive, not a load benchmark.'],
        'results':[], 'summary':{}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    token=os.getenv('RETRIEVAL_API_TOKEN','')
    headers={'Authorization':'Bearer '+token} if token else {}
    with httpx.Client(trust_env=False,timeout=200,headers=headers) as client:
        for mode,(routes,rerank) in modes.items():
            for case in cases:
                start=time.monotonic()
                response=client.post(args.url+'/v1/retrieve',json={'query':case['query'],
                    'routes':routes,'rerank':rerank,'top_k':5,'use_cache':False})
                payload=response.json()
                documents=payload.get('documents',[])
                item={'mode':mode,'case_id':case['id'],'http_status':response.status_code,
                    'latency_s':round(time.monotonic()-start,3),'response':payload,
                    **score(documents,case['expected_content_any_of'],5)}
                report['results'].append(item)
                args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({k:v for k,v in item.items() if k!='response'}),flush=True)
    for mode in modes:
        rows=[r for r in report['results'] if r['mode']==mode]
        report['summary'][mode]={'cases':len(rows),
            'http_success':sum(r['http_status']==200 for r in rows),
            'partial':sum(r['response'].get('status')=='partial' for r in rows),
            'hit_at_5':sum(r['hit_at_k'] for r in rows)/len(rows),
            'mrr':sum(r['reciprocal_rank'] for r in rows)/len(rows),
            'mean_latency_s':round(statistics.mean(r['latency_s'] for r in rows),3)}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2))
    if any(r['http_status']!=200 or r['response'].get('backend')!='live' for r in report['results']):
        raise SystemExit(1)

if __name__=='__main__':
    main()
