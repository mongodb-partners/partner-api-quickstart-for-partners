# Partner — Atlas Partner API Onboarding

This guide covers the end-to-end steps for a partner to onboard as an OAuth partner on the MongoDB Atlas platform, obtain OAuth credentials, and integrate the Atlas Partner API into their product.

> Replace the placeholders below (`<partner-name>`, `<partner-app-domain>`, etc.) with your own company and product details.

## Overview

By integrating with the Atlas Partner API, a partner application can allow users to provision and connect an Atlas database cluster directly from within the partner's product UI — without users leaving the product, and without the partner ever handling Atlas credentials.

### What the partner gets access to

| Operation | API Endpoint | Method |
|---|---|---|
| List Organizations | `/api/atlas/v2/orgs` | `GET` |
| List Projects in an Org | `/api/atlas/v2/groups?orgId={orgId}` | `GET` |
| Create a Project | `/api/atlas/v2/groups` | `POST` |
| List Clusters | `/api/atlas/v2/groups/{projectId}/clusters` | `GET` |
| Create a Cluster | `/api/atlas/v2/groups/{projectId}/clusters` | `POST` |
| Get Cluster Status | `/api/atlas/v2/groups/{projectId}/clusters/{name}` | `GET` |
| Delete a Cluster | `/api/atlas/v2/groups/{projectId}/clusters/{name}` | `DELETE` |

> **Note:** The user's Atlas Organization must have Delegated Partner Access enabled (see `PARTNER_API_GUIDE.md`) before delegated tokens can call these endpoints.

---

## Step 1 — Initiate Partner Onboarding with MongoDB

Contact your MongoDB partner manager or solutions engineer to begin onboarding. Provide:

- **Company name:** `<partner-name>`
- **Product name:** `<partner-product-name>`
- **Use case:** Allow users to provision and connect an Atlas cluster from within your product UI
- **Target environment to start:** Dev (`cloud-dev.mongodb.com`)
- **Technical contact:** name and email of the engineer owning the integration
- **Operational contact email:** for OAuth app ownership and incident notifications

---

## Step 2 — Agree on OAuth App Configuration

Work with the MongoDB team to agree on the following settings for your OAuth app:

| Field | Recommended value | Notes |
|---|---|---|
| `client_name` | `<partner-name>` | Shown on the Atlas consent screen |
| `client_type` | `web_app` | Use a confidential client if your app has a backend |
| `token_endpoint_auth_method` | `client_secret_basic` | Backend-to-backend token exchange |
| `redirect_uris` | `https://<partner-app-domain>/oauth/atlas/callback` | HTTPS required in production |
| `grant_types` | `["authorization_code", "refresh_token"]` | Include refresh tokens for persistent sessions |
| `access_token_lifetime` | `600` | 10 minutes |
| `maximum_refresh_token_lifetime` | `2592000` | 30 days |
| `allow_saved_consent` | `true` | No re-prompt after first consent |
| `resources` | `["https://api.mongodb.com/api/atlas"]` | Production; use `api-dev` for dev |

> **Why `web_app` and not `single_page_app`?**
> If your backend server handles the token exchange, this is a confidential client. Public (SPA) clients cannot hold a `client_secret` and do not support refresh tokens. If you need persistent sessions without repeated browser logins, `web_app` is the correct choice.

---

## Step 3 — Receive and Store Credentials

Once provisioned, MongoDB will share:

- **`client_id`** — a UUID identifying your OAuth app
- **`client_secret`** — for backend-to-backend token exchange (confidential clients only)

> **Security requirement:** Store `client_secret` in a secrets manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault). Never commit it to source control, log it, or expose it to the browser.

```ini title=".env (local dev) or secrets manager (staging/production)"
CLIENT_ID=<client-id-provided-by-mongodb>
CLIENT_SECRET=<client-secret-provided-by-mongodb>
OAUTH_BASE=https://authorize-dev.mongodb.com
CLOUD_BASE=https://cloud-dev.mongodb.com
RESOURCE=https://api-dev.mongodb.com/api/atlas
REDIRECT_URI=https://<partner-app-domain>/oauth/atlas/callback
```

---

## Step 4 — Register Atlas Test Accounts

### Dev environment

Register at `https://cloud-dev.mongodb.com/account/register` using a **tagged email**:

| Your email | Register with |
|---|---|
| `you@<partner-app-domain>` | `you+mongodb.com@<partner-app-domain>` |

After registration, note your **Organization ID** from the Atlas URL:
```
https://cloud-dev.mongodb.com/v2#/org/<ORG_ID>/...
```

### Staging / Production

No email restrictions. Register at `https://cloud-stage.mongodb.com/account/register` or `https://cloud.mongodb.com/account/register`.

---

## Step 5 — Enable Delegated Partner Access

For your own test organization during development, follow the "Enable Delegated Partner Access" section in `PARTNER_API_GUIDE.md`.

In your product, guide users through enabling it in their own Atlas org, or surface a link to Atlas settings.

---

## Step 6 — Validate the OAuth Flow End-to-End

```bash
# Configure .env with the credentials from Step 3
python3 oauthdemo/get_token.py
```

Then verify with an API call:

```bash
ACCESS_TOKEN=$(python3 -c \
  "import json; print(json.load(open('oauthdemo/.token_store.json'))['access_token'])")

curl -s "https://api-dev.mongodb.com/api/atlas/v2/orgs" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

Also verify token refresh (if you registered a confidential client with refresh tokens):

```bash
python3 oauthdemo/get_token.py --refresh-token
```

---

## Step 7 — Integrate into Your Product

### Authorization redirect

When a user clicks "Connect MongoDB Atlas" in your product UI:

```
https://cloud.mongodb.com/oauth/authorize
  ?response_type=code
  &client_id=<your-client-id>
  &redirect_uri=https://<partner-app-domain>/oauth/atlas/callback
  &code_challenge=<S256-pkce-challenge>
  &code_challenge_method=S256
  &state=<random-csrf-token>
  &resource=https://api.mongodb.com/api/atlas
```

### Callback handler

At `https://<partner-app-domain>/oauth/atlas/callback`, your backend:

1. Validates the `state` parameter (CSRF protection)
2. Exchanges the code for tokens:

```
POST https://authorize.mongodb.com/tokens
Content-Type: application/x-www-form-urlencoded
Authorization: Basic base64(<client_id>:<client_secret>)

grant_type=authorization_code
&code=<authorization-code>
&code_verifier=<pkce-verifier>
&redirect_uri=https://<partner-app-domain>/oauth/atlas/callback
```

3. Stores `refresh_token` server-side only — never in the browser

### Token refresh

When the `access_token` expires (10 minutes):

```
POST https://authorize.mongodb.com/tokens
Content-Type: application/x-www-form-urlencoded
Authorization: Basic base64(<client_id>:<client_secret>)

grant_type=refresh_token
&refresh_token=<stored-refresh-token>
```

Always store the new `refresh_token` returned in the response (MongoDB may rotate it).

### Atlas provisioning flow

Recommended sequence for provisioning an Atlas database for a new partner-managed project:

```
1. GET  /api/atlas/v2/orgs
        → show user their organizations; they select one

2. POST /api/atlas/v2/groups
        { "name": "<project-name>", "orgId": "<selected-org-id>" }
        → creates a dedicated Atlas project

3. POST /api/atlas/v2/groups/{projectId}/clusters
        → provisions an M0 free-tier cluster

4. GET  /api/atlas/v2/groups/{projectId}/clusters/{clusterName}
        → poll until stateName == "IDLE"
```

---

## Step 8 — Promote to Staging and Production

1. Work with your MongoDB partner contact to register the OAuth app in staging, then production.
2. Use separate `CLIENT_ID` / `CLIENT_SECRET` values per environment — store each in the appropriate secrets manager.
3. Update `redirect_uris` to production URLs (`https://<partner-app-domain>/oauth/atlas/callback`).
4. Confirm `published: true` so your app appears in the Atlas governance UX.

---

## OAuth App Configuration Reference

Full registration payload to submit to MongoDB:

```json
{
  "client_name": "<partner-name>",
  "client_type": "web_app",
  "token_endpoint_auth_method": "client_secret_basic",
  "redirect_uris": [
    "https://<partner-app-domain>/oauth/atlas/callback"
  ],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "resources": ["https://api.mongodb.com/api/atlas"],
  "access_token_lifetime": 600,
  "maximum_refresh_token_lifetime": 2592000,
  "allow_saved_consent": true,
  "published": true,
  "client_uri": "https://<partner-app-domain>",
  "tos_uri": "https://<partner-app-domain>/terms",
  "policy_uri": "https://<partner-app-domain>/privacy",
  "logo_uri": "https://<partner-app-domain>/logo.png",
  "owner": {
    "name": "<partner-name>",
    "operational_contacts": {
      "emails": ["<ops-contact@partner-app-domain>"]
    }
  }
}
```

---

## Token Lifecycle

| Token | Lifetime | Notes |
|---|---|---|
| Access token | 600 s (10 min) | Use for Atlas API calls |
| Refresh token | 30 days | Stored server-side only; always save the latest rotated value |

If the refresh token expires (30 days inactivity) or is revoked, the user must re-authenticate via the browser flow.

---

## Security Checklist

- [ ] `client_secret` is in a secrets manager — not in source control or browser-accessible config
- [ ] `redirect_uri` is HTTPS in staging and production
- [ ] `state` parameter is validated on every callback (CSRF protection)
- [ ] PKCE `code_challenge` is used on every authorization request
- [ ] `refresh_token` is stored server-side only — never logged or sent to the browser
- [ ] Token refresh errors prompt graceful re-authentication without exposing error details
- [ ] Access tokens are not written to application or infrastructure logs
- [ ] `.env` file is in `.gitignore` and has never been committed

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Invalid request to preauthorize` | `client_id` or `redirect_uri` mismatch | Confirm values exactly match what MongoDB provisioned |
| `401` from Atlas API | Access token expired | Use refresh token; if that fails, re-run browser login |
| `403 Forbidden` | Delegated Partner Access not enabled | Guide user to enable it in their org — see `PARTNER_API_GUIDE.md` |
| `400 invalid_grant` | Code already used or expired | Restart the auth flow |
| `400 grant_type not supported` | `refresh_token` not in `grant_types` | Confirm registration includes `"grant_types": ["authorization_code", "refresh_token"]` |
| `406 INVALID_VERSION_DATE` | Missing `Accept` header | Add `Accept: application/vnd.atlas.2025-03-12+json` to every Atlas API request |
| `Authentication failed (E0000004)` | Dev login with base email | Use `you+mongodb.com@<partner-app-domain>` format for dev accounts |
