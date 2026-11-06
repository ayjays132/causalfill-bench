import json, pathlib, urllib.request, urllib.error, sys, time, concurrent.futures
ROOT=pathlib.Path('/workspace/scratch/addf9cb6769c/signal-public-pilot/solver-work')
ENDPOINTS=json.loads(pathlib.Path('/workspace/scratch/addf9cb6769c/signal-public-pilot/endpoints.json').read_text())['endpoints']
def call(label, tool=None, arguments=None):
    e=next(e for e in ENDPOINTS if e['label']==label)
    path='/v1/episode' if tool is None else '/v1/tool'
    payload=None if tool is None else {'tool':tool,'arguments':arguments or {}}
    data=None if payload is None else json.dumps(payload,allow_nan=False).encode()
    req=urllib.request.Request(e['url']+path,data=data,headers={'Authorization':'Bearer '+e['token'],'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response: out=json.loads(response.read(262144))
    except urllib.error.HTTPError as ex: out={'error':'HTTP '+str(ex.code)}
    except (urllib.error.URLError,OSError) as ex: out={'transport_error':str(ex)}
    entry={'at':time.time(),'endpoint':path,'input':payload,'output':out}
    with (ROOT/(label+'.jsonl')).open('a') as f:f.write(json.dumps(entry,allow_nan=False)+'\n')
    return out
if __name__=='__main__':
    if sys.argv[1]=='all':
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda e:(e['label'],call(e['label'])),ENDPOINTS))
        for label,out in results:
            (ROOT/(label+'-episode.json')).write_text(json.dumps(out,indent=2))
            print(label,json.dumps(out))
    else:
        label=sys.argv[1]
        tool=sys.argv[2] if len(sys.argv)>2 else None
        arguments=json.loads(sys.argv[3]) if len(sys.argv)>3 else None
        print(json.dumps(call(label,tool,arguments)))
