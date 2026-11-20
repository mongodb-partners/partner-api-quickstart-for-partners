# Recovery Guide — User-Centered Error and Lifecycle Handling

Every failure in the connect experience should end in a **recovery path the user understands**, not a raw API error. This guide maps each condition to the partner behavior your engineering team should implement — and what the user sees.

For the screens and copy behind each state, see the [Partner UX Guide](UX-GUIDE.md). For raw symptom/cause/fix debugging during development, see [Troubleshooting](README.md#troubleshooting) in the Partner Integration Guide.

---

## Behavior matrix

| Condition | Partner behavior | What the user sees |
|---|---|---|
| **No organizations returned** | Explain that third-party app connections may be disabled on their org; link to the admin action (Organization Settings → App Connections) — an empty org list is a setup step, **not** an auth failure | "Your Atlas organization hasn't enabled app connections yet — ask your Organization Owner to enable them" |
| **401 Unauthorized** | Refresh the access token **once**; if refresh fails, prompt reauthorization | Silent if refresh works; otherwise "Reconnect MongoDB Atlas" |
| **403 Forbidden** | Insufficient Atlas role, org policy, or a blocked endpoint — do not retry; surface scope guidance and name the required role | "You don't have permission for this on the selected project" |
| **Cluster is provisioning** | Poll `stateName` until `IDLE`; show progress; never treat the initial `201` POST as success | "Creating your cluster… (3–5 min)" |
| **Consent denied** (`access_denied`) | Preserve the user's workflow; offer retry without penalty | "Authorization was cancelled — nothing was connected" |
| **Access revoked (Atlas-side)** | Clear cached credentials; stop background jobs; show reconnect | "`<product>` no longer has access to MongoDB Atlas" |
| **App connections disabled org-wide** | Expect immediate `403`s — Atlas checks the org setting on every call; guide the user to their Organization Owner | "Your organization has restricted third-party app connections" |
| **Client disabled by MongoDB** | `invalid_client` / `access_denied` with `client is disabled` is **terminal** — stop retrying and contact the MongoDB partner team | "This integration is temporarily unavailable — we're working with MongoDB to restore it" |
| **Refresh token rotated** | Always persist the newly returned refresh token atomically with the new access token — the old one is invalidated immediately | — (invisible to the user) |
| **`invalid_grant` on refresh** | Mark tenant *reauthorization required*; do not retry the same grant | One-click reconnect prompt |
| **`429` / `5xx` from Atlas API** | Retry with exponential backoff + jitter; respect `Retry-After` | — (invisible unless persistent) |
| **`406 INVALID_VERSION_DATE`** | Add `Accept: application/vnd.atlas.2025-03-12+json` to every request | — (development-time issue) |

---

## Condition details

### No organizations returned

`GET /api/atlas/v2/orgs` returns only organizations where **both** are true: the user is a member, **and** the organization allows third-party app connections (`delegatedPartnerAccess: READ_WRITE`). An empty list usually means the org admin hasn't opted in.

**Do:** explain the admin action and link to it (Organization Settings → App Connections, or the [`delegationSettings` API](README.md#step-4-enable-third-party-app-connections-delegated-partner-access)).
**Don't:** show an empty picker or a generic "no data" state — and don't present it as an authentication error; the user's credentials and consent are valid.

### 401 Unauthorized

Access tokens currently live 600 seconds (rely on `expires_in`). A `401` is normal lifecycle, not a bug.

**Do:** attempt exactly one refresh, retry the original call with the new token, and only surface UI when refresh itself fails.
**Don't:** loop retries or show the raw `401` to users.

### 403 Forbidden

The authenticated user lacks the Atlas role for the operation (e.g. creating a project needs `Organization Owner` or `Organization Project Creator`; creating a cluster needs `Project Owner` or `Project Cluster Creator`), the org's app-connections setting changed mid-session, or the endpoint is blocked for delegated access (e.g. federation settings).

**Do:** explain which resource was denied, name the required role, and offer the picker again or a "contact your admin" path.
**Don't:** retry identical calls — `403` is deterministic.

### Cluster is provisioning

Cluster creation is asynchronous. The `201` response means *accepted*.

**Do:** poll `GET …/clusters/{name}` every 15–30s until `stateName == "IDLE"`, with a generous timeout (~20 min) and a visible progress state. Let users navigate away and notify them.
**Don't:** proceed to database-user creation assuming connectivity, or block the whole app on the wait.

### Consent denied

The user clicked **Decline** on the Atlas consent screen — an intentional choice. Atlas redirects back with `error=access_denied`.

**Do:** land them back in your product with a neutral message and a working Connect button. Keep anything they configured before the redirect.
**Don't:** treat it as an error page or log the user out of any state.

### Access revoked

Users can revoke your app at any time from **Atlas Settings → App Connections**, and Org Owners can disable app connections org-wide (immediate `403`s on every call).

**Do:** on the first refresh that returns `invalid_grant`, clear stored tokens, mark the tenant disconnected, stop background work, and show "Reconnect MongoDB Atlas".
**Don't:** keep calling the API with stale credentials or hide the state change.

### Refresh token rotated

Every refresh call returns a **new** refresh token, and the previous one is invalidated immediately. Refresh tokens also expire after 7 days idle or 30 days maximum (Organization Owners can shorten this).

**Do:** persist both new tokens atomically, and serialize concurrent refreshes per tenant (single-flight) so parallel workers don't race.
**Don't:** keep using a previously stored refresh token after a successful refresh.

---

## Related guides

- [Partner UX Guide](UX-GUIDE.md#copy-deck) — user-facing copy for each state
- [Production Readiness](PRODUCTION.md) — token storage, rotation, and revocation cleanup
- [Troubleshooting](README.md#troubleshooting) — development-time symptom/cause/fix table
