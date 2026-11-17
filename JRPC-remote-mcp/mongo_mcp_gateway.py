#!/usr/bin/env python3
"""
mongo_mcp_gateway.py — REST facade over a MongoDB MCP server (JSON-RPC 2.0).

    caller ──REST──> this gateway (FastAPI, auth + allowlists) ──MCP/JSON-RPC──> MCP server

Supports MongoDB's Atlas-managed Remote MCP (https://mcp.mongodb.com) out of the
box: OAuth client-credentials via an Atlas MCP service account, token caching /
refresh, Mcp-Session-Id handling, SSE responses, and the remote-atlas-connect
data-plane flow. Also works with a self-hosted mongodb-mcp-server
(`--transport http`).

Endpoints:
    GET  /health            liveness
    GET  /api/tools         tools advertised by the MCP server
    GET  /api/collections   collections in API_DATABASE
    POST /api/query         bounded find; body {"collection","filter","limit"}
    POST /api/call          arbitrary tool call (only if ENABLE_GENERIC_CALL=1)

Env:
    MCP_SERVER_URL       default https://mcp.mongodb.com (self-hosted: http://127.0.0.1:3000)
    MCP_CLIENT_ID        Atlas MCP service-account id     (mdb_sa_id_...)
    MCP_CLIENT_SECRET    Atlas MCP service-account secret (mdb_sa_sk_...)
    MCP_PROJECT_ID       Atlas project id (24-hex)  ─┐ auto-connect data plane
    MCP_CLUSTER_NAME     Atlas cluster name         ─┘ via remote-atlas-connect
    API_DATABASE         default database (default "appdb")
    ALLOWED_COLLECTIONS  comma-separated query allowlist (default "products,orders")
    API_KEY              if set, required as X-API-Key header on /api/* routes
    ENABLE_GENERIC_CALL  "1" enables POST /api/call
    PORT                 gateway port (default 8000)

Requires: pip install requests fastapi uvicorn
Run:      MCP_CLIENT_ID=... MCP_CLIENT_SECRET=... MCP_PROJECT_ID=... \
          MCP_CLUSTER_NAME=... python mongo_mcp_gateway.py
"""

import json
import os
import re
import time
from contextlib import asynccontextmanager
from itertools import count

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# --- config -----------------------------------------------------------------

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "https://mcp.mongodb.com").rstrip("/")
MCP_CLIENT_ID = os.environ.get("MCP_CLIENT_ID", "")
MCP_CLIENT_SECRET = os.environ.get("MCP_CLIENT_SECRET", "")
MCP_PROJECT_ID = os.environ.get("MCP_PROJECT_ID", "")
MCP_CLUSTER_NAME = os.environ.get("MCP_CLUSTER_NAME", "")

API_DATABASE = os.environ.get("API_DATABASE", "appdb")
ALLOWED_COLLECTIONS = {c.strip() for c in
                       os.environ.get("ALLOWED_COLLECTIONS", "products,orders").split(",")
                       if c.strip()}
ALLOWED_OPS = {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin", "$exists"}
MAX_LIMIT = int(os.environ.get("MAX_LIMIT", "100"))

API_KEY = os.environ.get("API_KEY", "")
ENABLE_GENERIC_CALL = os.environ.get("ENABLE_GENERIC_CALL", "").lower() in ("1", "true", "yes")
PORT = int(os.environ.get("PORT", "8000"))

ATLAS_TOKEN_URL = "https://cloud.mongodb.com/api/oauth/token"
PROTOCOL_VERSION = "2025-06-18"


class MCPError(RuntimeError):
    pass


# --- MCP / JSON-RPC client ----------------------------------------------------

class MCPClient:
    """JSON-RPC 2.0 MCP client: Atlas OAuth, session ids, JSON or SSE replies."""

    def __init__(self, base_url, client_id="", client_secret=""):
        self.base_url = base_url.rstrip("/")
        self.mcp_url = None
        self.session_id = None
        self.connection_id = None
        self.tools = []
        self._ids = count(1)
        self._cid, self._secret = client_id, client_secret
        self._token, self._token_exp = "", 0.0
        self._http = requests.Session()

    # auth
    def _ensure_token(self, force=False):
        if not (self._cid and self._secret):
            return
        if not force and self._token and time.time() < self._token_exp - 60:
            return
        r = requests.post(ATLAS_TOKEN_URL, data={"grant_type": "client_credentials"},
                          auth=(self._cid, self._secret), timeout=15)
        if r.status_code != 200:
            raise MCPError(f"OAuth token exchange failed ({r.status_code}): {r.text[:200]}")
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 3600))
        print(f"[mcp] OAuth token acquired (expires in {body.get('expires_in', '?')}s)")

    def _headers(self):
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
            # Spec: client MUST send the negotiated protocol version after init.
            h["MCP-Protocol-Version"] = PROTOCOL_VERSION
        return h

    # transport
    @staticmethod
    def _parse(resp):
        if "text/event-stream" in resp.headers.get("Content-Type", ""):
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    try:
                        return json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
            raise MCPError(f"no JSON in SSE response: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()

    def _rpc_once(self, url, method, params):
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method}
        if params is not None:
            payload["params"] = params
        self._ensure_token()
        resp = self._http.post(url, json=payload, headers=self._headers(), timeout=60)
        if resp.status_code == 401 and self._cid:
            self._ensure_token(force=True)
            resp = self._http.post(url, json=payload, headers=self._headers(), timeout=60)
        if resp.headers.get("Mcp-Session-Id"):
            self.session_id = resp.headers["Mcp-Session-Id"]
        body = self._parse(resp)
        if "error" in body:
            e = body["error"]
            raise MCPError(f"JSON-RPC {e.get('code')}: {e.get('message')}")
        return body.get("result", {})

    def rpc(self, method, params=None):
        if self.mcp_url is None:
            init = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                    "clientInfo": {"name": "mongo-mcp-gateway", "version": "1.0.0"}}
            errors = []
            for candidate in (f"{self.base_url}/mcp", self.base_url):
                try:
                    result = self._rpc_once(candidate, "initialize", init)
                    self.mcp_url = candidate
                    self._notify("notifications/initialized")
                    s = result.get("serverInfo", {})
                    print(f"[mcp] connected: {s.get('name', '?')} @ {candidate} "
                          f"(protocol {result.get('protocolVersion', '?')}, "
                          f"session {self.session_id or 'none'})")
                    if method == "initialize":
                        return result
                    break
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{candidate}: {exc}")
                    self.session_id = None
            if self.mcp_url is None:
                raise MCPError("initialize failed — " + " | ".join(errors))
        return self._rpc_once(self.mcp_url, method, params)

    def _notify(self, method, params=None):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        try:
            self._http.post(self.mcp_url, json=payload, headers=self._headers(), timeout=10)
        except requests.RequestException:
            pass

    # MCP operations
    def list_tools(self):
        self.tools = self.rpc("tools/list", {}).get("tools", [])
        return self.tools

    def call_tool(self, name, arguments=None):
        args = dict(arguments or {})
        # Inject the auto-connected data-plane handle only for tools that
        # declare a connectionId parameter (org-level tools reject it).
        if self.connection_id and "connectionId" not in args:
            schema = next((t for t in self.tools if t["name"] == name), {})
            if "connectionId" in schema.get("inputSchema", {}).get("properties", {}):
                args["connectionId"] = self.connection_id
        result = self.rpc("tools/call", {"name": name, "arguments": args})
        if result.get("isError"):
            raise MCPError(f"tool '{name}' error: "
                           + " ".join(self.texts(result))[:300])
        return result

    @staticmethod
    def texts(result):
        return [b.get("text", "") for b in result.get("content", [])
                if b.get("type") == "text"]

    def connect(self, project_id, cluster_name):
        """remote-atlas-connect → capture connectionId for data tools."""
        result = self.rpc("tools/call", {"name": "remote-atlas-connect",
                                         "arguments": {"projectId": project_id,
                                                       "clusterName": cluster_name}})
        if result.get("isError"):
            raise MCPError("remote-atlas-connect failed: "
                           + " ".join(self.texts(result))[:300])
        for text in self.texts(result):
            try:
                data = json.loads(text)
                cid = data.get("connectionId") or data.get("id")
            except json.JSONDecodeError:
                m = re.search(r'connectionId is "([0-9a-fA-F-]{8,})"', text)
                cid = m.group(1) if m else None
            if cid:
                self.connection_id = str(cid)
                print(f"[mcp] data-plane connected (connectionId={cid})")
                return
        raise MCPError("remote-atlas-connect returned no connectionId")


# --- input validation -----------------------------------------------------------

def validate_filter(raw):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise HTTPException(400, "filter must be an object")
    for key, value in raw.items():
        if key.startswith("$"):
            raise HTTPException(400, f"top-level operator not allowed: {key}")
        if isinstance(value, dict):
            for op in value:
                if op not in ALLOWED_OPS:
                    raise HTTPException(400, f"operator not allowed: {op}")
    return raw


# --- FastAPI app ------------------------------------------------------------------

mcp = None


@asynccontextmanager
async def lifespan(_app):
    global mcp
    try:
        c = MCPClient(MCP_SERVER_URL, MCP_CLIENT_ID, MCP_CLIENT_SECRET)
        c.rpc("initialize")
        print(f"[mcp] {len(c.list_tools())} tools discovered")
        mcp = c
        if MCP_PROJECT_ID and MCP_CLUSTER_NAME:
            c.connect(MCP_PROJECT_ID, MCP_CLUSTER_NAME)
    except Exception as exc:  # noqa: BLE001
        mcp = None
        print(f"[warn] MCP startup failed: {exc}")
    yield


app = FastAPI(title="MongoDB MCP Gateway", lifespan=lifespan)


def client():
    if mcp is None:
        raise HTTPException(503, "MCP client not connected — check credentials "
                                 "and MCP_SERVER_URL.")
    return mcp


@app.middleware("http")
async def api_key_guard(request, call_next):
    if API_KEY and request.url.path.startswith("/api/"):
        if request.headers.get("X-API-Key") != API_KEY:
            return JSONResponse(401, {"error": "invalid or missing API key"})
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "mcp_connected": mcp is not None}


@app.get("/api/tools")
def api_tools():
    try:
        return {"tools": [{"name": t["name"], "description": t.get("description", "")}
                          for t in client().list_tools()]}
    except MCPError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/collections")
def api_collections():
    c = client()
    try:
        return {"database": API_DATABASE,
                "result": c.call_tool("list-collections", {"database": API_DATABASE})}
    except MCPError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/query")
async def api_query(request: Request):
    body = await request.json()
    collection = body.get("collection")
    if collection not in ALLOWED_COLLECTIONS:
        raise HTTPException(400, f"collection not allowed; allowed: {sorted(ALLOWED_COLLECTIONS)}")
    limit = body.get("limit", 50)
    if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= MAX_LIMIT):
        raise HTTPException(400, f"limit must be an integer from 1 to {MAX_LIMIT}")
    c = client()
    args = {"database": API_DATABASE, "collection": collection,
            "filter": validate_filter(body.get("filter")), "limit": limit}
    try:
        return {"collection": collection, "result": c.call_tool("find", args)}
    except MCPError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/call")
async def api_call(request: Request):
    if not ENABLE_GENERIC_CALL:
        raise HTTPException(403, "generic tool calling disabled "
                                 "(set ENABLE_GENERIC_CALL=1 to enable)")
    body = await request.json()
    if not body.get("tool"):
        raise HTTPException(400, "missing 'tool' in body")
    try:
        return client().call_tool(body["tool"], body.get("arguments", {}))
    except MCPError as exc:
        raise HTTPException(502, str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
