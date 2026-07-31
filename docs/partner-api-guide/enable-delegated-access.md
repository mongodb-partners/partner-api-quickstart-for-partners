---
id: enable-delegated-access
sidebar_position: 2
title: Enable Delegated Partner Access
description: How to enable Delegated Partner Access on an Atlas Organization using a service account token.
---

# Enable Delegated Partner Access

By default, an Atlas Organization blocks partner apps from accessing it. You must explicitly enable **Delegated Partner Access** before any partner token can call the Atlas Admin API for that Organization.

You only need to do this **once per Organization**. This step requires a **service account token**.

## Step 1 — Create a Service Account

1. Log in to the Atlas UI for your environment.
2. In the left sidebar click **Access Manager** → **Organization Access**.
3. Click the **Applications** tab → **Service Accounts** → **Add New Service Account**.
4. Name it (e.g. `partner-demo-sa`), set role to **Organization Owner**, click **Add Service Account**.
5. Copy the **Client ID** (`mdb_sa_id_...`) and **Client Secret** (`mdb_sa_sk_...`).

:::caution
The client secret is shown **only once**. Copy it immediately and store it securely.
:::

## Step 2 — Get a Service Account Token

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

## Step 3 — Check current setting

```bash
API_BASE=https://api-dev.mongodb.com
ORG_ID=<your-org-id>

curl -s "${API_BASE}/api/atlas/v2/orgs/${ORG_ID}/delegationSettings" \
  -H "Authorization: Bearer ${SA_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

Default response (access blocked):

```json
{
  "delegatedPartnerAccess": "DISALLOWED"
}
```

## Step 4 — Enable READ_WRITE access

```bash
curl -s -X PATCH \
  "${API_BASE}/api/atlas/v2/orgs/${ORG_ID}/delegationSettings" \
  -H "Authorization: Bearer ${SA_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d '{"delegatedPartnerAccess": "READ_WRITE"}' | jq .
```

Expected response:

```json
{
  "delegatedPartnerAccess": "READ_WRITE"
}
```

Once set, any delegated user token obtained via the partner OAuth client can call the Atlas Admin API for this Organization.
