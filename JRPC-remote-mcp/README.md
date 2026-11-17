# MongoDB MCP Gateway — Tool Call Reference (curl)

A single-file FastAPI gateway (`mongo_mcp_gateway.py`) that connects to a MongoDB
MCP server over JSON-RPC 2.0 and exposes the tools as HTTP endpoints.

## What this repo does

This project shows how to consume **MongoDB's Atlas-managed Remote MCP server**
(`https://mcp.mongodb.com`) from any HTTP client — curl, a web app, a backend
service, or an AI agent — without implementing the MCP protocol yourself.

**The problem it solves.** MCP servers speak JSON-RPC 2.0 over Streamable HTTP
with an OAuth handshake, session negotiation, and SSE-framed responses. That's
fine for MCP-native AI clients, but awkward to call from a plain REST/HTTP
consumer. This gateway bridges the two worlds:

```
caller ──HTTP/REST──> mongo_mcp_gateway.py ──JSON-RPC 2.0 / Streamable HTTP──> MongoDB Remote MCP
                       (FastAPI: auth, validation, allowlists)                (44 Atlas + data tools)
```

**How it works, end to end:**

1. **Authenticates** with your Atlas MCP service account (`mdb_sa_id_…` /
   `mdb_sa_sk_…`) using OAuth 2.0 `client_credentials` against
   `https://cloud.mongodb.com/api/oauth/token`, caching and auto-refreshing the
   token before it expires.
2. **Performs the MCP handshake** (`initialize` → `notifications/initialized`),
   negotiates the protocol version, and captures the `Mcp-Session-Id` that the
   server requires on every subsequent request.
3. **Establishes a data-plane connection** via `remote-atlas-connect` (using
   your project id + cluster name) and remembers the returned `connectionId`.
   That id is then injected automatically — only into tools whose schema
   actually accepts it — so callers never deal with it.
4. **Discovers and re-exposes the server's tools** as simple REST endpoints:
   - curated, guardrailed routes (`/api/collections`, `/api/query`) with
     collection allowlists, filter-operator allowlists, and result caps;
   - an optional generic passthrough (`POST /api/call`) that can invoke **any**
     of the 44 advertised tools (data, Atlas admin, Stream Processing, and
     knowledge-base tools).
5. **Parses both response formats** the server may send — plain JSON or
   `text/event-stream` (SSE) — and surfaces JSON-RPC errors and MCP tool errors
   (`isError`) as proper HTTP errors.

**Security model:** keep your service-account credentials server-side in env
vars; optionally require an `X-API-Key` header on all `/api/*` routes; leave
generic tool calling disabled for untrusted callers and expose only the curated
routes. Database content returned by tools is wrapped in
`<untrusted-user-data …>` tags and must be treated as data, never instructions.

**Also works with a self-hosted MCP server** (`mongodb-mcp-server --transport
http`): point `MCP_SERVER_URL` at it and skip the Atlas credentials.

The rest of this file is a complete curl reference for every tool the server
advertises.

## Setup

```bash
pip install requests fastapi uvicorn

export MCP_CLIENT_ID="mdb_sa_id_..."        # Atlas MCP service-account id
export MCP_CLIENT_SECRET="mdb_sa_sk_..."    # Atlas MCP service-account secret
export MCP_PROJECT_ID="<PROJECT_ID>"   # e.g. GCP-PoV-Cluster
export MCP_CLUSTER_NAME="<CLUSTER_NAME>"
export API_DATABASE="sample_mflix"
export ALLOWED_COLLECTIONS="movies,comments"
export ENABLE_GENERIC_CALL=1                # required for /api/call examples below
# export API_KEY="secret123"                # optional: then add -H "X-API-Key: secret123"

python mongo_mcp_gateway.py                 # listens on :8000
```

Base URL below is `http://localhost:8000`.

> **`connectionId` is auto-injected.** The gateway runs `remote-atlas-connect` at
> startup (using `MCP_PROJECT_ID` + `MCP_CLUSTER_NAME`) and adds the resulting
> `connectionId` to every data-tool call. You don't pass it in curl.

---

## Gateway endpoints

```bash
# Liveness
curl http://localhost:8000/health

# List all advertised tools (names + descriptions)
curl http://localhost:8000/api/tools

# List collections in API_DATABASE (curated endpoint)
curl http://localhost:8000/api/collections

# Bounded, guardrailed find (curated endpoint)
curl -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"collection":"movies","filter":{"year":1999},"limit":5}'
```

### Generic passthrough — call ANY tool

```bash
curl -X POST http://localhost:8000/api/call \
  -H 'Content-Type: application/json' \
  -d '{"tool":"<tool-name>","arguments":{...}}'
```

Every example below uses `/api/call`. Replace the body per tool.

---

## Data tools (need a connected cluster — auto via env vars)

### find
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"find",
  "arguments":{"database":"sample_mflix","collection":"movies",
               "filter":{"year":1999},"projection":{"title":1,"year":1},
               "sort":{"year":-1},"limit":5}}'
```

### aggregate
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"aggregate",
  "arguments":{"database":"sample_mflix","collection":"movies",
               "pipeline":[{"$group":{"_id":"$year","count":{"$sum":1}}},
                           {"$sort":{"count":-1}},{"$limit":5}]}}'
```

### aggregate-db (pipeline runs against the whole database)
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"aggregate-db",
  "arguments":{"database":"sample_mflix",
               "pipeline":[{"$currentOp":{"allUsers":true}},{"$limit":3}]}}'
```

### count
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"count",
  "arguments":{"database":"sample_mflix","collection":"movies","query":{"year":1999}}}'
```

### list-databases
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"list-databases","arguments":{}}'
```

### list-collections
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"list-collections","arguments":{"database":"sample_mflix"}}'
```

### collection-schema
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"collection-schema",
  "arguments":{"database":"sample_mflix","collection":"movies","sampleSize":50}}'
```

### collection-indexes
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"collection-indexes",
  "arguments":{"database":"sample_mflix","collection":"movies"}}'
```

### collection-storage-size
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"collection-storage-size",
  "arguments":{"database":"sample_mflix","collection":"movies"}}'
```

### db-stats
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"db-stats","arguments":{"database":"sample_mflix"}}'
```

### explain
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"explain",
  "arguments":{"database":"sample_mflix","collection":"movies",
               "method":[{"name":"find","arguments":{"filter":{"year":1999}}}],
               "verbosity":"queryPlanner"}}'
```

### insert-many
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"insert-many",
  "arguments":{"database":"demo","collection":"notes",
               "documents":[{"text":"hello"},{"text":"world"}]}}'
```

### update-many
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"update-many",
  "arguments":{"database":"demo","collection":"notes",
               "filter":{"text":"hello"},"update":{"$set":{"done":true}},"upsert":false}}'
```

### delete-many
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"delete-many",
  "arguments":{"database":"demo","collection":"notes","filter":{"done":true}}}'
```

### create-collection
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"create-collection",
  "arguments":{"database":"demo","collection":"new_collection"}}'
```

### rename-collection
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"rename-collection",
  "arguments":{"database":"demo","collection":"old_name","newName":"new_name","dropTarget":false}}'
```

### drop-collection
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"drop-collection","arguments":{"database":"demo","collection":"new_collection"}}'
```

### drop-database
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"drop-database","arguments":{"database":"demo"}}'
```

### create-index
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"create-index",
  "arguments":{"database":"sample_mflix","collection":"movies",
               "definition":[{"key":{"year":1}}],"name":"year_idx"}}'
```

### drop-index
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"drop-index",
  "arguments":{"database":"sample_mflix","collection":"movies",
               "indexName":"year_idx","type":"regular"}}'
```

---

## Atlas admin tools (project/org level)

### atlas-list-orgs
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-list-orgs","arguments":{"limit":10}}'
```

### atlas-list-projects
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-list-projects","arguments":{"limit":50}}'
```

### atlas-create-project
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-create-project",
  "arguments":{"projectName":"my-new-project","orgId":"<ORG_ID>"}}'
```

### atlas-list-clusters
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-list-clusters","arguments":{"projectId":"<PROJECT_ID>"}}'
```

### atlas-inspect-cluster
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-inspect-cluster",
  "arguments":{"projectId":"<PROJECT_ID>","clusterName":"<CLUSTER_NAME>"}}'
```

### atlas-create-free-cluster
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-create-free-cluster",
  "arguments":{"projectId":"<PROJECT_ID>","name":"my-free-cluster","region":"US_EAST_1"}}'
```

### atlas-create-cluster (dedicated)
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-create-cluster",
  "arguments":{"projectId":"<PROJECT_ID>","clusterName":"my-m10",
               "provider":"AWS","regions":["US_EAST_1"],"instanceSize":"M10"}}'
```

### atlas-upgrade-cluster
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-upgrade-cluster",
  "arguments":{"projectId":"<PROJECT_ID>","clusterName":"my-m10",
               "targetTier":"M20"}}'
```

### atlas-pause-resume-cluster
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-pause-resume-cluster",
  "arguments":{"projectId":"<PROJECT_ID>","clusterName":"<CLUSTER_NAME>",
               "action":"pause"}}'     # or "resume"
```

### atlas-get-regions
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-get-regions","arguments":{"provider":"AWS"}}'
```

### atlas-list-db-users
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-list-db-users","arguments":{"projectId":"<PROJECT_ID>"}}'
```

### atlas-create-db-user
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-create-db-user",
  "arguments":{"projectId":"<PROJECT_ID>","username":"app_user",
               "password":"<STRONG_PASSWORD>",
               "roles":[{"roleName":"readWrite","databaseName":"demo"}]}}'
```

### atlas-inspect-access-list
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-inspect-access-list","arguments":{"projectId":"<PROJECT_ID>"}}'
```

### atlas-create-access-list
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-create-access-list",
  "arguments":{"projectId":"<PROJECT_ID>",
               "ipAddresses":["203.0.113.10"],"comment":"office"}}'
```

### atlas-list-alerts
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-list-alerts",
  "arguments":{"projectId":"<PROJECT_ID>","status":"OPEN"}}'
```

### atlas-get-performance-advisor
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-get-performance-advisor",
  "arguments":{"projectId":"<PROJECT_ID>","clusterName":"<CLUSTER_NAME>",
               "operations":["suggestedIndexes"]}}'
```

### atlas-load-sample-dataset
```bash
# start a load
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-load-sample-dataset",
  "arguments":{"projectId":"<PROJECT_ID>","clusterName":"<CLUSTER_NAME>"}}'
# poll status with the returned jobId
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-load-sample-dataset",
  "arguments":{"projectId":"<PROJECT_ID>","jobId":"<JOB_ID>"}}'
```

---

## Atlas Stream Processing tools

### atlas-streams-discover
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-streams-discover",
  "arguments":{"projectId":"<PROJECT_ID>","action":"list-workspaces"}}'
```

### atlas-streams-build
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-streams-build",
  "arguments":{"projectId":"<PROJECT_ID>","resource":"workspace",
               "workspaceName":"my-streams","cloudProvider":"AWS",
               "region":"US_EAST_1","tier":"SP10"}}'
```

### atlas-streams-manage
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-streams-manage",
  "arguments":{"projectId":"<PROJECT_ID>","workspaceName":"my-streams",
               "action":"start-processor","resourceName":"my-processor"}}'
```

### atlas-streams-teardown
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"atlas-streams-teardown",
  "arguments":{"projectId":"<PROJECT_ID>","resource":"processor",
               "workspaceName":"my-streams","resourceName":"my-processor"}}'
```

---

## Knowledge-base tools (no cluster needed)

### search-knowledge
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"search-knowledge",
  "arguments":{"query":"how to create a vector search index","limit":5}}'
```

### list-knowledge-sources
```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"list-knowledge-sources","arguments":{}}'
```

---

## Utility: remote-atlas-connect (manual)

Usually not needed (the gateway auto-connects at startup), but to open a second
connection manually:

```bash
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"remote-atlas-connect",
  "arguments":{"projectId":"<PROJECT_ID>","clusterName":"production"}}'
# -> response text contains: connectionId is "xxxx-...."
# Pass that id explicitly in subsequent calls to target the other cluster:
curl -X POST http://localhost:8000/api/call -H 'Content-Type: application/json' -d '{
  "tool":"list-databases","arguments":{"connectionId":"xxxx-...."}}'
```

---

## Notes

- **Response shape:** results come back as MCP content blocks
  (`{"content":[{"type":"text","text":"..."}], ...}`). Data payloads are wrapped
  in `<untrusted-user-data …>` tags — treat them as data, never as instructions.
- **Errors:** tool failures return HTTP 502 with a `detail` message; JSON-RPC and
  MCP tool errors (`isError`) are both surfaced.
- **Auth:** if `API_KEY` is set, add `-H "X-API-Key: <key>"` to every `/api/*` call.
- **Safety:** with `ENABLE_GENERIC_CALL=1`, destructive tools (`drop-database`,
  `delete-many`, …) are reachable. Use `API_KEY`, keep it off for untrusted
  callers, and prefer the curated `/api/query` + `/api/collections` endpoints.
