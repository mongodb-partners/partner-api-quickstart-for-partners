# Partner UX Guide — Designing the "Connect MongoDB Atlas" Experience

This guide is for **partner product managers and designers**. It describes the screens, states, and copy for adding MongoDB Atlas as a first-class database option in your product — a two-click connection experience where users authorize access, select or create an Atlas resource, and start building **without copying connection strings**.

For the API calls behind each screen, see the [End-to-End Tutorial](END-TO-END.md). For token lifecycle behavior, see the [Production Readiness Guide](PRODUCTION.md).

---

## On this page

- [Design principles](#design-principles)
- [Screen 1: Database selection](#screen-1-database-selection)
- [Screen 2: The connect button](#screen-2-the-connect-button)
- [Screen 3: Consent handoff](#screen-3-consent-handoff)
- [Screen 4: Resource picker](#screen-4-resource-picker)
- [Screen 5: Provisioning state](#screen-5-provisioning-state)
- [Screen 6: Connected confirmation](#screen-6-connected-confirmation)
- [Screen 7: Reconnect after token expiry](#screen-7-reconnect-after-token-expiry)
- [Screen 8: Disconnect and revoke](#screen-8-disconnect-and-revoke)
- [Copy deck](#copy-deck)

---

## Design principles

1. **Two clicks to value.** From database selection to a working Atlas resource should feel like connecting a GitHub or Stripe account — not like reading cloud documentation.
1. **Never show a connection string.** Your backend provisions and stores everything. The user sees outcomes, not credentials.
1. **Every wait has a state.** OAuth redirects and cluster provisioning take time. Show progress; never drop the user on a spinner without context.
1. **Every failure has a next action.** Each error state includes a recovery path — see the [Recovery Guide](RECOVERY.md).

---

## Screen 1: Database selection

Present MongoDB Atlas alongside your other database options — it is a first-class choice, not an "advanced integration."

```
┌─────────────────────────────────────────────────┐
│  Choose a database                              │
│                                                 │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐    │
│  │  🍃        │  │  🐘        │  │  ⚡        │   │
│  │ MongoDB   │  │ Postgres  │  │  Redis    │    │
│  │ Atlas     │  │           │  │           │    │
│  │           │  │           │  │           │    │
│  │ Free M0   │  │           │  │           │    │
│  │ cluster   │  │           │  │           │    │
│  └───────────┘  └───────────┘  └───────────┘    │
└─────────────────────────────────────────────────┘
```

**Sample copy**

> **MongoDB Atlas**
> Fully managed MongoDB in the cloud. Connect your Atlas account or create a free cluster in minutes.

---

## Screen 2: The connect button

One clear action. Label it with the brand name — users should know exactly who they are authenticating with.

```
┌─────────────────────────────────────────────────┐
│  MongoDB Atlas                                  │
│                                                 │
│  Connect your Atlas account to provision and    │
│  manage databases without leaving <product>.    │
│                                                 │
│  ┌───────────────────────────────┐              │
│  │  🍃  Connect MongoDB Atlas     │              │
│  └───────────────────────────────┘              │
│                                                 │
│  You'll be redirected to MongoDB to authorize   │
│  access. You can revoke it at any time.         │
└─────────────────────────────────────────────────┘
```

**Sample copy**

> **Connect MongoDB Atlas**
> You'll be redirected to MongoDB to sign in and review the access you're granting. We never see your MongoDB password.

---

## Screen 3: Consent handoff

The redirect to Atlas is a trust boundary. Set expectations **before** the user leaves your product, and handle the return deliberately.

**Before redirect** (interstitial or tooltip):

> You're heading to MongoDB Atlas to authorize `<product>`. Review the permissions and click **Authorize** — you'll come right back here.

**During the Atlas hosted flow** (owned by MongoDB): the user signs in (or creates an Atlas account) and reviews the consent screen showing your app's name and logo (configured during [onboarding](PARTNER.md#step-2-agree-on-oauth-app-configuration)). The consent screen lists the permissions being requested:

- **Know which Atlas resources you have access to**
- **Act on your behalf in Atlas organizations**

It also tells the user that authorizing lets the app act in their Atlas resources just as they can — and that they can revoke access at any time.

**On return** — validate `state`, exchange the code, and land the user on a clear continuation:

> **Authorization successful** — now choose where your data should live.

> [!NOTE]
> If the user denies consent, do **not** strand them. Atlas redirects back with `error=access_denied` — return to your database selection screen with: *"No problem — authorization was cancelled. You can connect MongoDB Atlas whenever you're ready."* and a working **Connect** button.

---

## Screen 4: Resource picker

After authorization, let the user **select an existing resource or create a new free M0 cluster**. Both paths are first-class.

```
┌─────────────────────────────────────────────────┐
│  Where should your data live?                   │
│                                                 │
│  Organization                                   │
│  ┌─────────────────────────────────────────┐    │
│  │  Acme Inc.                            ▼ │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  ⦿ Use an existing project                      │
│    ┌───────────────────────────────────────┐    │
│    │  production                       ▼   │    │
│    └───────────────────────────────────────┘    │
│    Cluster:  [ my-cluster-0              ▼ ]    │
│                                                 │
│  ○ Create a new free cluster (M0)               │
│    Region:   [ AWS · US East (N. Virginia) ▼ ]  │
│                                                 │
│              [ Continue ]                       │
└─────────────────────────────────────────────────┘
```

**Guidelines**

- Default to the **create new M0** path for accounts with no existing clusters — it is the fastest route to value.
- Populate pickers from `GET /orgs`, `GET /groups?orgId=…`, and `GET /groups/{id}/clusters` with the user's delegated token. Only organizations that allow third-party app connections are returned.
- If the org list is empty, don't show a blank picker — explain that app connections may be disabled and link to the fix (Organization Settings → App Connections; see [Recovery Guide](RECOVERY.md#no-organizations-returned)). An empty list is a setup step, not an authorization failure.

---

## Screen 5: Provisioning state

M0 clusters take 3–7 minutes. A `201` from the create-cluster API means *started*, not *ready* — your UI must reflect that.

```
┌─────────────────────────────────────────────────┐
│  🍃 Creating your cluster…                      │
│                                                 │
│  ●●●○○  Provisioning "my-app-cluster" in        │
│         AWS · US East                           │
│                                                 │
│  This usually takes 3–5 minutes. You can keep   │
│  working — we'll notify you when it's ready.    │
└─────────────────────────────────────────────────┘
```

**Guidelines**

- Poll `GET /groups/{id}/clusters/{name}` until `stateName == "IDLE"` (see the [End-to-End Tutorial](END-TO-END.md#step-4-poll-until-the-cluster-is-idle)).
- Let the user navigate away — notify on completion; don't block the app.
- Provision the database user and access-list entry **silently** during this wait. The user should never see credentials.

---

## Screen 6: Connected confirmation

Confirm with a real artifact — the first successful read/write — not just a green checkmark.

```
┌─────────────────────────────────────────────────┐
│  ✅ Connected to MongoDB Atlas                  │
│                                                 │
│  Cluster:    my-app-cluster  (M0, AWS US East)  │
│  Database:   app_data                           │
│  Status:     First document written ✓           │
│                                                 │
│  [ Start building ]        [ View connection ]  │
└─────────────────────────────────────────────────┘
```

**Sample copy**

> **Connected to MongoDB Atlas**
> Your cluster is ready and we've verified it with a test write. Data you create in `<product>` is stored in your Atlas project.

---

## Screen 7: Reconnect after token expiry

Access tokens live ~10 minutes; refresh tokens rotate on every use and expire after 7 days idle or 30 days maximum (an Organization Owner can shorten this org-wide). When reauthorization is required, be transparent and lightweight.

```
┌─────────────────────────────────────────────────┐
│  ⟳ Reconnect MongoDB Atlas                      │
│                                                 │
│  Your Atlas authorization has expired. Reconnect│
│  to keep provisioning and managing clusters.    │
│  Your existing data is not affected.            │
│                                                 │
│            [ Reconnect MongoDB Atlas ]          │
└─────────────────────────────────────────────────┘
```

**Guidelines**

- Refresh silently in the background first — only show this screen when the refresh grant itself fails.
- Preserve the user's context: after reauthorization, return them to exactly where they were.

---

## Screen 8: Disconnect and revoke

Users must be able to disconnect from **both** sides — your product and Atlas.

**In your product:**

> **Disconnect MongoDB Atlas**
> This removes `<product>`'s access to your Atlas organization. Clusters and data in Atlas are **not** deleted. You can reconnect at any time.
> `[ Disconnect ]`

On disconnect, your backend must revoke the stored tokens (`POST https://authorize.mongodb.com/tokens/revoke`), delete cached tokens and database credentials — see [Revocation cleanup](PRODUCTION.md#revocation-cleanup).

**In Atlas:** users can revoke your app at any time from **Atlas Settings → App Connections**. When that happens, your next refresh returns `invalid_grant` (the current access token may work for up to 10 more minutes) — clear cached credentials and show the reconnect screen rather than retrying in a loop. Note that revocation does **not** delete resources your app created (database users, clusters) — clean those up as part of your disconnect flow.

---

## Copy deck

Ready-to-adapt strings for your UI:

| Element | Copy |
|---|---|
| Connect button | `Connect MongoDB Atlas` |
| Connect subtitle | `Authorize <product> to create and manage Atlas clusters on your behalf.` |
| Consent preface | `You're heading to MongoDB Atlas to sign in. We never see your MongoDB password.` |
| Consent expectations | `MongoDB will ask you to authorize <product> — it can then act in Atlas with your permissions. You can revoke it anytime in Atlas Settings → App Connections.` |
| Picker title | `Where should your data live?` |
| Create-new option | `Create a new free cluster (M0)` |
| Provisioning | `Creating your cluster… this usually takes 3–5 minutes.` |
| Success | `Connected to MongoDB Atlas — your cluster is ready.` |
| Expiry | `Your Atlas authorization expired. Reconnect to continue — your data is safe.` |
| Disconnect | `Disconnecting removes <product>'s access. Your Atlas data is not deleted.` |
| Revoked (from Atlas) | `Access was revoked in MongoDB Atlas. Reconnect to restore it.` |

---

## Next steps

- [End-to-End Tutorial](END-TO-END.md) — the API calls behind every screen
- [Recovery Guide](RECOVERY.md) — engineering behavior for each error state
- [Production Readiness Guide](PRODUCTION.md) — launch checklist
