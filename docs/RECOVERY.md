# Recovery Guide — User-Centered Error and Lifecycle Handling

Every failure in the connect experience should end in a **recovery path the user understands**, not a raw API error. This guide maps each condition to the partner behavior your engineering team should implement — and what the user sees.

For the screens and copy behind each state, see the [Partner UX Guide](UX-GUIDE.md). For raw symptom/cause/fix debugging during development, see [Troubleshooting](README.md#troubleshooting) in the Partner Integration Guide.

---

## Behavior matrix

| Condition | Partner behavior | What the user sees |
|---|---|---|
| **No organizations returned** | Explain that Delegated Partner Access may be disabled on their org; link to the admin action | "Your Atlas organization hasn't enabled partner access yet — ask your Organization Owner to enable it" |
| **401 Unauthorized** | Refresh the access token **once**; if refresh fails, prompt reauthorization | Silent if refresh works; otherwise "Reconnect MongoDB Atlas" |
| **403 Forbidden** | Insufficient Atlas role or org policy — do not retry; surface scope guidance | "You don't have permission for this on the selected project" |
| **Cluster is provisioning** | Poll `stateName` until `IDLE`; show progress; never treat the initial `201` POST as success | "Creating your cluster… (3–5 min)" |
| **Consent denied** | Preserve the user's workflow; offer retry without penalty | "Authorization was cancelled — nothing was connected" |
| **Access revoked (Atlas-side)** | Clear cached credentials; stop background jobs; show reconnect | "`<product>` no longer has access to MongoDB Atlas" |
| **Refresh token rotated** | Always persist the newly returned refresh token atomically with the new access token | — (invisible to the user) |
| **`invalid_grant` on refresh** | Mark tenant *reauthorization required*; do not retry the same grant | One-click reconnect prompt |
| **`429` / `5xx` from Atlas API** | Retry with exponential backoff + jitter; respect `Retry-After` | — (invisible unless persistent) |
| **`406 INVALID_VERSION_DATE`** | Add `Accept: application/vnd.atlas.2025-03-12+json` to every request | — (development-time issue) |

---

## Condition details

### No organizations returned

`GET /api/atlas/v2/orgs` returns only organizations where **both** are true: the user is a member, **and** Delegated Partner Access is enabled (`READ_WRITE`). An empty list usually means the org admin hasn't opted in.

**Do:** explain the admin action and link to it (Organization settings → delegated access, or the [`delegationSettings` API](README.md#step-4-enable-delegated-partner-access)).
**Don't:** show an empty picker or a generic "no data" state.

### 401 Unauthorized

Access tokens live 600 seconds. A `401` is normal lifecycle, not a bug.

**Do:** attempt exactly one refresh, retry the original call with the new token, and only surface UI when refresh itself fails.
**Don't:** loop retries or show the raw `401` to users.

### 403 Forbidden

The authenticated user lacks the Atlas role for the operation (e.g. creating a database user requires project-level user management), or the org's delegation setting changed mid-session.

**Do:** explain which resource was denied and offer the picker again or a "contact your admin" path.
**Don't:** retry identical calls — `403` is deterministic.

### Cluster is provisioning

Cluster creation is asynchronous. The `201` response means *accepted*.

**Do:** poll `GET …/clusters/{name}` every 15–30s until `stateName == "IDLE"`, with a generous timeout (~20 min) and a visible progress state. Let users navigate away and notify them.
**Don't:** proceed to database-user creation assuming connectivity, or block the whole app on the wait.

### Consent denied

The user clicked "Deny" on the Atlas consent screen — an intentional choice.

**Do:** land them back in your product with a neutral message and a working Connect button. Keep anything they configured before the redirect.
**Don't:** treat it as an error page or log the user out of any state.

### Access revoked

Users can revoke your app from their Atlas authorized applications at any time, and Org Owners can disable delegation org-wide.

**Do:** on the first refresh that returns `invalid_grant`, clear stored tokens, mark the tenant disconnected, stop background work, and show "Reconnect MongoDB Atlas".
**Don't:** keep calling the API with stale credentials or hide the state change.

### Refresh token rotated

MongoDB may return a **new** refresh token on every refresh call. The old one may be invalidated immediately.

**Do:** persist both new tokens atomically, and serialize concurrent refreshes per tenant (single-flight) so parallel workers don't race.
**Don't:** keep using a previously stored refresh token after a successful refresh.

---

## Related guides

- [Partner UX Guide](UX-GUIDE.md#copy-deck) — user-facing copy for each state
- [Production Readiness](PRODUCTION.md) — token storage, rotation, and revocation cleanup
- [Troubleshooting](README.md#troubleshooting) — development-time symptom/cause/fix table
