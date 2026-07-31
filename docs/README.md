# OAuth Access Token Demo

This guide walks through obtaining an OAuth access token against MongoDB Atlas using either the **Authorization Code (PKCE) flow** via `get_token.py` or the **Client Credentials flow** via `curl`, calling the Atlas Admin API directly with `curl`, and running a local **FastAPI** proxy server that wraps those same APIs.

---

## Getting Your OAuth Client Credentials

Before you can run any OAuth flow, you need a `client_id` (and optionally a `client_secret`) that is registered with the MongoDB Atlas OAuth provider.

### Current model — manual partner onboarding (early access)

MongoDB Atlas OAuth is currently **invite-only**. Client credentials are not self-provisioned. Instead:

1. **Register as a partner** — work with your MongoDB partner or solutions contact to initiate onboarding.
2. **MongoDB manually provisions your OAuth app** — the MongoDB team creates an OAuth app registration in the Atlas OAuth platform (dev, staging, or production) with the `redirect_uris`, `grant_types`, `resources`, and other settings you agree on.
3. **MongoDB shares your credentials** — once provisioned, your MongoDB contact provides:
   - `client_id` — always provided (a UUID such as `dummy-id-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
   - `client_secret` — only for **confidential clients** (web apps / backend services). Public clients (SPAs, native apps) use `token_endpoint_auth_method: none` and receive a `client_id` only.

> **Public vs. confidential clients:**
> If your app is a browser-based SPA or a native/mobile app, you will receive a `client_id` only — leave `CLIENT_SECRET` blank in `.env`. If your app has a secure backend server, you will receive both a `client_id` and a `client_secret`.

### Future model — self-serve via Atlas UI

The planned self-serve registration experience will allow partners to create and manage their OAuth apps directly in the Atlas UI without MongoDB involvement:

```
Atlas UI → Organization → Integrations → OAuth Apps → Create App
```

Credentials will be displayed immediately after creation. This guide will be updated when self-serve becomes generally available.

### For this demo

This repository ships with a pre-provisioned **Partner Test SPA** client for the dev environment:

```ini
CLIENT_ID=dummy-id-xxxx-xxxx-xxxx-xxxxxxxxxxxx
# No CLIENT_SECRET — this is a public SPA client
```

You can use these credentials as-is to test the Authorization Code + PKCE flow against `https://cloud-dev.mongodb.com`. When you are ready to use your own registered app, replace the `CLIENT_ID` (and `CLIENT_SECRET` if applicable) in `oauthdemo/.env`.

---

## Environments

| Environment | Cloud Base                        | OAuth Base                           | API Base                           |
|-------------|-----------------------------------|--------------------------------------|------------------------------------|
| Dev         | https://cloud-dev.mongodb.com     | https://authorize-dev.mongodb.com    | https://api-dev.mongodb.com        |
| Staging     | https://cloud-stage.mongodb.com   | https://authorize-stage.mongodb.com  | https://api-stage.mongodb.com      |
| Production  | https://cloud.mongodb.com         | https://authorize.mongodb.com        | https://api.mongodb.com            |

### `.env` file (`oauthdemo/.env`)

```ini
CLIENT_ID=dummy-id-xxxx-xxxx-xxxx-xxxxxxxxxxxx
CLIENT_SECRET=                                    # confidential clients only
CLOUD_BASE=https://cloud-dev.mongodb.com
OAUTH_BASE=https://authorize-dev.mongodb.com
RESOURCE=https://api-dev.mongodb.com/api/atlas
REDIRECT_URI=http://localhost:3000/oauth/callback
```

> `CLIENT_ID` must match the `redirect_uri` registered for that client. The Partner Test SPA
> (`dummy-id-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) is registered with `http://localhost:3000/oauth/callback`.
> The acme-devtools public client (`dummy-id-yyyy-yyyy-yyyy-yyyyyyyyyyyy`) is registered with `http://127.0.0.1:8089`.
> Mixing them causes `Invalid request to preauthorize`.

---

## Part 1 — Register a Test User Account

### Dev

Requires a tagged email. Register at:
```
https://cloud-dev.mongodb.com/account/register
```
Use email formatted as `yourname+mongodb.com@gmail.com`.
Gmail delivers to your real inbox. **Sign in with the same tagged email.**

### Staging

No restrictions. Register at:
```
https://cloud-stage.mongodb.com/account/register
```

### Production / Own Organization

```
https://cloud.mongodb.com/account/register
```

After registration, note your **Organization ID** from the Atlas URL:
```
https://cloud.mongodb.com/v2#/org/{ORG_ID}/...
```

---

## Part 2 — Create a Service Account

Required to call the Atlas Admin API programmatically and to enable delegated partner access.

1. Log in to the Atlas UI for your environment.
2. Click **Access Manager** → **Organization Access** in the left sidebar.
3. Click the **Applications** tab → **Service Accounts** → **Add New Service Account**.
4. Name it, set role to **Organization Owner**, click **Add Service Account**.
5. Copy the **Client ID** (`mdb_sa_id_...`) and **Client Secret** (`mdb_sa_sk_...`).
   > The secret is shown **only once**.
6. Add them to `oauthdemo/.env`:
   ```ini
   CLIENT_ID=mdb_sa_id_...
   CLIENT_SECRET=mdb_sa_sk_...
   ```

---

## Part 3 — Generate an Access Token

### Flow A — Client Credentials (Service Account, no browser)

#### curl
```bash
CLOUD_BASE=https://cloud-dev.mongodb.com
CLIENT_ID=mdb_sa_id_...
CLIENT_SECRET=mdb_sa_sk_...

ACCESS_TOKEN=$(curl -s -X POST "${CLOUD_BASE}/api/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n "${CLIENT_ID}:${CLIENT_SECRET}" | base64)" \
  -d "grant_type=client_credentials" | jq -r .access_token)

echo $ACCESS_TOKEN
```

#### Python script
```bash
python3 oauthdemo/get_token.py \
  --client-id     mdb_sa_id_... \
  --client-secret mdb_sa_sk_...
```

---

### Flow B — Authorization Code + PKCE (User Delegated, browser required)

> The Partner Test SPA client (`dummy-id-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) only issues access tokens — no refresh tokens.
> Token lifetime is 600 seconds. Re-run the browser flow when it expires.

#### Python script (recommended)
```bash
python3 oauthdemo/get_token.py
```
The script opens a browser, catches the callback at `http://localhost:3000/oauth/callback`,
exchanges the code for a token, and saves it to `oauthdemo/.token_store.json`.

#### curl (manual PKCE steps)

**Step 1 — Generate PKCE values:**
```bash
CODE_VERIFIER=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
CODE_CHALLENGE=$(python3 -c "
import base64, hashlib, sys
v = sys.argv[1].encode()
print(base64.urlsafe_b64encode(hashlib.sha256(v).digest()).rstrip(b'=').decode())
" "$CODE_VERIFIER")
```

**Step 2 — Open in browser** (replace `<CODE_CHALLENGE>` and `<STATE>`):
```
https://cloud-dev.mongodb.com/oauth/authorize
  ?response_type=code
  &client_id=dummy-id-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  &redirect_uri=http://localhost:3000/oauth/callback
  &code_challenge=<CODE_CHALLENGE>
  &code_challenge_method=S256
  &state=<random_string>
  &resource=https://api-dev.mongodb.com/api/atlas
```

**Step 3 — Copy the `code` from the callback URL:**
```
http://localhost:3000/oauth/callback?code=<AUTHORIZATION_CODE>&...
```

**Step 4 — Exchange the code:**
```bash
ACCESS_TOKEN=$(curl -s -X POST "https://authorize-dev.mongodb.com/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=<AUTHORIZATION_CODE>" \
  -d "code_verifier=${CODE_VERIFIER}" \
  -d "redirect_uri=http://localhost:3000/oauth/callback" \
  -d "client_id=dummy-id-xxxx-xxxx-xxxx-xxxxxxxxxxxx" | jq -r .access_token)
```

#### CLI flags
```bash
python3 oauthdemo/get_token.py \
  --client-id     dummy-id-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --oauth-base    https://authorize-dev.mongodb.com \
  --cloud-base    https://cloud-dev.mongodb.com \
  --resource      https://api-dev.mongodb.com/api/atlas \
  --redirect-port 3000
```

#### Read stored token in other scripts
```bash
ACCESS_TOKEN=$(python3 -c \
  "import json; print(json.load(open('oauthdemo/.token_store.json'))['access_token'])")
```

---

### Flow C — Refresh Token

Only available if the client has `refresh_token` in `grant_types`.

```bash
# Load stored refresh token automatically
python3 oauthdemo/get_token.py --refresh-token

# Pass explicitly
python3 oauthdemo/get_token.py --refresh-token <token>
```

---

## Part 4 — Enable Delegated Partner Access

Required before delegated (user) tokens can call the Atlas Admin API.
Use the **service account token** from Flow A.

```bash
CLOUD_BASE=https://cloud-dev.mongodb.com
ORG_ID=<your_org_id>

# Enable
curl -s -X PATCH \
  "${CLOUD_BASE}/api/atlas/v2/orgs/${ORG_ID}/delegationSettings" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d '{"delegatedPartnerAccess": "READ_WRITE"}' | jq .

# Verify
curl -s "${CLOUD_BASE}/api/atlas/v2/orgs/${ORG_ID}/delegationSettings" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

Expected:
```json
{ "delegatedPartnerAccess": "READ_WRITE" }
```

---

## Part 5 — Atlas Admin API Reference

All requests require:
```
Authorization: Bearer <access_token>
Accept: application/vnd.atlas.2025-03-12+json
```

Set these variables before running the curl commands:
```bash
API_BASE=https://api-dev.mongodb.com
ACCESS_TOKEN=<your_access_token>
ORG_ID=<your_org_id>
PROJECT_ID=<your_project_id>
CLUSTER_NAME=<your_cluster_name>
```

---

### List Organizations

#### curl
```bash
curl -s "${API_BASE}/api/atlas/v2/orgs" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

#### Python
```python
import json, urllib.request

API_BASE     = "https://api-dev.mongodb.com"
ACCESS_TOKEN = json.load(open("oauthdemo/.token_store.json"))["access_token"]

req = urllib.request.Request(
    f"{API_BASE}/api/atlas/v2/orgs",
    headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/vnd.atlas.2025-03-12+json",
    },
)
with urllib.request.urlopen(req) as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))
```

---

### List Projects in an Organization

#### curl
```bash
curl -s "${API_BASE}/api/atlas/v2/groups?orgId=${ORG_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

#### Python
```python
req = urllib.request.Request(
    f"{API_BASE}/api/atlas/v2/groups?orgId={ORG_ID}",
    headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/vnd.atlas.2025-03-12+json",
    },
)
with urllib.request.urlopen(req) as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))
```

---

### Create a Project

#### curl
```bash
curl -s -X POST "${API_BASE}/api/atlas/v2/groups" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d "{\"name\": \"my-project\", \"orgId\": \"${ORG_ID}\"}" | jq .
```

#### Python
```python
import json, urllib.request

payload = json.dumps({"name": "my-project", "orgId": ORG_ID}).encode()
req = urllib.request.Request(
    f"{API_BASE}/api/atlas/v2/groups",
    data=payload,
    method="POST",
    headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/vnd.atlas.2025-03-12+json",
        "Content-Type": "application/vnd.atlas.2025-03-12+json",
    },
)
with urllib.request.urlopen(req) as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))
```

---

### Create a Cluster

#### curl
```bash
curl -s -X POST "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d '{
    "name": "'"${CLUSTER_NAME}"'",
    "clusterType": "REPLICASET",
    "replicationSpecs": [{
      "regionConfigs": [{
        "providerName": "TENANT",
        "backingProviderName": "AWS",
        "regionName": "US_EAST_1",
        "priority": 7,
        "electableSpecs": { "instanceSize": "M0" }
      }]
    }]
  }' | jq .
```

#### Python
```python
payload = json.dumps({
    "name": CLUSTER_NAME,
    "clusterType": "REPLICASET",
    "replicationSpecs": [{
        "regionConfigs": [{
            "providerName": "TENANT",
            "backingProviderName": "AWS",
            "regionName": "US_EAST_1",
            "priority": 7,
            "electableSpecs": {"instanceSize": "M0"},
        }]
    }]
}).encode()

req = urllib.request.Request(
    f"{API_BASE}/api/atlas/v2/groups/{PROJECT_ID}/clusters",
    data=payload,
    method="POST",
    headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/vnd.atlas.2025-03-12+json",
        "Content-Type": "application/vnd.atlas.2025-03-12+json",
    },
)
with urllib.request.urlopen(req) as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))
```

---

### Get Cluster Status

#### curl
```bash
curl -s "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

#### Python
```python
req = urllib.request.Request(
    f"{API_BASE}/api/atlas/v2/groups/{PROJECT_ID}/clusters/{CLUSTER_NAME}",
    headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/vnd.atlas.2025-03-12+json",
    },
)
with urllib.request.urlopen(req) as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))
```

---

### Delete a Cluster

#### curl
```bash
curl -s -X DELETE \
  "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

#### Python
```python
req = urllib.request.Request(
    f"{API_BASE}/api/atlas/v2/groups/{PROJECT_ID}/clusters/{CLUSTER_NAME}",
    method="DELETE",
    headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/vnd.atlas.2025-03-12+json",
    },
)
with urllib.request.urlopen(req) as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))
```

---

## Part 6 — FastAPI Proxy Server

`api.py` exposes all the above Atlas operations as a local REST API.
It reads the access token automatically from `oauthdemo/.token_store.json`.

### Setup

```bash
cd oauthdemo
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Start the server

The server must be started from inside the `oauthdemo/` directory so Python can locate the `api` module.

```bash
# Step 1 — authenticate (from repo root)
python3 oauthdemo/get_token.py

# Step 2 — start the API server (must cd into oauthdemo first)
cd oauthdemo
source .venv/bin/activate
uvicorn api:app --reload --port 8080
```

Interactive docs available at: `http://localhost:8080/docs`

---

### Endpoints

| Method   | Path                                              | Description                     |
|----------|---------------------------------------------------|---------------------------------|
| `GET`    | `/health`                                         | Token store status              |
| `POST`   | `/auth/refresh`                                   | Refresh access token            |
| `GET`    | `/orgs`                                           | List Organizations              |
| `GET`    | `/orgs/{org_id}/projects`                         | List Projects in an Org         |
| `POST`   | `/projects`                                       | Create a Project                |
| `GET`    | `/projects/{project_id}/clusters`                 | List Clusters in a Project      |
| `POST`   | `/projects/{project_id}/clusters`                 | Create a Cluster                |
| `GET`    | `/projects/{project_id}/clusters/{cluster_name}`  | Get Cluster Status              |
| `DELETE` | `/projects/{project_id}/clusters/{cluster_name}`  | Delete a Cluster                |

---

### curl against the FastAPI server

**Health check:**
```bash
curl -s http://localhost:8080/health | jq .
```

**Refresh access token (uses stored refresh token automatically):**
```bash
curl -s -X POST http://localhost:8080/auth/refresh | jq .
```

**Refresh with an explicit refresh token:**
```bash
curl -s -X POST http://localhost:8080/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<your_refresh_token>"}' | jq .
```

**List Organizations:**
```bash
curl -s http://localhost:8080/orgs | jq .

# Filter by name
curl -s "http://localhost:8080/orgs?name=Acme" | jq .
```

**List Projects in an Organization:**
```bash
curl -s http://localhost:8080/orgs/${ORG_ID}/projects | jq .
```

**Create a Project:**
```bash
curl -s -X POST http://localhost:8080/projects \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"my-project\", \"org_id\": \"${ORG_ID}\"}" | jq .
```

**List Clusters:**
```bash
curl -s http://localhost:8080/projects/${PROJECT_ID}/clusters | jq .
```

**Create a Cluster:**
```bash
curl -s -X POST http://localhost:8080/projects/${PROJECT_ID}/clusters \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-cluster",
    "provider": "AWS",
    "region": "US_EAST_1",
    "instance_size": "M0"
  }' | jq .
```

**Get Cluster Status:**
```bash
curl -s http://localhost:8080/projects/${PROJECT_ID}/clusters/${CLUSTER_NAME} | jq .
```

**Delete a Cluster:**
```bash
curl -s -X DELETE \
  http://localhost:8080/projects/${PROJECT_ID}/clusters/${CLUSTER_NAME} | jq .
```

---

## Part 7 — Token Lifecycle

| Client type                          | Access token lifetime | Refresh token         |
|--------------------------------------|-----------------------|-----------------------|
| Partner Test SPA (`dummy-id-xxxx-...`)    | 600 s (10 min)        | Not issued            |
| Service account (client credentials) | 600 s (default)       | Not issued            |
| Confidential web app (if configured) | Configurable          | Issued if configured  |

When the token expires the FastAPI server returns `401`. Re-run `get_token.py` to get a new token — the server picks it up automatically on the next request.

```bash
python3 get_token.py   # from oauthdemo/ directory
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Invalid request to preauthorize` | `client_id` and `redirect_uri` mismatch | Check `.env` — `CLIENT_ID` must match the client registered with that `redirect_uri` |
| `406 INVALID_VERSION_DATE` | Missing `Accept` header | Add `-H "Accept: application/vnd.atlas.2025-03-12+json"` |
| `401` from FastAPI | Token expired or missing | Re-run `python3 get_token.py` |
| `405 Method Not Allowed` on `/authorize` | Wrong base URL | Use `CLOUD_BASE` for `/oauth/authorize`, not `OAUTH_BASE` |
| `OSError: [Errno 48] Address already in use` | Port 3000 still open | Run `lsof -ti:3000 \| xargs kill -9` |
| `PermissionError: [Errno 13]` | Port below 1024 | Use `--redirect-port 3000` or above |
| `403 Forbidden` on Atlas API | Delegated partner access not enabled | Follow Part 4 |
| `Authentication failed (E0000004)` | Non-employee email on internal SSO | Register standalone Atlas account at `/account/register` |
| Token not received after 5 min | Browser did not redirect | Re-run the script; PKCE state expired |
