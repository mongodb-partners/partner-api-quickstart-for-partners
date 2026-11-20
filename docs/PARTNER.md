# Partner Onboarding — Atlas App Connections (Partner API)

This guide covers the steps a partner goes through to register with MongoDB, receive OAuth credentials, and integrate Atlas App Connections (user-delegated access to the Atlas Administration API) into their product.

> [!NOTE]
> Replace all placeholders (`<partner-name>`, `<partner-app-domain>`, etc.) with your own details.
>
> For technical details on token flows, API calls, and testing setup, refer to the [Partner Integration Guide](README.md). MongoDB's official version of this flow is [Integrate Your App with Atlas App Connections](https://www.mongodb.com/docs/atlas/app-connections/partner-integration-guide/).

---

## On this page

- [How Credentials Are Issued](#how-credentials-are-issued)
- [What Your App Can Do](#what-your-app-can-do)
- [Step 1: Initiate onboarding](#step-1-initiate-onboarding)
- [Step 2: Agree on OAuth app configuration](#step-2-agree-on-oauth-app-configuration)
- [Step 3: Receive and store credentials](#step-3-receive-and-store-credentials)
- [Step 4: Validate end-to-end](#step-4-validate-end-to-end)
- [Step 5: Integrate into your product](#step-5-integrate-into-your-product)
- [Step 6: Promote to staging and production](#step-6-promote-to-staging-and-production)
- [OAuth App Registration Payload](#oauth-app-registration-payload)
- [Security Checklist](#security-checklist)

---

## How Credentials Are Issued

Atlas App Connections is currently available to **approved design partners**. To become one, submit the [Become a Partner](https://www.mongodb.com/company/partners/) form and include **"Partner API"** in the More Information field. You do not create your OAuth app yourself — MongoDB provisions it for you.

| Step | Who does it |
|---|---|
| Partner applies via the Become a Partner form ("Partner API") | **You** |
| MongoDB creates the OAuth app registration | **MongoDB** |
| MongoDB shares `client_id` (and `client_secret` if applicable) | **MongoDB** |
| Partner configures `.env` and starts the flow | **You** |

> [!NOTE]
> **Future state:** Partners are planned to self-register and manage OAuth applications via Atlas (client ID/secret creation, redirect URIs, metadata, secret regeneration). See [Partner Delegation](partner-delegations.md). This guide will be updated when self-serve is available.

---

## What Your App Can Do

Once a user's delegated access token is obtained, your app can list orgs, manage projects and clusters, create database users, and manage IP access lists on that user's behalf. The full operations table and curl examples are in the [Partner Integration Guide](README.md#overview).

> [!IMPORTANT]
> Every request requires these headers:
>
> ```
> Authorization: Bearer <access_token>
> Accept: application/vnd.atlas.2025-03-12+json
> ```

---

## Step 1: Initiate onboarding

Submit the [Become a Partner](https://www.mongodb.com/company/partners/) form with **"Partner API"** in the More Information field, or contact your MongoDB partner manager or solutions engineer. Provide:

- **Company name:** `<partner-name>`
- **Product name:** `<partner-product-name>`
- **Use case:** Allow users to provision and connect an Atlas cluster from within your product
- **Target environment:** Production (`cloud.mongodb.com`) — Atlas does not provide separate partner environments
- **Technical contact:** name and email of the engineer owning the integration
- **Operational contact:** email for app ownership and incident notifications

---

## Step 2: Agree on OAuth app configuration

Work with the MongoDB team to define your app settings:

| Field | Recommended value | Notes |
|---|---|---|
| `client_name` | `<partner-name>` | Shown on the Atlas consent screen |
| `client_type` | `web_app` | Use `single_page_app` if your app has no backend |
| `token_endpoint_auth_method` | `client_secret_basic` | Use `none` for public (SPA) clients — prefer secret-less PKCE where possible |
| `redirect_uris` | `https://<partner-app-domain>/oauth/atlas/callback` | HTTPS required except loopback (`localhost`, `127.0.0.1`, `::1` may use HTTP); no fragments (`#`) |
| `grant_types` | `["authorization_code", "refresh_token"]` | Omit `refresh_token` for public clients |
| `access_token_lifetime` | `600` | 10 minutes |
| `maximum_refresh_token_lifetime` | `2592000` | 30 days (confidential clients only) |
| `allow_saved_consent` | `true` | User not re-prompted after first consent |
| `resources` | `["https://cloud.mongodb.com/api/atlas"]` | Registration-time setting; production authorization requests do not send `resource` |

---

## Step 3: Receive and store credentials

MongoDB will share:

- **`client_id`** — always provided; identifies your OAuth app
- **`client_secret`** — confidential clients only (omitted for public/SPA clients, which authenticate with only the `client_id` + PKCE)

> [!WARNING]
> Store `client_secret` in a secrets manager — never in source control or browser-accessible config. To rotate a suspected-compromised secret, contact MongoDB.

These credentials are issued by MongoDB for your **partner OAuth app**. They are distinct from **service account** credentials (which you or your customers create in Atlas for client-credentials access) and from **MCP configuration** credentials (which Atlas generates for the Remote MCP server) — see [Get Your OAuth Credentials](README.md#get-your-oauth-credentials).

Configure them in your `.env` alongside the environment endpoints — see [Environments](README.md#environments) in the Partner Integration Guide.

---

## Step 4: Validate end-to-end

Follow [Obtain an Access Token](README.md#obtain-an-access-token) and [Use the Access Token](README.md#use-the-access-token) in the Partner Integration Guide to confirm your credentials work before writing product code.

For setting up your own test Atlas account and enabling third-party app connections on it, see [Set Up a Test Atlas Environment](README.md#set-up-a-test-atlas-environment) in the Partner Integration Guide.

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
```

> [!IMPORTANT]
> Send **only** these parameters. The production authorization endpoint does not require a `resource` parameter — omit it, even though the OAuth 2.1 specification defines one.

### Callback handler

At `https://<partner-app-domain>/oauth/atlas/callback`, your backend:

1. **Validates `state`** (CSRF protection) and **`iss`** (must equal `https://authorize.mongodb.com` — prevents authorization-server mix-up attacks). Checks for an `error` parameter (e.g. `access_denied` when the user declines) before using the `code`.

1. **Exchanges the code for tokens** (back-channel POST) — codes are single-use and expire within 10 minutes:

   ```
   POST https://authorize.mongodb.com/tokens
   Content-Type: application/x-www-form-urlencoded

   grant_type=authorization_code
   &code=<authorization-code>
   &code_verifier=<pkce-verifier>
   &redirect_uri=https://<partner-app-domain>/oauth/atlas/callback
   &client_id=<your-client-id>
   &client_secret=<your-client-secret>   # confidential clients only
   ```

   Confidential clients may instead authenticate with HTTP Basic (`Authorization: Basic base64(client_id:client_secret)`) and omit `client_id`/`client_secret` from the body.

1. **Stores `refresh_token` server-side only** — never in the browser or logs. Every refresh returns a **new** refresh token and immediately invalidates the previous one — always persist both new values atomically.

### Provisioning flow

Recommended Atlas API call sequence when onboarding a new user:

```
1. GET  /api/atlas/v2/orgs
        → user selects their organization
        (only orgs that allow third-party app connections are usable targets;
         an empty list means no org has enabled them — a setup step, not a failure)

2. POST /api/atlas/v2/groups
        { "name": "<project-name>", "orgId": "<selected-org-id>" }
        → create a dedicated Atlas project (or select an existing one)
        → Atlas validates the orgId and returns 403 if that org has not opted in

3. POST /api/atlas/v2/groups/{projectId}/clusters
        → provision an M0 free-tier cluster (or select an existing one)

4. GET  /api/atlas/v2/groups/{projectId}/clusters/{clusterName}
        → poll until stateName == "IDLE" — the 201 response is NOT readiness

5. POST /api/atlas/v2/groups/{projectId}/databaseUsers
        → create a SCRAM database user for data-plane access

6. POST /api/atlas/v2/groups/{projectId}/accessList
        → allow your application's egress IPs

7. From the cluster response, read connectionStrings.standardSrv
        → connection string for direct database access (data plane)

8. Connect with a MongoDB driver and perform the first read/write
        → show the user "Connected to MongoDB Atlas"
```

The full walkthrough — with curl examples, a runnable script (`end_to_end.py`), and the first database operation — is in the [End-to-End Tutorial](END-TO-END.md). For the screens behind each step, see the [Partner UX Guide](UX-GUIDE.md).

### Retrieve a connection string (data plane)

The Atlas Administration API covered in this guide is **control-plane only**, but the connection string your app needs for **direct database access** (CRUD operations, creating collections, building indexes) is already included in the cluster response — no separate API call is required. Once the cluster reports `stateName == "IDLE"`, read `connectionStrings.standardSrv` (`mongodb+srv://…`) and store it in your secrets manager alongside the refresh token — never in the browser or logs.

> [!WARNING]
> **The connection string alone does not authenticate.** To actually connect, the project also needs:
>
> - **A database user** — via `POST /api/atlas/v2/groups/{projectId}/databaseUsers`
> - **An IP Access List entry** covering your app's egress IPs — via `POST /api/atlas/v2/groups/{projectId}/accessList`
>
> Both calls work with a delegated token when the authenticated user holds a project role that permits user and network management (e.g. `Project Owner`). Full examples: [End-to-End Tutorial](END-TO-END.md) (steps 5–8) and the [Atlas Admin API Reference](README.md#create-a-database-user). Confirm the recommended data-plane approach for your use case with your MongoDB partner contact.

---

## Step 6: Promote to staging and production

Atlas does not provide separate partner environments — you develop and launch against **production**. If MongoDB provisioned your OAuth client in an internal dev or staging environment for early testing, promote by asking your MongoDB partner contact to register the OAuth app in production:

1. Ask your MongoDB partner contact to register the OAuth app in production.
1. Use separate `CLIENT_ID` / `CLIENT_SECRET` per environment — stored in the appropriate secrets manager.
1. Update `redirect_uris` to production HTTPS URLs.
1. Confirm `published: true` so the app appears in the Atlas governance UX (Organization Settings → App Connections).

> [!NOTE]
> Integration responsibilities split three ways — MongoDB, you (the partner), and the end user. The full ownership matrix is in the [Production Readiness Guide](PRODUCTION.md#responsibility-matrix).

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
  "resources": ["https://cloud.mongodb.com/api/atlas"],
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

- [ ] `client_secret` stored in a secrets manager — not in source control or browser config (prefer secret-less PKCE where your client type allows)
- [ ] `redirect_uri` is HTTPS in production (HTTP allowed only for loopback addresses)
- [ ] `state` parameter validated on every callback (CSRF protection)
- [ ] `iss` parameter validated on every callback (authorization-server mix-up protection)
- [ ] PKCE `code_challenge` (S256) used on every authorization request — `plain` is rejected
- [ ] `refresh_token` stored server-side only — never logged or sent to the browser
- [ ] Every refresh persists the **new** refresh token (old one is invalidated immediately)
- [ ] Token refresh errors surface graceful re-authentication — no raw error details exposed
- [ ] Access tokens not written to application or infrastructure logs
- [ ] `.env` is in `.gitignore` and has never been committed
- [ ] Tokens revoked via `POST /tokens/revoke` when a user disconnects

---

Run into an error during onboarding? See the [Troubleshooting table](README.md#troubleshooting) in the Partner Integration Guide.

---

## Next steps

- [Partner Integration Guide](README.md) — token flows, curl examples, and testing setup
- [End-to-End Tutorial](END-TO-END.md) — provision through to the first database read/write
- [Partner UX Guide](UX-GUIDE.md) — design the connect experience
- [Production Readiness](PRODUCTION.md) — launch checklist and token lifecycle
- [Recovery Guide](RECOVERY.md) — user-centered error handling
- [Atlas Administration API reference](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2) — full endpoint documentation
