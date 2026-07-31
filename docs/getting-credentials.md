---
id: getting-credentials
sidebar_position: 2
title: Getting Your OAuth Credentials
description: How to obtain a client_id and client_secret from MongoDB as a partner.
---

# Getting Your OAuth Credentials

Before running any OAuth flow, you need a `client_id` (and optionally a `client_secret`) registered with the MongoDB Atlas OAuth provider. These are **not** GitHub credentials or self-generated values — they must be issued by MongoDB.

## Current model — manual partner onboarding (early access)

MongoDB Atlas OAuth is currently **invite-only**. Client credentials are provisioned manually by the MongoDB team, not through a self-serve portal.

### How onboarding works

1. **Register as a partner** — contact your MongoDB partner manager or solutions engineer to initiate the OAuth app onboarding process.
2. **Agree on app configuration** — you and the MongoDB team agree on the OAuth app settings:
   - `redirect_uris` — the callback URL(s) your app will use
   - `client_type` — `single_page_app` (public) or `web_app` (confidential)
   - `grant_types` — typically `authorization_code`; `refresh_token` optional for confidential clients
   - `resources` — the Atlas API audience your app will access
3. **MongoDB provisions your app** — the MongoDB team registers the OAuth app in the Atlas OAuth platform for the target environment.
4. **MongoDB shares your credentials:**

| Client type | What you receive |
|---|---|
| SPA / native app (public client) | `client_id` only — no secret, uses `token_endpoint_auth_method: none` |
| Web app / backend service (confidential client) | `client_id` **and** `client_secret` |

:::caution
Do not use credentials from another provider (e.g. GitHub OAuth) with the MongoDB Atlas OAuth endpoints. The `client_id` must be a UUID issued by `authorize.mongodb.com`.
:::

## Public vs. confidential clients

| | Public (`single_page_app`) | Confidential (`web_app`) |
|---|---|---|
| Has `client_secret` | No | Yes |
| Supports refresh tokens | No | Yes (if configured) |
| Token exchange | PKCE only | PKCE + HTTP Basic auth |
| Best for | Browser SPAs, native apps | Apps with a secure backend server |

## Future model — self-serve via Atlas UI

The planned self-serve registration experience will allow partners to create and manage OAuth apps directly in Atlas without MongoDB team involvement:

```
Atlas UI → Organization → Integrations → OAuth Apps → Create App
```

Credentials will be displayed immediately after app creation. This guide will be updated when self-serve becomes generally available.

## For the demo

This repository ships with a pre-provisioned **Partner Test SPA** client for the dev environment. Set up your `.env`:

```ini title="oauthdemo/.env"
CLIENT_ID=<client-id-provided-by-mongodb>
# CLIENT_SECRET — leave blank for public SPA clients
OAUTH_BASE=https://authorize-dev.mongodb.com
CLOUD_BASE=https://cloud-dev.mongodb.com
RESOURCE=https://api-dev.mongodb.com/api/atlas
REDIRECT_URI=http://localhost:3000/oauth/callback
```

:::tip
`CLIENT_ID` must exactly match the value provisioned by MongoDB for your `redirect_uri`. Mixing credentials from different registrations causes `Invalid request to preauthorize`.
:::
