# Production Readiness — Taking the Integration Live

The code in this repository (`get_token.py`, `api.py`, `end_to_end.py`) is a **development demo**. It persists tokens in a plaintext `.token_store.json`, opens a local HTTP callback, and proxies every request through one shared local token. That is ideal for learning the flow — it is **not** a production architecture.

This guide covers what changes when real users connect their Atlas accounts.

---

## On this page

- [Demo vs. production](#demo-vs-production)
- [Production checklist](#production-checklist)
- [Token lifecycle in production](#token-lifecycle-in-production)
- [Revocation cleanup](#revocation-cleanup)
- [Responsibility matrix](#responsibility-matrix)
- [Monitoring and alerting](#monitoring-and-alerting)

---

## Demo vs. production

| Concern | This demo | Production |
|---|---|---|
| Token storage | Plaintext `.token_store.json`, one shared file | Encrypted, per-tenant records in your database or vault |
| OAuth callback | `http://localhost:3000` | HTTPS endpoint under your domain |
| `state` / PKCE | Generated per run, `state` not verified | Cryptographically random, bound to the user session, **verified on callback** |
| Client secret | `.env` file | Secrets manager, never in code or browser |
| Refresh tokens | Single-user, single-process | Rotation-safe, concurrency-controlled per tenant |
| API errors | Surfaced raw | Retries with backoff; user-centered recovery ([Recovery Guide](RECOVERY.md)) |
| Revocation | Not handled | Cached credentials deleted; UI shows reconnect |

---

## Production checklist

### Token storage

- [ ] Tokens stored **per tenant** (one row/record per connected user), keyed by your internal user ID
- [ ] `access_token` and `refresh_token` **encrypted at rest** (KMS envelope encryption or your vault's transit engine)
- [ ] Tokens never written to application logs, error reports, analytics, or the browser
- [ ] Database passwords created during provisioning stored with the same rigor as OAuth tokens

### OAuth flow hardening

- [ ] Callback endpoints are **HTTPS only** in staging and production
- [ ] `state` is a random, single-use value bound to the user's session and **validated on every callback** (CSRF protection)
- [ ] PKCE `code_challenge` / `code_verifier` (S256) used on every authorization request — public and confidential clients alike
- [ ] `client_secret` lives in a secrets manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault); confidential-client exchanges use HTTP Basic auth server-side only
- [ ] Authorization codes treated as single-use and short-lived; never logged

### Token refresh and rotation

- [ ] Refresh happens **proactively** (e.g. at 50–80% of the 600-second lifetime), not only after a `401`
- [ ] The **newly returned refresh token is always persisted** — MongoDB may rotate it on every use; keeping the old value breaks the chain
- [ ] Concurrent refreshes for the same tenant are serialized (row lock / mutex / single-flight) so two workers don't race and invalidate each other's rotated token
- [ ] A failed refresh with `invalid_grant` marks the connection as *needs reauthorization* and triggers the reconnect UX — no retry loop

### Atlas API resilience

- [ ] Retries with exponential backoff + jitter on `429` and `5xx`; respect `Retry-After` when present
- [ ] Cluster creation treated as an **async operation**: poll `stateName` until `IDLE` with a timeout — never treat the `201` as completion
- [ ] Every request sends `Accept: application/vnd.atlas.2025-03-12+json` (pin and upgrade the API version deliberately)
- [ ] Timeouts on all outbound calls; no unbounded waits

### Provisioning and data plane

- [ ] Database users created with generated passwords, least-privilege roles (`readWrite` on the specific database — not `atlasAdmin`)
- [ ] IP Access List entries restricted to your application egress CIDRs — never `0.0.0.0/0`
- [ ] Connection strings assembled server-side from `connectionStrings.standardSrv`; never displayed to users
- [ ] Per-tenant Atlas resources (project/cluster/user) recorded so they can be torn down on disconnect

### Lifecycle and audit

- [ ] Audit log entries for: consent granted, token refreshed, resource provisioned, credential created, disconnect, and every `401/403` recovery path
- [ ] Disconnect deletes cached tokens **and** provisioned database credentials, and updates the UI state
- [ ] Access revoked Atlas-side is detected (first `401` that refresh can't fix) and transitions the tenant to *reconnect required*
- [ ] Alerting on refresh-failure rate, `403` spikes (possible org policy change), and provisioning timeouts

---

## Token lifecycle in production

| Token | Lifetime | Production handling |
|---|---|---|
| Access token | 600 s (10 min) | Proactive refresh; never exposed to browsers or logs |
| Refresh token | Configured per client (e.g. 30 days) | Persist every rotated value immediately; serialize concurrent refreshes; treat `invalid_grant` as *reauthorization required* |
| Authorization code | Seconds, single-use | Exchange immediately; never store |

Recommended refresh sequence per tenant:

```
1. Access token within 20–50% of expiry? ── no ──► use it
                 │ yes
                 ▼
2. Acquire per-tenant refresh lock
3. POST grant_type=refresh_token (Basic auth if confidential)
4. Persist BOTH new access_token AND new refresh_token atomically
5. Release lock
   On invalid_grant → mark tenant "reauthorization required",
                      surface "Reconnect MongoDB Atlas" in the UI
```

---

## Revocation cleanup

A user can end the relationship two ways — handle both:

**User disconnects in your product**

1. Delete stored `access_token` / `refresh_token` for the tenant
1. Delete or rotate provisioned database credentials (delete the Atlas database user if your integration created it)
1. Leave Atlas resources (project/cluster/data) untouched unless the user explicitly asks for deletion
1. Show: *"Disconnected. Your Atlas data was not deleted."*

**User revokes in Atlas** (authorized applications)

1. Your next API call returns `401`, and refresh returns `invalid_grant`
1. Clear cached credentials, mark the tenant *reconnect required*
1. Stop background jobs for that tenant — do not retry in a loop
1. Surface the reconnect prompt ([UX Guide](UX-GUIDE.md#screen-7-reconnect-after-token-expiry))

---

## Responsibility matrix

| Area | MongoDB | Partner (you) | End user |
|---|---|---|---|
| OAuth client registration | Provision and configure (invite-only model today; self-serve planned) | Supply redirect URIs, app metadata, logo, contacts | — |
| OAuth flow | Operate authorization server, consent screen, token issuance | Implement redirect, callback, `state`/PKCE validation, token exchange | Authenticate and consent |
| Atlas resource selection | Provide Admin API | Build the picker, provisioning states, and error handling | Choose organization / project / cluster |
| Provisioning | Provision infrastructure; report `stateName` | Poll to `IDLE`; create database user and access list; store credentials securely | Wait (or keep working — notified when ready) |
| Database credentials | Define lifecycle expectations via API | Generate, store, rotate, and use credentials server-side | Approve the overall access grant |
| Org-level controls | Expose `delegationSettings`, governance UX | Surface "delegation disabled" states with admin guidance | Org Owner enables/disables delegated access |
| Revocation | Invalidate grants and tokens | Delete cached credentials, disconnect UI, stop jobs | Revoke from Atlas authorized applications |
| Audit | Record delegated actions Atlas-side | Log integration lifecycle events per tenant | Review authorized applications |

> [!NOTE]
> Onboarding is currently invite-only and manually provisioned by MongoDB. Self-service app registration in Atlas is planned — see [Partner Delegation: Current & Future State](partner-delegations.md).

---

## Monitoring and alerting

Track these per tenant and in aggregate:

| Signal | Why it matters |
|---|---|
| Refresh success/failure rate | Rising `invalid_grant` = users falling out of authorization |
| `401` after refresh | Revoked Atlas-side; drives reconnect UX |
| `403` spikes | Org disabled delegation or user roles changed |
| Cluster provisioning time / timeouts | UX expectations; stuck `CREATING` states |
| Access-list and database-user operation failures | Data plane silently broken for new connections |
| Disconnect and revocation counts | Adoption health |

---

## Next steps

- [Recovery Guide](RECOVERY.md) — user-centered behavior for every failure condition
- [Partner UX Guide](UX-GUIDE.md) — the screens these behaviors power
- [Partner Onboarding](PARTNER.md) — getting credentials for staging and production
