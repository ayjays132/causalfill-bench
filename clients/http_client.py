"""Agent-side client. Copy only this file into the agent's isolated container.

No imports of evaluator modules. Set CFB_URL and CFB_TOKEN in the agent runner.
Usage: python http_client.py episode
       echo '{"tool":"list_files","arguments":{}}' | python http_client.py tool
"""
import json
import os
import sys
import urllib.error
import urllib.request


def request(endpoint,payload=None):
    base=os.environ.get("CFB_URL","http://127.0.0.1:8787").rstrip("/")
    token=os.environ.get("CFB_TOKEN","")
    if len(token)<24: raise ValueError("CFB_TOKEN is missing or too short")
    data=None if payload is None else json.dumps(payload,allow_nan=False).encode()
    req=urllib.request.Request(base+endpoint,data=data,
        headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            return json.loads(response.read(262144))
    except urllib.error.HTTPError as exc:
        return {"error":"HTTP "+str(exc.code)}


def main():
    if len(sys.argv)!=2 or sys.argv[1] not in ("episode","tool"):
        raise ValueError("usage: http_client.py episode|tool")
    if sys.argv[1]=="episode": out=request("/v1/episode")
    else:
        raw=sys.stdin.read(131073)
        if len(raw)>131072: raise ValueError("request exceeds 128 KiB")
        out=request("/v1/tool",json.loads(raw))
    print(json.dumps(out,allow_nan=False))


if __name__=="__main__":
    try: main()
    except (ValueError,OSError) as exc: raise SystemExit(str(exc))
