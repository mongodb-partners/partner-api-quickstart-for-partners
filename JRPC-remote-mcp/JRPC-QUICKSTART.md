# JRPC Remote MCP Quickstart — Implementation Guide

Implementation content for the **"Separate alternative: JRPC HTTP API gateway"**
section of the *Lovable + MongoDB Integration* plan.

> **Positioning.** This is an independent alternative to the official-driver
> plan (Phases 0–4). It is **not** part of that roadmap and is **not** an
> already production-ready BYOK service. Evaluate it separately for runtime
> compatibility, customer setup, security boundaries, operational ownership,
> and supported Atlas capabilities before any pilot.

**The idea in one paragraph:** run a small server-side gateway that speaks
JSON-RPC 2.0 / Streamable HTTP to MongoDB Atlas **Managed Remote MCP**, and
expose only a narrow set of read operations as a plain HTTPS API. The published
Lovable app calls that HTTPS API (ideally through a server-side/API connector,
not browser code). The browser never sees a MongoDB connection string or an MCP
credential — it only sees your gateway's API.

```
Lovable app ──HTTPS/REST──> JRPC gateway ──JSON-RPC 2.0 / Streamable HTTP──> Atlas Managed Remote MCP
  (server-side call)         (this service: auth, validation, allowlists)      (mongodb.com hosted tools)
```

---

## What the gateway does (per phase of the request)

| Phase | What happens | Code in `mongo_mcp_gateway.py` |
|---|---|---|
| Auth | OAuth `client_credentials` against Atlas, cached + refreshed | `MCPClient._ensure_token` |
| Handshake | MCP `initialize` → `notifications/initialized` | `MCPClient.rpc` (first call) |
| Session | capture + replay `Mcp-Session-Id`, send `MCP-Protocol-Version` | `MCPClient._headers` |
| Data plane | `remote-atlas-connect` → remember `connectionId` | `MCPClient.connect` |
| Discovery | `tools/list` at startup | `MCPClient.list_tools` |
| Call | `tools/call`, inject `connectionId` only where the schema allows | `MCPClient.call_tool` |
| Facade | narrow REST endpoints with allowlists + validation | FastAPI routes |

The full working reference is `mongo_mcp_gateway.py` in this folder; `README.md`
has a curl example per tool. Below is how to deploy it to match this document's
guardrails.

---

## Implementation outline (mapped to the doc's five steps)

### 1. Deploy the service and configure its upstream

Run the gateway as a secured HTTPS service in a controlled environment. Point it
at the Atlas Managed Remote MCP endpoint and authenticate with a service account.

```bash
pip install requests fastapi uvicorn

# Upstream = Atlas Managed Remote MCP (default). Credentials stay server-side.
export MCP_SERVER_URL="https://mcp.mongodb.com"
export MCP_CLIENT_ID="mdb_sa_id_..."        # Atlas MCP service account
export MCP_CLIENT_SECRET="mdb_sa_sk_..."
export MCP_PROJECT_ID="<PROJECT_ID>"        # Atlas project
export MCP_CLUSTER_NAME="<CLUSTER_NAME>"    # Atlas cluster

# Narrow the surface: read-only database + allowlisted collections.
export API_DATABASE="appdb"
export ALLOWED_COLLECTIONS="products,orders"

# Require callers to authenticate; do NOT enable generic passthrough.
export API_KEY="<GATEWAY_SHARED_SECRET>"    # callers must send X-API-Key
# ENABLE_GENERIC_CALL is intentionally left unset (off).

python mongo_mcp_gateway.py                 # serves on :8000
```

Startup log (sanity check):

```
[mcp] OAuth token acquired (expires in 3600s)
[mcp] connected: .../atlas-mcp/remote-mcp-server @ https://mcp.mongodb.com (session ...)
[mcp] 44 tools discovered
[mcp] data-plane connected (connectionId=...)
```

### 2. Expose only the narrow read operations the app needs

**Do not** expose the generic tool passthrough or arbitrary database commands.
With `ENABLE_GENERIC_CALL` unset, only these routes exist:

| Route | Purpose | Guardrails |
|---|---|---|
| `GET /health` | liveness | no secrets |
| `GET /api/tools` | list advertised tool names | metadata only |
| `GET /api/collections` | list collections in `API_DATABASE` | fixed database |
| `POST /api/query` | bounded `find` on one allowlisted collection | collection allowlist, operator allowlist, `limit` clamp |

`/api/query` validation (the core of the "narrow reads only" promise):

```python
# Only allowlisted collections...
if collection not in ALLOWED_COLLECTIONS:
    raise HTTPException(400, "collection not allowed")
# ...only allowlisted filter operators (no $where, no pipelines)...
for key, value in raw_filter.items():
    if key.startswith("$"):                     # block top-level operators
        raise HTTPException(400, f"operator not allowed: {key}")
    if isinstance(value, dict):
        for op in value:
            if op not in ALLOWED_OPS:           # $eq,$gt,...$exists only
                raise HTTPException(400, f"operator not allowed: {op}")
# ...and a hard cap on result size.
limit = clamp(body.get("limit", 50), 1, MAX_LIMIT)
```

### 3. Have Lovable call the HTTPS endpoint via a server-side path

The published app should reach the gateway through a server-side/API connector
wherever possible, so the gateway secret and upstream credentials never appear
in browser code.

```bash
# What the app's server-side connector sends:
curl -X POST https://<your-gateway-host>/api/query \
  -H "X-API-Key: <GATEWAY_SHARED_SECRET>" \
  -H 'Content-Type: application/json' \
  -d '{"collection":"products","filter":{"sku":"KB-01"},"limit":10}'
```

If Lovable's published-app runtime can only make client-side HTTP calls, treat
the gateway key as a browser-visible value and add a stronger caller-auth /
tenant layer (step 4) before any real customer data flows.

### 4. Add caller auth, isolation, limits, and redacted logs

Before any customer pilot, the gateway needs (the reference file includes the
first three; the rest are pilot work):

- **Caller authentication** — `X-API-Key` middleware (included); OIDC/JWT at the
  ingress for production.
- **Request validation** — allowlists + operator allowlist + limit clamp (included).
- **Rate / timeout limits** — MCP client timeout is set (60s); add per-caller
  rate limiting at the ingress.
- **Redacted logs** — log principal, route/tool, duration, outcome, request id;
  never log `Authorization` headers, connection strings, or document bodies.

### 5. Multi-customer mapping — an open question, do not assume

The reference gateway holds **one** upstream connection (`connectionId`) bound
to a single project/cluster at startup. That is intentionally **single-tenant**.

For multiple customers you must confirm, not assume:

- how each customer maps to **their own** Atlas credentials / `connectionId`;
- whether the upstream enforces per-customer access controls through a shared
  gateway configuration;
- tenant isolation for secrets, sessions, and logs.

A plausible per-tenant shape (one `MCPClient` per customer, keyed by caller
identity) is sketched below — treat it as a design starting point pending
validation, not shipped behavior:

```python
# Sketch only — validate upstream per-customer support before building.
clients = {}   # tenant_id -> MCPClient

def client_for(tenant_id, tenant_cfg):
    if tenant_id not in clients:
        c = MCPClient(MCP_SERVER_URL, tenant_cfg["client_id"],
                      tenant_cfg["client_secret"])
        c.rpc("initialize")
        c.connect(tenant_cfg["project_id"], tenant_cfg["cluster_name"])
        clients[tenant_id] = c
    return clients[tenant_id]
```

---

## Pilot guardrails (carry over verbatim)

- No credentials in client-side code; no broad write permissions; access limited
  to the agreed read-only scope.
- Do not assume OAuth client credentials or chat MCP provide database
  authorization for the published app.
- Treat JRPC as an alternative pending security, product-fit, and multi-tenant
  validation — not as an already production-ready BYOK service.

## Open decisions and risks (as they apply to this alternative)

- Does Lovable's published-app runtime support server-side outbound HTTPS to the
  gateway, or only browser-side calls (which changes the caller-auth design)?
- Can the upstream Managed Remote MCP enforce per-customer access controls
  through a shared gateway, or is a per-customer gateway/connection required?
- What are the supported database/collection restriction, auditing, and
  credential-rotation capabilities for the target Atlas tiers?
- Who owns gateway operations, scaling, and incident response in production?

---

**References:** full working code in `mongo_mcp_gateway.py`; per-tool curl
reference in `README.md`; step-by-step protocol internals in `IMPLEMENTATION.md`.
