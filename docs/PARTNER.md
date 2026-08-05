# Partner Onboarding — MongoDB Atlas Admin API - V2

This guide covers the steps a partner goes through to register with MongoDB, receive OAuth credentials, and integrate the MongoDB Atlas Admin API - V2 into their product.

> [!NOTE]
> Replace all placeholders (`<partner-name>`, `<partner-app-domain>`, etc.) with your own details.
>
> For technical details on token flows, API calls, and testing setup, refer to the [Partner Integration Guide](README.md).

---

## On this page

- [How Credentials Are Issued](#how-credentials-are-issued)
- [Supported Operations](#supported-operations)
- [Step 1: Initiate onboarding](#step-1-initiate-onboarding)
- [Step 2: Agree on OAuth app configuration](#step-2-agree-on-oauth-app-configuration)
- [Step 3: Receive and store credentials](#step-3-receive-and-store-credentials)
- [Step 4: Validate end-to-end](#step-4-validate-end-to-end)
- [Step 5: Integrate into your product](#step-5-integrate-into-your-product)
- [Step 6: Promote to staging and production](#step-6-promote-to-staging-and-production)
- [OAuth App Registration Payload](#oauth-app-registration-payload)
- [Security Checklist](#security-checklist)
- [Troubleshooting](#troubleshooting)

---

## How Credentials Are Issued

MongoDB Atlas OAuth is currently **invite-only**. You do not create your OAuth app yourself — MongoDB provisions it for you.

| Step | Who does it |
|---|---|
| Partner contacts MongoDB partner team | **You** |
| MongoDB creates the OAuth app registration | **MongoDB** |
| MongoDB shares `client_id` (and `client_secret` if applicable) | **MongoDB** |
| Partner configures `.env` and starts the flow | **You** |

> [!NOTE]
> **Future state:** Partners will be able to self-register via **Atlas UI → Organization → Integrations → OAuth Apps**. This guide will be updated when self-serve is available.

---

## Supported Operations

Once a user's delegated access token is obtained, your app can perform the following MongoDB Atlas operations on that user's behalf:

| Operation | Endpoint | Method |
|---|---|---|
| List the user's Organizations | `/api/atlas/v2/orgs` | `GET` |
| List Projects in an Organization | `/api/atlas/v2/groups?orgId={orgId}` | `GET` |
| Create a Project | `/api/atlas/v2/groups` | `POST` |
| List Clusters in a Project | `/api/atlas/v2/groups/{projectId}/clusters` | `GET` |
| Create a Cluster | `/api/atlas/v2/groups/{projectId}/clusters` | `POST` |
| Get Cluster status | `/api/atlas/v2/groups/{projectId}/clusters/{clusterName}` | `GET` |
| Delete a Cluster | `/api/atlas/v2/groups/{projectId}/clusters/{clusterName}` | `DELETE` |

> [!IMPORTANT]
> Every request requires these headers:
>
> ```
> Authorization: Bearer <access_token>
> Accept: application/vnd.atlas.2025-03-12+json
> ```
>
> For full curl examples of each operation, see [Atlas Admin API Reference](README.md#atlas-admin-api-reference) in the Partner Integration Guide.

---

## Step 1: Initiate onboarding

Contact your MongoDB partner manager or solutions engineer. Provide:

- **Company name:** `<partner-name>`
- **Product name:** `<partner-product-name>`
- **Use case:** Allow users to provision and connect an Atlas cluster from within your product
- **Target environment:** Dev (`cloud-dev.mongodb.com`) to start
- **Technical contact:** name and email of the engineer owning the integration
- **Operational contact:** email for app ownership and incident notifications

---

## Step 2: Agree on OAuth app configuration

Work with the MongoDB team to define your app settings:

| Field | Recommended value | Notes |
|---|---|---|
| `client_name` | `<partner-name>` | Shown on the Atlas consent screen |
| `client_type` | `web_app` | Use `single_page_app` if your app has no backend |
| `token_endpoint_auth_method` | `client_secret_basic` | Use `none` for public (SPA) clients |
| `redirect_uris` | `https://<partner-app-domain>/oauth/atlas/callback` | HTTPS required in production |
| `grant_types` | `["authorization_code", "refresh_token"]` | Omit `refresh_token` for public clients |
| `access_token_lifetime` | `600` | 10 minutes |
| `maximum_refresh_token_lifetime` | `2592000` | 30 days (confidential clients only) |
| `allow_saved_consent` | `true` | User not re-prompted after first consent |
| `resources` | `["https://api.mongodb.com/api/atlas"]` | Use `api-dev` for dev |

---

## Step 3: Receive and store credentials

MongoDB will share:

- **`client_id`** — always provided; a UUID identifying your OAuth app
- **`client_secret`** — confidential clients only (omitted for public/SPA clients)

> [!WARNING]
> Store `client_secret` in a secrets manager — never in source control or browser-accessible config.

### Example

```ini
# .env
CLIENT_ID=<client-id-provided-by-mongodb>
CLIENT_SECRET=<client-secret-provided-by-mongodb>   # leave blank for public clients
OAUTH_BASE=https://authorize-dev.mongodb.com
CLOUD_BASE=https://cloud-dev.mongodb.com
RESOURCE=https://api-dev.mongodb.com/api/atlas
REDIRECT_URI=https://<partner-app-domain>/oauth/atlas/callback
```

---

## Step 4: Validate end-to-end

Follow [Obtain an Access Token](README.md#obtain-an-access-token) and [Use the Access Token](README.md#use-the-access-token) in the Partner Integration Guide to confirm your credentials work before writing product code.

For setting up your own test Atlas account and enabling Delegated Partner Access on it, see [Set Up a Test Atlas Environment](README.md#set-up-a-test-atlas-environment) in the Partner Integration Guide.

---

## Step 5: Integrate into your product

### Authorization redirect

When a user clicks "Connect MongoDB Atlas" in your product:

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

1. **Validates `state`** (CSRF protection).

1. **Exchanges the code for tokens** (back-channel POST):

   ```
   POST https://authorize.mongodb.com/tokens
   Content-Type: application/x-www-form-urlencoded
   Authorization: Basic base64(<client_id>:<client_secret>)   # confidential clients only

   grant_type=authorization_code
   &code=<authorization-code>
   &code_verifier=<pkce-verifier>
   &redirect_uri=https://<partner-app-domain>/oauth/atlas/callback
   ```

1. **Stores `refresh_token` server-side only** — never in the browser or logs.

### Provisioning flow

Recommended Atlas API call sequence when onboarding a new user:

```
1. GET  /api/atlas/v2/orgs
        → user selects their organization

2. POST /api/atlas/v2/groups
        { "name": "<project-name>", "orgId": "<selected-org-id>" }
        → create a dedicated Atlas project

3. POST /api/atlas/v2/groups/{projectId}/clusters
        → provision an M0 free-tier cluster

4. GET  /api/atlas/v2/groups/{projectId}/clusters/{clusterName}
        → poll until stateName == "IDLE"

5. From the same cluster response, read connectionStrings.standardSrv
        → connection string for direct database access (data plane)
```

See [Atlas Admin API Reference](README.md#atlas-admin-api-reference) in the Partner Integration Guide for full curl examples.

### Retrieve a connection string (data plane)

The MongoDB Atlas Admin API - V2 covered in this guide is **control-plane only**, but the connection string your app needs for **direct database access** (CRUD operations, creating collections, building indexes) is already included in the cluster response — no separate API call is required.

Once the cluster reports `stateName == "IDLE"`, read the `connectionStrings` field:

```bash
curl -s "https://api.mongodb.com/api/atlas/v2/groups/<project-id>/clusters/<cluster-name>" \
  -H "Authorization: Bearer <access-token>" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .connectionStrings
```

### Example

```json
{
  "standard":    "mongodb://mycluster-shard-00-00.abcde.mongodb.net:27017,...",
  "standardSrv": "mongodb+srv://mycluster.abcde.mongodb.net"
}
```

Use `standardSrv` (`mongodb+srv://`) for modern drivers. Store it in your secrets manager alongside the refresh token — never in the browser or logs.

> [!WARNING]
> **The connection string alone does not authenticate.** To actually connect, the project also needs:
>
> - **A database user** — via `POST /api/atlas/v2/groups/{projectId}/databaseUsers`
> - **An IP Access List entry** covering your app's egress IPs — via `POST /api/atlas/v2/groups/{projectId}/accessList`
>
> These Atlas Admin API endpoints exist today but are **not yet covered by this quickstart** — confirm they work with your delegated token, and the current recommended approach for data-plane access, with your MongoDB partner contact before building on them.

---

## Step 6: Promote to staging and production

To promote your integration to staging and production:

1. Ask your MongoDB partner contact to register the OAuth app in staging, then production.
1. Use separate `CLIENT_ID` / `CLIENT_SECRET` per environment — stored in the appropriate secrets manager.
1. Update `redirect_uris` to production HTTPS URLs.
1. Confirm `published: true` so the app appears in the Atlas governance UX.

---

## OAuth App Registration Payload

Submit this to MongoDB when initiating onboarding ([Step 1](#step-1-initiate-onboarding)):

### Example

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

## Security Checklist

- [ ] `client_secret` stored in a secrets manager — not in source control or browser config
- [ ] `redirect_uri` is HTTPS in staging and production
- [ ] `state` parameter validated on every callback (CSRF protection)
- [ ] PKCE `code_challenge` used on every authorization request
- [ ] `refresh_token` stored server-side only — never logged or sent to the browser
- [ ] Token refresh errors surface graceful re-authentication — no raw error details exposed
- [ ] Access tokens not written to application or infrastructure logs
- [ ] `.env` is in `.gitignore` and has never been committed

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Invalid request to preauthorize` | `client_id` / `redirect_uri` mismatch | Confirm values exactly match what MongoDB provisioned |
| `401` from Atlas API | Access token expired | Refresh token or re-run browser login flow |
| `403 Forbidden` | Delegated Partner Access not enabled on user's org | User must enable it — see [Set Up a Test Atlas Environment](README.md#set-up-a-test-atlas-environment) in the Partner Integration Guide |
| `400 invalid_grant` | Code already used or expired | Restart the auth flow |
| `400 grant_type not supported` | Refresh token used on a public client | Public clients do not support refresh tokens |
| `406 INVALID_VERSION_DATE` | Missing `Accept` header | Add `Accept: application/vnd.atlas.2025-03-12+json` to every request |
| `Authentication failed (E0000004)` | Dev login with base email | Use `you+mongodb.com@domain.com` format for dev accounts |

---

## Next steps

- [Partner Integration Guide](README.md) — token flows, curl examples, and testing setup
- [Atlas Administration API reference](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2) — full endpoint documentation
