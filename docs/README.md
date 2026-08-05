# MongoDB Atlas Admin API - V2 — Partner Integration Guide

This guide explains what the MongoDB Atlas Admin API - V2 is, how partners get onboarded, how to obtain and use OAuth tokens, and how to call the Atlas Admin API on behalf of your users.

---

## On this page

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Environments](#environments)
- [Get Your OAuth Credentials](#get-your-oauth-credentials)
- [Obtain an Access Token](#obtain-an-access-token)
- [Use the Access Token](#use-the-access-token)
- [Atlas Admin API Reference](#atlas-admin-api-reference)
- [Token Lifecycle](#token-lifecycle)
- [Run the FastAPI Demo Server](#run-the-fastapi-demo-server)
- [Set Up a Test Atlas Environment](#set-up-a-test-atlas-environment)
- [Troubleshooting](#troubleshooting)

---

## Overview

The **MongoDB Atlas Admin API - V2** lets a trusted third-party application call Atlas Admin API endpoints **on behalf of an authenticated Atlas user**, without ever seeing that user's credentials.

A partner application can use these APIs to:

| Operation | Endpoint | Method |
|---|---|---|
| List the user's Organizations | `/api/atlas/v2/orgs` | `GET` |
| List Projects in an Organization | `/api/atlas/v2/groups?orgId={orgId}` | `GET` |
| Create a Project | `/api/atlas/v2/groups` | `POST` |
| List Clusters in a Project | `/api/atlas/v2/groups/{projectId}/clusters` | `GET` |
| Create a Cluster | `/api/atlas/v2/groups/{projectId}/clusters` | `POST` |
| Get Cluster status | `/api/atlas/v2/groups/{projectId}/clusters/{name}` | `GET` |
| Delete a Cluster | `/api/atlas/v2/groups/{projectId}/clusters/{name}` | `DELETE` |

> [!NOTE]
> For detailed information on all available APIs, refer to the official [Atlas Administration API documentation](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2).

### Why this is different from a normal Atlas API call

Normally, calling the Atlas Admin API requires an API key belonging to the organization. With the MongoDB Atlas Admin API - V2 model:

- The **user logs in** to Atlas in their browser via standard OAuth.
- The partner app receives a short-lived **delegated access token** scoped to what that user is allowed to do.
- The partner app calls Atlas APIs using that token — **no org-level API key needed**.

The partner app never sees the user's password and holds only a short-lived, user-scoped token.

---

## How It Works

The flow follows **OAuth 2.1 Authorization Code + PKCE**:

```
User clicks "Connect to Atlas" in your app
          │
          ▼
Redirect to Atlas login
(cloud.mongodb.com/oauth/authorize?client_id=...&code_challenge=...&resource=...)
          │
          ▼  User logs in and grants consent
Atlas redirects back to your redirect_uri with an authorization code
          │
          ▼
Your backend POSTs the code + code_verifier to the token endpoint
(authorize.mongodb.com/tokens)
          │
          ▼
Token endpoint returns an access_token (and refresh_token if configured)
          │
          ▼
Your app calls the Atlas Admin API with:
  Authorization: Bearer <access_token>
  Accept: application/vnd.atlas.2025-03-12+json
```

---

## Environments

| Environment | Atlas UI | OAuth / Token Endpoint | Atlas Admin API |
|---|---|---|---|
| **Dev** | https://cloud-dev.mongodb.com | https://authorize-dev.mongodb.com | https://api-dev.mongodb.com |
| **Staging** | https://cloud-stage.mongodb.com | https://authorize-stage.mongodb.com | https://api-stage.mongodb.com |
| **Production** | https://cloud.mongodb.com | https://authorize.mongodb.com | https://api.mongodb.com |

### Example

Configure your environment in `oauthdemo/.env`:

```ini
CLIENT_ID=<client-id-provided-by-mongodb>
CLIENT_SECRET=             # confidential clients only — leave blank for public SPA clients
OAUTH_BASE=https://authorize-dev.mongodb.com
CLOUD_BASE=https://cloud-dev.mongodb.com
RESOURCE=https://api-dev.mongodb.com/api/atlas
REDIRECT_URI=http://localhost:3000/oauth/callback
```

> [!WARNING]
> `CLIENT_ID` must exactly match the `redirect_uri` registered for that client. Mixing them causes `Invalid request to preauthorize`.

---

## Get Your OAuth Credentials

MongoDB Atlas OAuth is currently **invite-only**. Client credentials are **not self-provisioned** — MongoDB provisions them manually on your behalf.

### Procedure

To get onboarded and receive credentials:

1. **Register as a partner.** Contact your MongoDB partner manager or solutions engineer to initiate onboarding.

1. **Agree on app configuration.** You and the MongoDB team align on `redirect_uris`, `client_type`, `grant_types`, and `resources`.

1. **MongoDB provisions your OAuth app.** The MongoDB team registers the app in the Atlas OAuth platform for your target environment (dev → staging → production).

1. **MongoDB shares your credentials**:

   | Client type | What you receive |
   |---|---|
   | **Public client** (SPA / native app) | `client_id` only — uses `token_endpoint_auth_method: none`, no secret |
   | **Confidential client** (web app with backend) | `client_id` **and** `client_secret` |

> [!NOTE]
> If you are integrating now, your MongoDB contact will provide your `client_id` and, if applicable, `client_secret`. You do not need to create or configure anything in the Atlas UI — MongoDB handles this during the onboarding process.

> [!WARNING]
> Store `client_secret` in a secrets manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault). Never commit it to source control or expose it to the browser.

### Future model — self-serve via Atlas UI

The planned self-serve experience will let partners register their own OAuth apps directly in Atlas without MongoDB team involvement:

```
Atlas UI → Organization → Integrations → OAuth Apps → Create App
```

Credentials will be shown immediately after creation. This guide will be updated when self-serve is generally available.

### Public vs. confidential clients

| | Public (`single_page_app`) | Confidential (`web_app`) |
|---|---|---|
| Has `client_secret` | No | Yes |
| Supports refresh tokens | No | Yes (if configured) |
| Token exchange | PKCE only | PKCE + HTTP Basic auth |
| Best for | Browser SPAs, native/mobile apps | Apps with a secure backend server |

---

## Obtain an Access Token

This section covers the two grant flows. **Flow A — Authorization Code + PKCE** is the primary flow for the MongoDB Atlas Admin API - V2 and produces a delegated token scoped to the logged-in user.

### Flow A — Authorization Code + PKCE (delegated user token, browser required)

#### Method 1: Python script (recommended)

```bash
python3 oauthdemo/get_token.py
```

The script:

1. Opens the Atlas login page in your browser.
1. Listens on `localhost:3000/oauth/callback` for the redirect.
1. Exchanges the authorization code for a token.
1. Saves the token to `oauthdemo/.token_store.json`.

#### Method 2: curl (manual steps)

To obtain a token manually with `curl`:

1. **Generate PKCE values:**

   ```bash
   CODE_VERIFIER=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   CODE_CHALLENGE=$(python3 -c "
   import base64, hashlib, sys
   v = sys.argv[1].encode()
   print(base64.urlsafe_b64encode(hashlib.sha256(v).digest()).rstrip(b'=').decode())
   " "$CODE_VERIFIER")
   ```

1. **Open this URL in your browser:**

   ```
   https://cloud-dev.mongodb.com/oauth/authorize
     ?response_type=code
     &client_id=<your-client-id>
     &redirect_uri=http://localhost:3000/oauth/callback
     &code_challenge=<CODE_CHALLENGE>
     &code_challenge_method=S256
     &state=<random-string>
     &resource=https://api-dev.mongodb.com/api/atlas
   ```

1. **Copy the `code` from the callback URL:**

   ```
   http://localhost:3000/oauth/callback?code=<AUTHORIZATION_CODE>&state=...
   ```

1. **Exchange the code for a token:**

   ```bash
   # Public client (no client_secret)
   ACCESS_TOKEN=$(curl -s -X POST "https://authorize-dev.mongodb.com/tokens" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=authorization_code" \
     -d "code=<AUTHORIZATION_CODE>" \
     -d "code_verifier=${CODE_VERIFIER}" \
     -d "redirect_uri=http://localhost:3000/oauth/callback" \
     -d "client_id=<your-client-id>" | jq -r .access_token)

   # Confidential client (with client_secret — use HTTP Basic auth)
   ACCESS_TOKEN=$(curl -s -X POST "https://authorize-dev.mongodb.com/tokens" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -H "Authorization: Basic $(echo -n '<client_id>:<client_secret>' | base64)" \
     -d "grant_type=authorization_code" \
     -d "code=<AUTHORIZATION_CODE>" \
     -d "code_verifier=${CODE_VERIFIER}" \
     -d "redirect_uri=http://localhost:3000/oauth/callback" | jq -r .access_token)
   ```

### Flow B — Refresh Token (confidential clients only)

Only available if `refresh_token` is in your client's `grant_types`.

```bash
# Using the Python script (loads stored refresh token automatically)
python3 oauthdemo/get_token.py --refresh-token

# Pass an explicit refresh token
python3 oauthdemo/get_token.py --refresh-token <token>

# Using curl
curl -s -X POST "https://authorize-dev.mongodb.com/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n '<client_id>:<client_secret>' | base64)" \
  -d "grant_type=refresh_token" \
  -d "refresh_token=<stored-refresh-token>" | jq .
```

> [!IMPORTANT]
> Always store the new `refresh_token` returned in the response — MongoDB may rotate it on each use.

---

## Use the Access Token

Once you have an access token, use it as a **Bearer token** on every Atlas Admin API request.

### Required headers

Every request requires these headers:

```
Authorization: Bearer <access_token>
Accept: application/vnd.atlas.2025-03-12+json
```

### Procedure

To verify your token works:

1. **Read the stored token:**

   ```bash
   ACCESS_TOKEN=$(python3 -c \
     "import json; print(json.load(open('oauthdemo/.token_store.json'))['access_token'])")
   ```

1. **Call an Atlas Admin API endpoint:**

   ```bash
   API_BASE=https://api-dev.mongodb.com

   curl -s "${API_BASE}/api/atlas/v2/orgs" \
     -H "Authorization: Bearer ${ACCESS_TOKEN}" \
     -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
   ```

### Result

A successful response lists the Atlas Organizations the authenticated user belongs to (and for which Delegated Partner Access is enabled).

### Token expiry

Access tokens are **short-lived** (typically 600 seconds / 10 minutes). When expired:

- Atlas returns `401 Unauthorized`.
- Re-run `python3 oauthdemo/get_token.py` for a new token (browser flow).
- Or use the refresh token flow if your client supports it.

### Example: inspect a token (debug)

Decode the JWT payload without a library (base64 only, no verification):

```bash
python3 -c "
import json, base64
token = open('oauthdemo/.token_store.json').read()
payload = json.loads(token)['access_token'].split('.')[1]
padding = 4 - len(payload) % 4
print(json.dumps(json.loads(base64.urlsafe_b64decode(payload + '='*padding)), indent=2))
"
```

---

## Atlas Admin API Reference

### Before you begin

Set these variables once before running any command:

```bash
API_BASE=https://api-dev.mongodb.com
ORG_ID=<your-org-id>
PROJECT_ID=<your-project-id>
CLUSTER_NAME=<your-cluster-name>

ACCESS_TOKEN=$(python3 -c \
  "import json; print(json.load(open('oauthdemo/.token_store.json'))['access_token'])")
```

### List Organizations

Returns all Atlas Organizations the authenticated user belongs to that have Delegated Partner Access enabled.

```bash
curl -s "${API_BASE}/api/atlas/v2/orgs" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .

# Filter by name
curl -s "${API_BASE}/api/atlas/v2/orgs?name=Acme" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

### List Projects in an Organization

```bash
curl -s "${API_BASE}/api/atlas/v2/groups?orgId=${ORG_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

### Create a Project

```bash
curl -s -X POST "${API_BASE}/api/atlas/v2/groups" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d "{\"name\": \"my-project\", \"orgId\": \"${ORG_ID}\"}" | jq .
```

> [!TIP]
> Copy the `id` field from the response — this is your `PROJECT_ID`.

### Create a Cluster

Creates a free **M0** cluster. Change `instanceSize` to `M10` or higher for dedicated tiers.

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

| Field | Options | Default |
|---|---|---|
| `backingProviderName` | `AWS`, `GCP`, `AZURE` | `AWS` |
| `regionName` | `US_EAST_1`, `EU_WEST_1`, `AP_SOUTHEAST_1`, … | `US_EAST_1` |
| `instanceSize` | `M0` (free), `M10`, `M20`, `M30`, … | `M0` |

### Get Cluster Status

```bash
curl -s "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .stateName
```

| `stateName` | Meaning |
|---|---|
| `CREATING` | Cluster is being provisioned |
| `IDLE` | Cluster is running and ready |
| `UPDATING` | Configuration change in progress |
| `DELETING` | Cluster is being deleted |

### Example: poll until ready

```bash
until [ "$(curl -s "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq -r .stateName)" = "IDLE" ]; do
  echo "Waiting..."; sleep 15
done && echo "Cluster is ready."
```

### Delete a Cluster

> [!WARNING]
> Deletion is permanent and irreversible.

```bash
curl -s -X DELETE \
  "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

---

## Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| **Delegated user access token** | 600 s (10 min) | Use for all Atlas Admin API calls |
| **Refresh token** | Configured per client (e.g. 30 days) | Confidential clients only; always store the latest rotated value |

When a token expires, Atlas returns `401 Unauthorized`. Re-authenticate via the browser flow or use the refresh token if your client supports it.

---

## Run the FastAPI Demo Server

`api.py` is a local FastAPI proxy that wraps the Atlas Admin API and reads the access token automatically from `oauthdemo/.token_store.json`.

### Before you begin

Install the dependencies:

```bash
cd oauthdemo
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Procedure

1. **Get an access token** (from repo root):

   ```bash
   python3 oauthdemo/get_token.py
   ```

1. **Start the server** (from `oauthdemo/`):

   ```bash
   cd oauthdemo
   source .venv/bin/activate
   uvicorn api:app --reload --port 8080
   ```

1. **Open the interactive docs:**

   http://localhost:8080/docs

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Token store status and expiry |
| `POST` | `/auth/refresh` | Refresh access token |
| `GET` | `/orgs` | List Organizations |
| `GET` | `/orgs/{org_id}/projects` | List Projects in an Org |
| `POST` | `/projects` | Create a Project |
| `GET` | `/projects/{project_id}/clusters` | List Clusters |
| `POST` | `/projects/{project_id}/clusters` | Create a Cluster |
| `GET` | `/projects/{project_id}/clusters/{cluster_name}` | Get Cluster Status |
| `DELETE` | `/projects/{project_id}/clusters/{cluster_name}` | Delete a Cluster |

### Examples

```bash
BASE=http://localhost:8080

# Health check
curl -s ${BASE}/health | jq .

# List orgs
curl -s ${BASE}/orgs | jq .

# List projects
curl -s ${BASE}/orgs/${ORG_ID}/projects | jq .

# Create a project
curl -s -X POST ${BASE}/projects \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"my-project\", \"org_id\": \"${ORG_ID}\"}" | jq .

# Create a cluster
curl -s -X POST ${BASE}/projects/${PROJECT_ID}/clusters \
  -H "Content-Type: application/json" \
  -d '{"name": "my-cluster", "provider": "AWS", "region": "US_EAST_1", "instance_size": "M0"}' | jq .

# Get cluster status
curl -s ${BASE}/projects/${PROJECT_ID}/clusters/${CLUSTER_NAME} | jq .stateName

# Delete a cluster
curl -s -X DELETE ${BASE}/projects/${PROJECT_ID}/clusters/${CLUSTER_NAME} | jq .
```

---

## Set Up a Test Atlas Environment

> [!NOTE]
> **This section is for self-testing only.** It walks through setting up your own Atlas account and service account so you can test the full delegated flow end-to-end **without depending on MongoDB to provision accounts for you**.
>
> In a real partner integration, your **end users** are the ones with existing Atlas accounts. They log in with their own credentials — you do not create accounts for them. The service account and Delegated Partner Access setup below is done **by you (the partner/developer)** in your own test Atlas organization during development.

### Step 1: Register an Atlas test account

**Dev environment** (requires a tagged email):

```
https://cloud-dev.mongodb.com/account/register
```

Use a tagged email — insert `+mongodb.com` before the `@`:

| Your real email | Register with |
|---|---|
| `you@gmail.com` | `you+mongodb.com@gmail.com` |
| `eng@company.com` | `eng+mongodb.com@company.com` |

> [!TIP]
> Always sign in with the same tagged address used at registration.

**Staging / Production** (no email restrictions):

```
https://cloud-stage.mongodb.com/account/register   # staging
https://cloud.mongodb.com/account/register          # production
```

After registration, note your **Organization ID** from the Atlas URL:

```
https://cloud-dev.mongodb.com/v2#/org/<ORG_ID>/...
```

### Step 2: Create a service account

A service account lets you enable Delegated Partner Access on your test organization programmatically. This is a one-time setup per organization.

> [!IMPORTANT]
> The service account `client_id` / `client_secret` (`mdb_sa_id_...` / `mdb_sa_sk_...`) are **only used here** to enable delegated access on your own test org. They are **not** used for the partner OAuth flow itself. For the actual OAuth flow that your end users go through, you use the **MongoDB-provided partner `client_id`** from [Get Your OAuth Credentials](#get-your-oauth-credentials).

To create a service account:

1. Log in to the Atlas UI for your environment.
1. In the left sidebar, click **Access Manager** → **Organization Access**.
1. Click the **Applications** tab → **Service Accounts** → **Add New Service Account**.
1. Name it (e.g. `partner-test-sa`), set the role to **Organization Owner**, and click **Add Service Account**.
1. Copy the **Client ID** (`mdb_sa_id_...`) and **Client Secret** (`mdb_sa_sk_...`).

> [!WARNING]
> The client secret is shown **only once**. Store it immediately — you cannot retrieve it again.

### Step 3: Get a service account token

```bash
CLOUD_BASE=https://cloud-dev.mongodb.com
SA_CLIENT_ID=mdb_sa_id_...
SA_CLIENT_SECRET=mdb_sa_sk_...

SA_TOKEN=$(curl -s -X POST "${CLOUD_BASE}/api/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n "${SA_CLIENT_ID}:${SA_CLIENT_SECRET}" | base64)" \
  -d "grant_type=client_credentials" | jq -r .access_token)

echo "Service account token: ${SA_TOKEN}"
```

Or using the Python script:

```bash
python3 oauthdemo/get_token.py \
  --client-id     mdb_sa_id_... \
  --client-secret mdb_sa_sk_...
```

### Step 4: Enable Delegated Partner Access

This setting must be enabled on your test organization before delegated user tokens can call the Atlas Admin API.

```bash
API_BASE=https://api-dev.mongodb.com
ORG_ID=<your-org-id>

# Check current setting
curl -s "${API_BASE}/api/atlas/v2/orgs/${ORG_ID}/delegationSettings" \
  -H "Authorization: Bearer ${SA_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .

# Enable READ_WRITE access
curl -s -X PATCH \
  "${API_BASE}/api/atlas/v2/orgs/${ORG_ID}/delegationSettings" \
  -H "Authorization: Bearer ${SA_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d '{"delegatedPartnerAccess": "READ_WRITE"}' | jq .
```

### Result

Expected response:

```json
{ "delegatedPartnerAccess": "READ_WRITE" }
```

Once enabled, any delegated user token obtained via the partner OAuth flow (see [Obtain an Access Token](#obtain-an-access-token)) can call the Atlas Admin API for this organization. This setting is **permanent per org** — you only do it once.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Invalid request to preauthorize` | `client_id` or `redirect_uri` mismatch | `CLIENT_ID` in `.env` must exactly match the value MongoDB provisioned for that `redirect_uri` |
| `406 INVALID_VERSION_DATE` | Missing `Accept` header | Add `-H "Accept: application/vnd.atlas.2025-03-12+json"` to every Atlas API request |
| `401 Unauthorized` from Atlas API | Access token expired | Re-run `python3 oauthdemo/get_token.py` or use the refresh token flow |
| `401` from FastAPI server | Token expired or not yet obtained | Re-run `python3 oauthdemo/get_token.py` |
| `403 Forbidden` on Atlas API | Delegated Partner Access not enabled on the user's org | Complete [Step 4: Enable Delegated Partner Access](#step-4-enable-delegated-partner-access), or ask the user to enable it in their org settings |
| `405 Method Not Allowed` on `/authorize` | Wrong base URL | Use `CLOUD_BASE` for `/oauth/authorize`, not `OAUTH_BASE` |
| `400 invalid_grant` | Authorization code already used or expired | Codes are single-use — restart the auth flow |
| `400 grant_type not supported` | Refresh token used on a public client | Public clients do not support refresh tokens — re-run the browser flow |
| `Authentication failed (E0000004)` | Dev login with base email instead of tagged email | Use `you+mongodb.com@gmail.com` format for dev accounts |
| `OSError: [Errno 48] Address already in use` | Port 3000 in use from a previous run | Script auto-frees the port; or run `lsof -ti:3000 \| xargs kill -9` |
| `PermissionError: [Errno 13]` | Port below 1024 requires root | Use `--redirect-port 3000` or above |
| `Could not import module "api"` | uvicorn started from wrong directory | `cd oauthdemo` first, then run `uvicorn api:app` |
| Token not received after 5 minutes | Browser did not redirect to localhost | Re-run the script — PKCE state expired |

---

## Next steps

- [Partner Onboarding Guide](PARTNER.md) — register with MongoDB and integrate the flow into your product
- [Atlas Administration API reference](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2) — full endpoint documentation
