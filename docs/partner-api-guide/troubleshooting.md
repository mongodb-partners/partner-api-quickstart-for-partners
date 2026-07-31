---
id: troubleshooting
sidebar_position: 5
title: Troubleshooting
description: Common errors and fixes for the Atlas Partner API OAuth integration.
---

# Troubleshooting

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `Invalid request to preauthorize` | `client_id` or `redirect_uri` mismatch | `CLIENT_ID` in `.env` must exactly match the value MongoDB provisioned for that `redirect_uri` |
| `406 INVALID_VERSION_DATE` | Missing `Accept` header | Add `-H "Accept: application/vnd.atlas.2025-03-12+json"` to every Atlas API request |
| `401 Unauthorized` from Atlas API | Access token expired | Re-run `python3 oauthdemo/get_token.py` |
| `401` from FastAPI server | Token expired or not yet obtained | Re-run `python3 oauthdemo/get_token.py` |
| `405 Method Not Allowed` on `/authorize` | Wrong base URL used | Use `CLOUD_BASE` for `/oauth/authorize`, not `OAUTH_BASE` |
| `403 Forbidden` on Atlas API | Delegated Partner Access not enabled | See [Enable Delegated Partner Access](/partner-api-guide/enable-delegated-access) |
| `400 invalid_grant` | Authorization code already used or expired | Codes are single-use and short-lived — restart the auth flow |
| `400 grant_type not supported` | Refresh token used on a client that doesn't support it | This client was registered with `grant_types: [authorization_code]` only — re-run the browser flow |
| `Authentication failed (E0000004)` | Logged in with base email in dev | Use the tagged email: `you+mongodb.com@gmail.com` |
| `OSError: [Errno 48] Address already in use` | Port 3000 left open from a previous run | The script auto-frees the port on startup; or run `lsof -ti:3000 \| xargs kill -9` manually |
| `PermissionError: [Errno 13]` | Port below 1024 requires root | Use `--redirect-port 3000` or above |
| `Could not import module "api"` | uvicorn run from wrong directory | `cd oauthdemo` first, then run `uvicorn api:app` |
| Token not received after 5 minutes | Browser did not redirect to localhost | Re-run the script — PKCE state expired |

## Credential mismatch errors

The most common cause of `Invalid request to preauthorize` is using a `client_id` from one environment or provider with credentials from another:

- GitHub OAuth credentials **cannot** be used with `authorize.mongodb.com`
- Dev `client_id` values **cannot** be used against staging or production endpoints
- Each `client_id` is bound to specific `redirect_uri` values at registration time — these must match exactly

## Token debugging

Inspect a stored token without making any API calls:

```bash
# Check expiry
curl -s http://localhost:8080/health | jq .

# Decode the JWT payload (base64, no verification)
python3 -c "
import json, base64
token = open('oauthdemo/.token_store.json').read()
payload = json.loads(token)['access_token'].split('.')[1]
padding = 4 - len(payload) % 4
print(json.dumps(json.loads(base64.urlsafe_b64decode(payload + '='*padding)), indent=2))
"
```
