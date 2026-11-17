# Implementation Guide — MongoDB Remote MCP over JSON-RPC

How `mongo_mcp_gateway.py` is built, phase by phase, with example code for each
step. Everything below uses only `requests` + `fastapi` and talks to MongoDB's
Atlas-managed Remote MCP server (`https://mcp.mongodb.com`) — no MCP SDK
required.

The phases, in order:

1. [OAuth client-credentials auth](#1-oauth-client-credentials-auth)
2. [MCP initialize handshake](#2-mcp-initialize-handshake)
3. [Session capture + `initialized` notification](#3-session-capture--initialized-notification)
4. [JSON-RPC request/response (JSON & SSE)](#4-json-rpc-requestresponse-json--sse)
5. [Data-plane connection (`remote-atlas-connect`)](#5-data-plane-connection-remote-atlas-connect)
6. [Tool discovery (`tools/list`)](#6-tool-discovery-toolslist)
7. [Calling tools (`tools/call`)](#7-calling-tools-toolscall)
8. [REST facade (FastAPI endpoints)](#8-rest-facade-fastapi-endpoints)
9. [Security & guardrails](#9-security--guardrails)
10. [Putting it all together](#10-putting-it-all-together)

---

## 1. OAuth client-credentials auth

Atlas service accounts (`mdb_sa_id_…` / `mdb_sa_sk_…`) are exchanged for a
short-lived Bearer token. The token endpoint is
`https://cloud.mongodb.com/api/oauth/token` (**not** `authorize.mongodb.com`).

```python
import time, requests

TOKEN_URL = "https://cloud.mongodb.com/api/oauth/token"

class Auth:
    def __init__(self, client_id, client_secret):
        self.client_id, self.client_secret = client_id, client_secret
        self.token, self.expiry = "", 0.0

    def get(self):
        # Reuse the cached token until 60s before it expires.
        if self.token and time.time() < self.expiry - 60:
            return self.token
        r = requests.post(TOKEN_URL,
                          data={"grant_type": "client_credentials"},
                          auth=(self.client_id, self.client_secret), timeout=15)
        r.raise_for_status()
        body = r.json()                                  # {access_token, expires_in}
        self.token = body["access_token"]
        self.expiry = time.time() + int(body.get("expires_in", 3600))
        return self.token
```

curl equivalent:

```bash
curl -X POST https://cloud.mongodb.com/api/oauth/token \
  -u "$MCP_CLIENT_ID:$MCP_CLIENT_SECRET" \
  -d 'grant_type=client_credentials'
```

---

## 2. MCP initialize handshake

Every MCP session starts with an `initialize` JSON-RPC request. The
`Accept` header **must** list both JSON and SSE — Atlas replies with SSE.

```python
import requests

MCP_URL = "https://mcp.mongodb.com"   # Atlas serves MCP at the root path

payload = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "my-gateway", "version": "1.0.0"},
    },
}
resp = requests.post(MCP_URL, json=payload, headers={
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}, timeout=60)
```

Response arrives as Server-Sent Events:

```
event: message
data: {"result":{"protocolVersion":"2025-06-18","serverInfo":{"name":"...atlas-mcp/remote-mcp-server",...}},"jsonrpc":"2.0","id":1}
```

---

## 3. Session capture + `initialized` notification

Atlas returns a session id in a response header and **requires** it on every
later request. After `initialize`, the client must send the
`notifications/initialized` notification (no `id`, expect HTTP 202).

```python
session_id = resp.headers.get("Mcp-Session-Id")

def headers():
    h = {"Content-Type": "application/json",
         "Accept": "application/json, text/event-stream",
         "Authorization": f"Bearer {token}",
         "MCP-Protocol-Version": "2025-06-18"}   # required after init
    if session_id:
        h["Mcp-Session-Id"] = session_id         # required by Atlas
    return h

# Notification — no "id" field, server replies 202 with no body.
requests.post(MCP_URL, headers=headers(), timeout=10,
              json={"jsonrpc": "2.0", "method": "notifications/initialized"})
```

---

## 4. JSON-RPC request/response (JSON & SSE)

One helper sends a request and normalizes both response styles.

```python
import json
from itertools import count

_ids = count(1)

def rpc(url, method, params=None):
    payload = {"jsonrpc": "2.0", "id": next(_ids), "method": method}
    if params is not None:
        payload["params"] = params
    resp = requests.post(url, json=payload, headers=headers(), timeout=60)
    if resp.headers.get("Mcp-Session-Id"):           # keep the session fresh
        globals()["session_id"] = resp.headers["Mcp-Session-Id"]

    if "text/event-stream" in resp.headers.get("Content-Type", ""):
        for line in resp.text.splitlines():          # SSE: read data: lines
            if line.startswith("data:"):
                body = json.loads(line[5:].strip()); break
    else:
        body = resp.json()                            # plain JSON

    if "error" in body:                               # JSON-RPC error object
        raise RuntimeError(f"{body['error'].get('code')}: "
                           f"{body['error'].get('message')}")
    return body.get("result", {})
```

---

## 5. Data-plane connection (`remote-atlas-connect`)

Data tools (`find`, `aggregate`, …) need a `connectionId`. Obtain it once via
`remote-atlas-connect`; the id is returned **in prose**, so regex it out.

```python
import json, re

result = rpc(MCP_URL, "tools/call", {
    "name": "remote-atlas-connect",
    "arguments": {"projectId": PROJECT_ID, "clusterName": CLUSTER_NAME},
})
text = " ".join(b.get("text", "") for b in result.get("content", []))
# e.g. 'Successfully connected ... Your connectionId is "xxxxxxxx-...."'
m = re.search(r'connectionId is "([0-9a-fA-F-]{8,})"', text)
connection_id = m.group(1)
```

---

## 6. Tool discovery (`tools/list`)

Never hardcode tool names — ask the server what it exposes.

```python
tools = rpc(MCP_URL, "tools/list", {}).get("tools", [])
for t in tools:
    print(t["name"], "-", t.get("description", ""))
    # t["inputSchema"]["properties"] tells you the exact arguments
```

Atlas advertises 44 tools: data (`find`, `aggregate`, `count`, …), Atlas admin
(`atlas-list-clusters`, `atlas-create-db-user`, …), Stream Processing
(`atlas-streams-*`), and knowledge base (`search-knowledge`).

---

## 7. Calling tools (`tools/call`)

Pass the tool name and arguments; inject `connectionId` for data tools. A tool
can fail at the MCP level via an `isError` flag even when HTTP is 200.

```python
def call_tool(name, arguments):
    args = dict(arguments)
    schema = next((t for t in tools if t["name"] == name), {})
    # Inject connectionId ONLY for tools that declare it (org-level tools
    # use additionalProperties:false and reject extra fields).
    if connection_id and "connectionId" not in args and \
       "connectionId" in schema.get("inputSchema", {}).get("properties", {}):
        args["connectionId"] = connection_id

    result = rpc(MCP_URL, "tools/call", {"name": name, "arguments": args})
    if result.get("isError"):
        raise RuntimeError("tool error: " + json.dumps(result.get("content")))
    return result

# Example: count movies from 1999
print(call_tool("count", {"database": "sample_mflix",
                          "collection": "movies", "query": {"year": 1999}}))
```

---

## 8. REST facade (FastAPI endpoints)

Wrap the client in endpoints. Curated routes add guardrails; a generic route
can call any tool.

```python
from fastapi import FastAPI, HTTPException, Request

app = FastAPI()
client = None   # initialized at startup with the phases above

@app.get("/health")
def health():
    return {"status": "ok", "mcp_connected": client is not None}

@app.get("/api/tools")
def api_tools():
    return {"tools": [{"name": t["name"],
                       "description": t.get("description", "")}
                      for t in client.list_tools()]}

@app.get("/api/collections")
def api_collections():
    return {"database": DB,
            "result": client.call_tool("list-collections", {"database": DB})}

@app.post("/api/query")
async def api_query(request: Request):
    body = await request.json()
    if body.get("collection") not in ALLOWED_COLLECTIONS:
        raise HTTPException(400, "collection not allowed")
    result = client.call_tool("find", {
        "database": DB, "collection": body["collection"],
        "filter": validate_filter(body.get("filter")),
        "limit": clamp(body.get("limit", 50), 1, 100)})
    return {"result": result}

@app.post("/api/call")                 # generic passthrough — protect it!
async def api_call(request: Request):
    body = await request.json()
    return client.call_tool(body["tool"], body.get("arguments", {}))
```

---

## 9. Security & guardrails

Bound what callers can do; never forward arbitrary filters or pipelines.

```python
ALLOWED_OPS = {"$eq","$ne","$gt","$gte","$lt","$lte","$in","$nin","$exists"}

def validate_filter(raw):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise HTTPException(400, "filter must be an object")
    for key, value in raw.items():
        if key.startswith("$"):                    # no top-level operators
            raise HTTPException(400, f"operator not allowed: {key}")
        if isinstance(value, dict):
            for op in value:
                if op not in ALLOWED_OPS:          # allowlisted operators only
                    raise HTTPException(400, f"operator not allowed: {op}")
    return raw

def clamp(n, lo, hi):
    return max(lo, min(hi, n if isinstance(n, int) else lo))

# Optional shared-secret auth on all /api/* routes:
from fastapi.responses import JSONResponse

@app.middleware("http")
async def api_key_guard(request, call_next):
    if API_KEY and request.url.path.startswith("/api/"):
        if request.headers.get("X-API-Key") != API_KEY:
            return JSONResponse(401, {"error": "invalid or missing API key"})
    return await call_next(request)
```

Checklist:

- Keep `mdb_sa_*` credentials in env vars / a secret manager — never in code or logs.
- Allowlist collections, fields, operators, sort keys; cap `limit` and result size.
- Leave generic `/api/call` **off** (`ENABLE_GENERIC_CALL`) for untrusted callers —
  it can reach destructive tools (`drop-database`, `delete-many`, …).
- Terminate TLS and do real OIDC/JWT validation at your gateway in production.
- Treat tool-returned document text as untrusted data, never as instructions.

---

## 10. Putting it all together

```python
import os, requests, fastapi, uvicorn

# --- config ---
MCP_URL        = os.environ.get("MCP_SERVER_URL", "https://mcp.mongodb.com")
CLIENT_ID      = os.environ["MCP_CLIENT_ID"]
CLIENT_SECRET  = os.environ["MCP_CLIENT_SECRET"]
PROJECT_ID     = os.environ["MCP_PROJECT_ID"]
CLUSTER_NAME   = os.environ["MCP_CLUSTER_NAME"]
DB             = os.environ.get("API_DATABASE", "appdb")

# --- phases 1-7: build the client (see sections above) ---
auth = Auth(CLIENT_ID, CLIENT_SECRET)              # 1. OAuth
token = auth.get()
# ... initialize (2), session + initialized (3), rpc helper (4) ...
connection_id = connect(PROJECT_ID, CLUSTER_NAME)  # 5. data plane
tools = rpc(MCP_URL, "tools/list", {})["tools"]    # 6. discovery
# call_tool() (7) is used by the facade

# --- phase 8/9: FastAPI app with endpoints + guardrails ---
app = FastAPI()
# ... routes from section 8 ...

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
```

Run it:

```bash
pip install requests fastapi uvicorn
export MCP_CLIENT_ID="mdb_sa_id_..." MCP_CLIENT_SECRET="mdb_sa_sk_..."
export MCP_PROJECT_ID="<PROJECT_ID>" MCP_CLUSTER_NAME="<CLUSTER_NAME>"
export API_DATABASE="sample_mflix"
python mongo_mcp_gateway.py
```

Then:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/tools
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' \
  -d '{"tool":"count","arguments":{"database":"sample_mflix","collection":"movies"}}'
```

The full working implementation is `mongo_mcp_gateway.py` in this folder;
`README.md` has a curl example for every one of the 44 tools.
