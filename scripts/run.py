#!/usr/bin/env python3
"""Bounded paired inference experiment. Standard library only; no mock inference."""
import argparse, datetime, hashlib, json, os, random, time, urllib.request, urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODELS={'gpt-6-astra':'openai','claude-fable-5-1':'anthropic','claude-opus-5-5':'anthropic'}
def extract(provider, raw):
    if provider=='openai':
        text=''.join(c.get('text','') for o in raw.get('output',[]) if o.get('type')=='message' for c in o.get('content',[]) if c.get('type')=='output_text')
        reasoning=raw.get('usage',{}).get('output_tokens_details',{}).get('reasoning_tokens')
        complete=raw.get('status')=='completed'
    else:
        text=''.join(c.get('text','') for c in raw.get('content',[]) if c.get('type')=='text')
        reasoning=None # No comparable separately billed reasoning-token field assumed.
        complete=raw.get('stop_reason')=='end_turn'
    return dict(text=text.strip(),reasoning_tokens=reasoning,complete=complete)
def request(provider, model, system, prompt, budget):
    if provider=='openai':
        key=os.getenv('OPENAI_API_KEY')
        body={'model':model,'instructions':system,'input':prompt,'max_output_tokens':budget,'reasoning':{'effort':'medium'},'store':False}
        url='https://api.openai.com/v1/responses'
        headers={'Authorization':'Bearer '+(key or '')}
    else:
        key=os.getenv('ANTHROPIC_API_KEY')
        body={'model':model,'system':system,'messages':[{'role':'user','content':prompt}],'max_tokens':budget,'thinking':{'type':'adaptive'}}
        url='https://api.anthropic.com/v1/messages'
        headers={'x-api-key':key or '', 'anthropic-version':'2023-06-01'}
    if not key: return body,None,{'type':'missing_credential','message':provider+' API key not configured'}
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={**headers,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return body,json.load(resp),None
    except urllib.error.HTTPError as e:
        # Body is retained for debugging; authentication headers are never logged.
        return body,None,{'type':'http_error','status':e.code,'body':e.read().decode(errors='replace')}
    except Exception as e:
        return body,None,{'type':type(e).__name__,'message':str(e)}
def main():
    p=argparse.ArgumentParser();p.add_argument('--model',choices=list(MODELS),required=True);p.add_argument('--repeats',type=int,default=3);p.add_argument('--seed',type=int,default=20261021);p.add_argument('--budget',type=int,default=2048);p.add_argument('--method');p.add_argument('--preflight',action='store_true');a=p.parse_args()
    if not 1<=a.repeats<=10 or not 256<=a.budget<=8192: p.error('repeats 1..10; budget 256..8192')
    cases=json.loads((ROOT/'data/cases.json').read_text()); cases=[c for c in cases if not a.method or c['method']==a.method]
    if not cases: p.error('no matching method')
    provider=MODELS[a.model]; stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');dest=ROOT/'logs'/f'{stamp}-{a.model}.jsonl'
    tasks=[(c,rep,arm) for c in cases for rep in range(a.repeats) for arm in ['control','attack']];random.Random(a.seed).shuffle(tasks)
    missing=not os.getenv('OPENAI_API_KEY' if provider=='openai' else 'ANTHROPIC_API_KEY')
    with dest.open('x') as out:
        for c,rep,arm in tasks:
            start=time.monotonic();raw=None;body=None
            if a.preflight or missing:
                err={'type':'preflight_only' if a.preflight else 'missing_credential'}
            else: body,raw,err=request(provider,a.model,c['system'],c[arm],a.budget)
            record={'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'case_id':c['id'],'method':c['method'],'metric':c['metric'],'model_requested':a.model,'provider':provider,'repeat':rep,'arm':arm,'seed':a.seed,'budget':a.budget,'case_sha256':hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest(),'expected':c['expected'],'target':c['target'],'system':c['system'],'prompt':c[arm],'request':body,'raw_response':raw,'error':err,'elapsed_seconds':time.monotonic()-start,'status':'not_run' if a.preflight or missing else ('api_error' if err else 'response')}
            if raw is not None: record.update(extract(provider,raw))
            out.write(json.dumps(record,ensure_ascii=False)+'\n');out.flush()
    print(dest.relative_to(ROOT)); print('not_run' if a.preflight or missing else 'requests_finished')
if __name__=='__main__': main()
