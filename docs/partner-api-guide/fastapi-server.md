---
id: fastapi-server
sidebar_position: 4
title: FastAPI Demo Server
description: Run the local FastAPI proxy server that wraps the Atlas Partner API.
---

# FastAPI Demo Server

`api.py` is a local FastAPI proxy that wraps the Atlas Admin API. It reads the access token automatically from `oauthdemo/.token_store.json` so you do not need to pass `Authorization` headers in every request.

## Setup

```bash
cd oauthdemo
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Start the server

```bash
# Step 1 — authenticate (from repo root)
python3 oauthdemo/get_token.py

# Step 2 — start the server (must run from oauthdemo/)
cd oauthdemo
source .venv/bin/activate
uvicorn api:app --reload --port 8080
```

Interactive API docs are available at: **http://localhost:8080/docs**

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Token store status and expiry |
| `POST` | `/auth/refresh` | Refresh access token |
| `GET` | `/orgs` | List Organizations |
| `GET` | `/orgs/{org_id}/projects` | List Projects in an Org |
| `POST` | `/projects` | Create a Project |
| `GET` | `/projects/{project_id}/clusters` | List Clusters in a Project |
| `POST` | `/projects/{project_id}/clusters` | Create a Cluster |
| `GET` | `/projects/{project_id}/clusters/{cluster_name}` | Get Cluster Status |
| `DELETE` | `/projects/{project_id}/clusters/{cluster_name}` | Delete a Cluster |

## curl examples

Set variables once:

```bash
BASE=http://localhost:8080
ORG_ID=<your-org-id>
PROJECT_ID=<your-project-id>
CLUSTER_NAME=<your-cluster-name>
```

**Health check:**
```bash
curl -s ${BASE}/health | jq .
```

**List Organizations:**
```bash
curl -s ${BASE}/orgs | jq .

# Filter by name
curl -s "${BASE}/orgs?name=Acme" | jq .
```

**List Projects:**
```bash
curl -s ${BASE}/orgs/${ORG_ID}/projects | jq .
```

**Create a Project:**
```bash
curl -s -X POST ${BASE}/projects \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"my-project\", \"org_id\": \"${ORG_ID}\"}" | jq .
```

**Create a Cluster:**
```bash
curl -s -X POST ${BASE}/projects/${PROJECT_ID}/clusters \
  -H "Content-Type: application/json" \
  -d '{
    "name": "'"${CLUSTER_NAME}"'",
    "provider": "AWS",
    "region": "US_EAST_1",
    "instance_size": "M0"
  }' | jq .
```

**Get Cluster Status:**
```bash
curl -s ${BASE}/projects/${PROJECT_ID}/clusters/${CLUSTER_NAME} | jq .stateName
```

**Delete a Cluster:**
```bash
curl -s -X DELETE \
  ${BASE}/projects/${PROJECT_ID}/clusters/${CLUSTER_NAME} | jq .
```

**Refresh access token:**
```bash
# Use stored refresh token automatically
curl -s -X POST ${BASE}/auth/refresh | jq .

# Pass an explicit refresh token
curl -s -X POST ${BASE}/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<your-refresh-token>"}' | jq .
```

## Token expiry

When the token expires the server returns `401`. Re-run `get_token.py` — the server picks up the new token automatically on the next request:

```bash
python3 oauthdemo/get_token.py
```
