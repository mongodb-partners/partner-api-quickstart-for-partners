# Atlas App Connections — Partner Integration Guide (Partner API)

This guide explains what **Atlas App Connections** is, how partners get onboarded, how to obtain and use OAuth tokens, and how to call the Atlas Administration API on behalf of your users (the **Partner API** path).

> [!NOTE]
> MongoDB's official documentation now covers this integration at [Integrate Your App with Atlas App Connections](https://www.mongodb.com/docs/atlas/app-connections/partner-integration-guide/). This kit mirrors that guide and adds runnable scripts and UX/production guidance. For AI clients and agents, see the sibling path: the [MongoDB Atlas Managed MCP Server](https://www.mongodb.com/docs/mcp-server/remote-mcp/access-models) (Remote MCP).

It is the developer track of the **Connect MongoDB Atlas integration kit** — the building blocks behind the end-to-end journey described on the [landing page](../index.md):

```
Connect button → Atlas OAuth → delegated tokens → select/create
project + cluster → database user + network access → first read/write
```

- Want the complete journey with a runnable script? → [End-to-End Tutorial](END-TO-END.md)
- Designing the user experience? → [Partner UX Guide](UX-GUIDE.md)
- Hardening for launch? → [Production Readiness](PRODUCTION.md) · [Recovery Guide](RECOVERY.md)

> [!IMPORTANT]
> The runnable code in this repository (`get_token.py`, `api.py`, `end_to_end.py`) is a **development demo**: plaintext local token storage, a localhost callback, and one shared token. See [Demo vs. production](PRODUCTION.md#demo-vs-production) before building your real integration.

---

## On this page

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Environments](#environments)
- [Get Your OAuth Credentials](#get-your-oauth-credentials)
- [Obtain an Access Token](#obtain-an-access-token)
- [Use the Access Token](#use-the-access-token)
- [Atlas Admin API Reference](#atlas-admin-api-reference)
- [Run the FastAPI Demo Server](#run-the-fastapi-demo-server)
- [Set Up a Test Atlas Environment](#set-up-a-test-atlas-environment)
- [Troubleshooting](#troubleshooting)

---

## Overview

**Atlas App Connections** is the MongoDB Atlas OAuth 2.1 platform that lets a trusted third-party application call Atlas Administration API endpoints **on behalf of an authenticated Atlas user**, without ever seeing that user's credentials. "Partner API" is the direct integration path where your app calls the Atlas Administration API itself with the user's delegated permissions (no MCP server in between).

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
| Create a Database User | `/api/atlas/v2/groups/{projectId}/databaseUsers` | `POST` |
| Add an IP Access List entry | `/api/atlas/v2/groups/{projectId}/accessList` | `POST` |

The last two operations bridge from control plane to **data plane** — they are what let your application actually connect and read/write. The full journey is in the [End-to-End Tutorial](END-TO-END.md).

> [!NOTE]
> For detailed information on all available APIs, refer to the official [Atlas Administration API documentation](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2).

### Why this is different from a normal Atlas API call

Normally, calling the Atlas Administration API requires an API key or service account belonging to the organization. With Atlas App Connections delegated access:

- The **user logs in** to Atlas in their browser via standard OAuth 2.1 + PKCE.
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
(cloud.mongodb.com/oauth/authorize?client_id=...&code_challenge=...&state=...)
          │
          ▼  User logs in and grants consent
Atlas redirects back to your redirect_uri with an authorization code (+ state, iss)
          │
          ▼
Your backend POSTs the code + code_verifier to the token endpoint
(authorize.mongodb.com/tokens)
          │
          ▼
Token endpoint returns an access_token and a refresh_token
          │
          ▼
Your app calls the Atlas Administration API with:
  Authorization: Bearer <access_token>
  Accept: application/vnd.atlas.2025-03-12+json
```

> [!IMPORTANT]
> **Do not send a `resource` parameter** in the authorization request. The current Atlas authorization endpoint does not require one — send only `response_type`, `client_id`, `redirect_uri`, `code_challenge`, `code_challenge_method`, and `state`. The runnable demo in this repo still targets the dev environment, where a `resource` indicator is required — see [Environments](#environments).

On the callback, your handler must verify `state` (CSRF) **and** the `iss` parameter (must equal the authorization base, e.g. `https://authorize.mongodb.com`) to prevent authorization-server mix-up attacks. Authorization codes are single-use and expire within 10 minutes.

---

## Environments

Per the [official guide](https://www.mongodb.com/docs/atlas/app-connections/partner-integration-guide/): **develop and launch your integration against production — Atlas does not provide separate partner environments.** All OAuth and API endpoints use two production base URLs:

| Base | URL |
|---|---|
| Authorization base (`OAUTH_BASE`) | `https://authorize.mongodb.com` |
| Cloud base (`CLOUD_BASE`) | `https://cloud.mongodb.com` |

The authorization endpoint where users log in is on the cloud base (`{CLOUD_BASE}/oauth/authorize`), while the token endpoint is on the authorization base (`{OAUTH_BASE}/tokens`). The Atlas Administration API is hosted on the cloud base: `{CLOUD_BASE}/api/atlas`.

> [!TIP]
> **Discover endpoints automatically.** Atlas publishes OAuth 2.1 server metadata at `https://authorize.mongodb.com/.well-known/oauth-authorization-server`. Many OAuth client libraries can read it to configure endpoints without hardcoding URLs.

### Internal dev / staging environments

The dev and staging hosts below are MongoDB-internal environments. Use them only if your MongoDB partner contact provisioned your OAuth client there:

| Environment | Atlas UI | OAuth / Token Endpoint | Atlas Admin API |
|---|---|---|---|
| **Dev** (internal) | https://cloud-dev.mongodb.com | https://authorize-dev.mongodb.com | https://api-dev.mongodb.com |
| **Staging** (internal) | https://cloud-stage.mongodb.com | https://authorize-stage.mongodb.com | https://api-stage.mongodb.com |
| **Production** | https://cloud.mongodb.com | https://authorize.mongodb.com | https://cloud.mongodb.com/api/atlas |

### Example

Configure your environment in `.env`:

```ini
CLIENT_ID=<client-id-provided-by-mongodb>
CLIENT_SECRET=             # confidential clients only — leave blank for public SPA clients
OAUTH_BASE=https://authorize.mongodb.com
CLOUD_BASE=https://cloud.mongodb.com
RESOURCE=https://cloud.mongodb.com/api/atlas   # dev-environment clients only; omit for production clients
REDIRECT_URI=http://localhost:3000/oauth/callback
```

> [!WARNING]
> `CLIENT_ID` must exactly match the `redirect_uri` registered for that client. Mixing them causes `Invalid request to preauthorize`. Note that redirect URIs must use HTTPS in production — only loopback addresses (`localhost`, `127.0.0.1`, `::1`) may use HTTP.

---

## Get Your OAuth Credentials

Atlas App Connections is available to **approved design partners**. To become one, submit the [Become a Partner](https://www.mongodb.com/company/partners/) form and include **"Partner API"** in the More Information field. Client credentials are **not self-provisioned** — MongoDB registers your OAuth app and shares a `client_id` (plus a `client_secret` for confidential clients). You do not create or configure anything in the Atlas UI.

For the full onboarding process — what to provide, app configuration fields, and promotion from dev to production — see [Partner Onboarding](PARTNER.md). Self-serve registration via Atlas UI (Organization → Integrations → OAuth Apps) is planned; see [Partner Delegation](partner-delegations.md).

### Public vs. confidential clients

| | Public (`single_page_app`) | Confidential (`web_app`) |
|---|---|---|
| Has `client_secret` | No | Yes |
| Supports refresh tokens | No | Yes |
| Token exchange auth | `client_id` in body | HTTP Basic auth (or `client_secret` in body) |
| Best for | Browser SPAs, native/mobile apps | Apps with a secure backend server |

> [!TIP]
> **Prefer secret-less authentication.** Atlas supports secret-less authentication using PKCE, which removes the need to manage a `client_secret` altogether. Where your client type allows it, use secret-less authentication as the most secure option.

> [!WARNING]
> If you do use a confidential client, store `client_secret` in a secrets manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault). Never commit it to source control or expose it to the browser. To rotate a suspected-compromised secret, contact MongoDB.

> [!NOTE]
> **Don't confuse OAuth client credentials with other Atlas credentials.** The `client_id` / `client_secret` discussed in this guide belong to your partner OAuth app and are issued by MongoDB during onboarding. They are different from (a) **service account** credentials (`mdb_sa_id_...` / `mdb_sa_sk_...`) that you create yourself in Atlas for client-credentials access (see [Set Up a Test Atlas Environment](#set-up-a-test-atlas-environment)), and (b) the **MCP configuration** client ID/secret that Atlas generates when an admin creates an MCP configuration for the Remote MCP server (see the [MCP access models](https://www.mongodb.com/docs/mcp-server/remote-mcp/access-models)). None of these are end-user-generated.

---

## Obtain an Access Token

This section covers the two grant flows. **Flow A — Authorization Code + PKCE** is the primary flow for Atlas App Connections and produces a delegated token scoped to the logged-in user.

### Flow A — Authorization Code + PKCE (delegated user token, browser required)

#### Method 1: Python script (recommended)

```bash
python3 get_token.py
```

The script:

1. Opens the Atlas login page in your browser.
1. Listens on `localhost:3000/oauth/callback` for the redirect.
1. Exchanges the authorization code for a token.
1. Saves the token to `.token_store.json`.

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

1. **Open this URL in your browser** (production clients — no `resource` parameter):

   ```
   https://cloud.mongodb.com/oauth/authorize
     ?response_type=code
     &client_id=<your-client-id>
     &redirect_uri=http://localhost:3000/oauth/callback
     &code_challenge=<CODE_CHALLENGE>
     &code_challenge_method=S256
     &state=<random-string>
   ```

   > [!NOTE]
   > If your client was provisioned in the internal **dev** environment, use `https://cloud-dev.mongodb.com/oauth/authorize` and append `&resource=https://api-dev.mongodb.com/api/atlas` — dev-environment clients still require the `resource` indicator.

1. **Copy the `code` from the callback URL** (and verify `state` matches what you sent, and `iss` equals the authorization base):

   ```
   http://localhost:3000/oauth/callback?code=<AUTHORIZATION_CODE>&state=...&iss=https://authorize.mongodb.com
   ```

1. **Exchange the code for a token:**

   ```bash
   # Public client (no client_secret — PKCE only)
   ACCESS_TOKEN=$(curl -s -X POST "https://authorize.mongodb.com/tokens" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=authorization_code" \
     -d "code=<AUTHORIZATION_CODE>" \
     -d "code_verifier=${CODE_VERIFIER}" \
     -d "redirect_uri=http://localhost:3000/oauth/callback" \
     -d "client_id=<your-client-id>" | jq -r .access_token)

   # Confidential client — Option 1: client_secret in the body (per the official guide)
   ACCESS_TOKEN=$(curl -s -X POST "https://authorize.mongodb.com/tokens" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=authorization_code" \
     -d "code=<AUTHORIZATION_CODE>" \
     -d "code_verifier=${CODE_VERIFIER}" \
     -d "redirect_uri=http://localhost:3000/oauth/callback" \
     -d "client_id=<your-client-id>" \
     -d "client_secret=<your-client-secret>" | jq -r .access_token)

   # Confidential client — Option 2: HTTP Basic auth (client_secret_basic)
   ACCESS_TOKEN=$(curl -s -X POST "https://authorize.mongodb.com/tokens" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -H "Authorization: Basic $(echo -n '<client_id>:<client_secret>' | base64)" \
     -d "grant_type=authorization_code" \
     -d "code=<AUTHORIZATION_CODE>" \
     -d "code_verifier=${CODE_VERIFIER}" \
     -d "redirect_uri=http://localhost:3000/oauth/callback" | jq -r .access_token)
   ```

   The response includes `access_token`, `refresh_token` (confidential clients), `token_type` (`Bearer`), and `expires_in` (currently `600`). Rely on `expires_in` to schedule refreshes rather than hardcoding a lifetime.

### Flow B — Refresh Token (confidential clients only)

Only available if `refresh_token` is in your client's `grant_types`.

```bash
# Using the Python script (loads stored refresh token automatically)
python3 get_token.py --refresh-token

# Pass an explicit refresh token
python3 get_token.py --refresh-token <token>

# Using curl
curl -s -X POST "https://authorize.mongodb.com/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token" \
  -d "refresh_token=<stored-refresh-token>" \
  -d "client_id=<your-client-id>" \
  -d "client_secret=<your-client-secret>" | jq .
```

> [!IMPORTANT]
> The refresh response **always** returns a new `access_token` **and** a new `refresh_token`, and the previous refresh token is **immediately invalidated**. Always replace both stored values atomically.

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
     "import json; print(json.load(open('.token_store.json'))['access_token'])")
   ```

1. **Call an Atlas Administration API endpoint** (hosted on the cloud base):

   ```bash
   API_BASE=https://cloud.mongodb.com

   curl -s "${API_BASE}/api/atlas/v2/orgs" \
     -H "Authorization: Bearer ${ACCESS_TOKEN}" \
     -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
   ```

### Result

A successful response lists the Atlas Organizations the authenticated user belongs to **that allow third-party app connections** (App Connections enabled by the Organization Owner). An empty list is a setup step, not a failure — prompt the user to ask their Organization Owner to enable app connections (Organization Settings → App Connections).

### Token expiry

Access tokens are **short-lived** (currently 600 seconds / 10 minutes — rely on `expires_in`, not a hardcoded value). Refresh tokens expire after **7 days of inactivity** (idle lifetime) or **30 days** from the initial grant regardless of activity (maximum lifetime); Organization Owners can set a stricter maximum lifetime for their org (Organization Settings → App Connections). When an access token expires:

- Atlas returns `401 Unauthorized`.
- Use the refresh token flow if your client supports it.
- When the refresh token expires, the user must re-authorize — design for a graceful "reconnect" prompt (see the [Recovery Guide](RECOVERY.md)).

For rotation, concurrency, and revocation handling in a real deployment, see [Token lifecycle in production](PRODUCTION.md#token-lifecycle-in-production).

### Revoking tokens

When a user disconnects in your product, revoke tokens rather than letting them expire — `POST https://authorize.mongodb.com/tokens/revoke` with `token=<refresh_or_access_token>` (optionally `token_type_hint`). Revoking a refresh token invalidates every access token issued from it. The endpoint returns `200 OK` whether or not the token was valid. Full details: [Revocation cleanup](PRODUCTION.md#revocation-cleanup).

### Example: inspect a token (debug)

Decode the JWT payload without a library (base64 only, no verification):

```bash
python3 -c "
import json, base64
token = open('.token_store.json').read()
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
API_BASE=https://cloud.mongodb.com   # internal dev clients: https://api-dev.mongodb.com
ORG_ID=<your-org-id>
PROJECT_ID=<your-project-id>
CLUSTER_NAME=<your-cluster-name>

ACCESS_TOKEN=$(python3 -c \
  "import json; print(json.load(open('.token_store.json'))['access_token'])")
```

### List Organizations

Returns only the Atlas Organizations the authenticated user belongs to **that allow third-party app connections**. Atlas filters cross-organization list endpoints to opted-in organizations.

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

### Create a Database User

Creates a SCRAM user your application authenticates with for data-plane access. The connection string identifies the cluster — this user is what authenticates the connection.

```bash
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")

curl -s -X POST "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/databaseUsers" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d '{
    "databaseName": "admin",
    "username": "app_user",
    "password": "'"${DB_PASSWORD}"'",
    "roles": [{ "roleName": "readWrite", "databaseName": "app_data" }]
  }' | jq .
```

> [!WARNING]
> Generate the password server-side, store it in a secrets manager, and scope roles to the specific database. Requires the authenticated user to hold a project role that permits database-user management — a `403` here means insufficient role or delegation scope.

### Add an IP Access List Entry

Atlas rejects connections from IPs not on the project's IP Access List. Add your application's egress IPs:

```bash
curl -s -X POST "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/accessList" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d '[{ "cidrBlock": "<your-egress-ip>/32", "comment": "partner app egress" }]' | jq .
```

> [!WARNING]
> Never use `0.0.0.0/0` outside of throwaway local testing — it opens the database to the entire internet.

Once the cluster is `IDLE`, the database user exists, and the access list allows your egress IP, read `connectionStrings.standardSrv` from the cluster response and connect with any MongoDB driver. The complete flow — including polling, propagation retries, and the first insert — is in the [End-to-End Tutorial](END-TO-END.md).

---

## Run the FastAPI Demo Server

`api.py` is a local FastAPI proxy that wraps the Atlas Admin API and reads the access token automatically from `.token_store.json`.

> [!NOTE]
> All commands below are run from the **repository root** (the directory containing `get_token.py` and `api.py`).

### Before you begin

Install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Procedure

1. **Get an access token:**

   ```bash
   python3 get_token.py
   ```

1. **Start the server:**

   ```bash
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
> In a real partner integration, your **end users** are the ones with existing Atlas accounts. They log in with their own credentials — you do not create accounts for them. The service account and App Connections enablement below is done **by you (the partner/developer)** in your own test Atlas organization during development.

### Step 1: Register an Atlas test account

**Production** (no email restrictions — this is where real integrations live):

```
https://cloud.mongodb.com/account/register
```

**Internal dev environment** (only if MongoDB provisioned your client there; requires a tagged email):

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

After registration, note your **Organization ID** from the Atlas URL:

```
https://cloud.mongodb.com/v2#/org/<ORG_ID>/...
```

### Step 2: Create a service account

A service account lets you enable third-party app connections on your test organization programmatically. This is a one-time setup per organization.

> [!IMPORTANT]
> The service account `client_id` / `client_secret` (`mdb_sa_id_...` / `mdb_sa_sk_...`) are **only used here** to enable app connections on your own test org. They are **not** used for the partner OAuth flow itself. For the actual OAuth flow that your end users go through, you use the **MongoDB-provided partner `client_id`** from [Get Your OAuth Credentials](#get-your-oauth-credentials).

To create a service account:

1. Log in to the Atlas UI for your environment.
1. In the left sidebar, click **Access Manager** → **Organization Access**.
1. Click the **Applications** tab → **Service Accounts** → **Add New Service Account**.
1. Name it (e.g. `partner-test-sa`), set the role to **Organization Owner**, and click **Add Service Account**.
1. Copy the **Client ID** (`mdb_sa_id_...`) and **Client Secret** (`mdb_sa_sk_...`).

> [!WARNING]
> The client secret is shown **only once**. Store it immediately — you cannot retrieve it again.

### Step 3: Get a service account token

Service accounts authenticate with the OAuth 2.0 Client Credentials flow against the cloud base (tokens are valid for 1 hour):

```bash
CLOUD_BASE=https://cloud.mongodb.com
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
python3 get_token.py \
  --client-id     mdb_sa_id_... \
  --client-secret mdb_sa_sk_...
```

### Step 4: Enable third-party app connections (Delegated Partner Access)

App connections must be enabled on your test organization before delegated user tokens can call the Atlas Administration API. App connections are **disabled by default** for existing organizations and for new organizations an existing Atlas user creates; they are **enabled by default** only for organizations a brand-new user creates at sign-up.

**In the Atlas UI:** an Organization Owner opens **Organization Settings → App Connections** and turns on **Allow users to connect third-party apps**.

**Or via the API** (values are `DISALLOWED` and `READ_WRITE`; the endpoint requires Organization Owner privileges):

```bash
API_BASE=https://cloud.mongodb.com
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

Once enabled, any delegated user token obtained via the partner OAuth flow (see [Obtain an Access Token](#obtain-an-access-token)) can call the Atlas Administration API for this organization. This setting is **permanent per org** — you only do it once. Disabling it later takes effect **immediately** — Atlas checks the setting on every Administration API call.

> [!NOTE]
> When your application **creates** an organization on a user's behalf, the new organization doesn't allow third-party app connections yet. Enabling them is a manual step: contact MongoDB to have the organization allowlisted.

---

## Troubleshooting

Development-time symptom/cause/fix table. For **production behavior** — what your product should do and what the user should see for each condition — see the [Recovery Guide](RECOVERY.md).

| Symptom | Cause | Fix |
|---|---|---|
| `Invalid request to preauthorize` | `client_id` or `redirect_uri` mismatch | `CLIENT_ID` in `.env` must exactly match the value MongoDB provisioned for that `redirect_uri` |
| `406 INVALID_VERSION_DATE` | Missing `Accept` header | Add `-H "Accept: application/vnd.atlas.2025-03-12+json"` to every Atlas API request |
| `401 Unauthorized` from Atlas API | Access token expired | Use the refresh token flow, or re-run `python3 get_token.py` |
| `401` from FastAPI server | Token expired or not yet obtained | Re-run `python3 get_token.py` |
| `401 invalid_client` | Client authentication failed — or the client is **disabled** | Verify `client_id` / `client_secret`; `client is disabled` is terminal — stop retrying and contact the MongoDB partner team |
| `403 Forbidden` on Atlas API | App connections not enabled on the user's org, the user lacks the required role, or the endpoint is blocked for delegated access | Complete [Step 4](#step-4-enable-third-party-app-connections-delegated-partner-access) or ask the user to enable app connections (Organization Settings → App Connections); name the required Atlas role in your error handling |
| `405 Method Not Allowed` on `/authorize` | Wrong base URL | Use `CLOUD_BASE` for `/oauth/authorize`, not `OAUTH_BASE` |
| `400 invalid_grant` | Authorization code already used or expired, or refresh token invalid | Codes are single-use and expire in 10 minutes — restart the auth flow. Reusing a code invalidates **all** tokens from that grant |
| `400 invalid_target` | `resource` parameter invalid or unexpected | Production clients: **omit** `resource` from the authorization request — only internal dev-environment clients send it |
| `400 unauthorized_client` | Client not registered for this grant type | Verify your client registration includes `authorization_code` |
| `access_denied` | User declined consent (or client disabled) | Inform the user; do not retry automatically |
| `400 grant_type not supported` | Refresh token used on a public client | Public clients do not support refresh tokens — re-run the browser flow |
| `Authentication failed (E0000004)` | Dev login with base email instead of tagged email | Use `you+mongodb.com@gmail.com` format for dev accounts |
| `OSError: [Errno 48] Address already in use` | Port 3000 in use from a previous run | Script auto-frees the port; or run `lsof -ti:3000 \| xargs kill -9` |
| `PermissionError: [Errno 13]` | Port below 1024 requires root | Use `--redirect-port 3000` or above |
| `Could not import module "api"` | uvicorn started from wrong directory | Run `uvicorn api:app` from the repository root (the directory containing `api.py`) |
| Token not received after 5 minutes | Browser did not redirect to localhost | Re-run the script — PKCE state expired |

---

## Next steps

- [End-to-End Tutorial](END-TO-END.md) — from OAuth token to the first database read/write
- [Partner Onboarding Guide](PARTNER.md) — register with MongoDB and integrate the flow into your product
- [Partner UX Guide](UX-GUIDE.md) — design the connect experience
- [Production Readiness](PRODUCTION.md) — security checklist and launch requirements
- [Recovery Guide](RECOVERY.md) — user-centered error and lifecycle handling
- [Atlas Administration API reference](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2) — full endpoint documentation
