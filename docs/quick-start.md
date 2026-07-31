---
id: quick-start
sidebar_position: 3
title: Quick Start
description: Get an Atlas OAuth access token and call the Partner API in minutes.
---

# Quick Start

Get an access token and make your first Atlas API call in under 5 minutes.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.8+ | For `get_token.py` and the FastAPI server |
| `curl` + `jq` | For direct API calls — `brew install jq` |
| A registered OAuth `client_id` | See [Getting Your Credentials](/getting-credentials) |
| An Atlas account | See [Register a Test Account](#register-a-test-account) |

## Register a test account

### Dev environment

Register at `https://cloud-dev.mongodb.com/account/register` using a **tagged email**:

| Your email | Register with |
|---|---|
| `you@gmail.com` | `you+mongodb.com@gmail.com` |
| `eng@company.com` | `eng+mongodb.com@company.com` |

:::note
Always sign in with the exact tagged address used at registration.
:::

### Staging / Production

No email format restrictions. Register at:
- Staging: `https://cloud-stage.mongodb.com/account/register`
- Production: `https://cloud.mongodb.com/account/register`

After registration, note your **Organization ID** from the Atlas URL:
```
https://cloud-dev.mongodb.com/v2#/org/<ORG_ID>/...
```

## Configure your environment

```ini title="oauthdemo/.env"
CLIENT_ID=<client-id-provided-by-mongodb>
CLIENT_SECRET=          # confidential clients only — leave blank for SPA
OAUTH_BASE=https://authorize-dev.mongodb.com
CLOUD_BASE=https://cloud-dev.mongodb.com
RESOURCE=https://api-dev.mongodb.com/api/atlas
REDIRECT_URI=http://localhost:3000/oauth/callback
```

## Get an access token

### Option A — Authorization Code + PKCE (browser flow)

```bash
python3 oauthdemo/get_token.py
```

This opens Atlas login in your browser. After you sign in and consent, the token is saved to `oauthdemo/.token_store.json`.

#### Optional CLI flags

```bash
python3 oauthdemo/get_token.py \
  --client-id     <your-client-id> \
  --oauth-base    https://authorize-dev.mongodb.com \
  --cloud-base    https://cloud-dev.mongodb.com \
  --resource      https://api-dev.mongodb.com/api/atlas \
  --redirect-port 3000
```

### Option B — Client Credentials (service account, no browser)

```bash
CLOUD_BASE=https://cloud-dev.mongodb.com
SA_CLIENT_ID=mdb_sa_id_...
SA_CLIENT_SECRET=mdb_sa_sk_...

ACCESS_TOKEN=$(curl -s -X POST "${CLOUD_BASE}/api/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic $(echo -n "${SA_CLIENT_ID}:${SA_CLIENT_SECRET}" | base64)" \
  -d "grant_type=client_credentials" | jq -r .access_token)
```

### Option C — Refresh Token (confidential clients only)

```bash
# Use stored refresh token automatically
python3 oauthdemo/get_token.py --refresh-token

# Or pass an explicit token
python3 oauthdemo/get_token.py --refresh-token <token>
```

## Read the token

```bash
ACCESS_TOKEN=$(python3 -c \
  "import json; print(json.load(open('oauthdemo/.token_store.json'))['access_token'])")
```

## Make your first API call

```bash
API_BASE=https://api-dev.mongodb.com

curl -s "${API_BASE}/api/atlas/v2/orgs" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

A successful response lists the Atlas Organizations the user belongs to.

## Token lifetime

| Client type | Access token lifetime | Refresh token |
|---|---|---|
| SPA (public client) | 600 s (10 min) | Not issued |
| Service account | 600 s (default) | Not issued |
| Confidential web app | Configurable | Issued if configured |

When the token expires, re-run `python3 oauthdemo/get_token.py`.

## Next step

[Enable Delegated Partner Access](/partner-api-guide/enable-delegated-access) on your Atlas Organization so delegated tokens can call the Admin API.
