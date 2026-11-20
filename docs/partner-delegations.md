# Partner Delegation — Current State and Future State

This guide describes how partner delegation works today, what is intentionally not available yet, and what MongoDB has planned for future phases.

> [!NOTE]
> The official terms are now **Atlas App Connections** (the OAuth 2.1 platform) and **third-party app connections** (the per-organization setting). The governing API remains `delegationSettings`. See [Atlas App Connections Overview](https://www.mongodb.com/docs/atlas/app-connections/) and [Manage Third-Party App Access to Atlas](https://www.mongodb.com/docs/atlas/app-connections/manage-app-access/).

---

## On this page

- [Current capability](#current-capability)
- [How delegation works, step by step](#how-delegation-works-step-by-step)
- [Not available in the current model](#not-available-in-the-current-model)
- [Planned future capabilities](#planned-future-capabilities)
- [Roadmap summary](#roadmap-summary)
- [Additional caveat](#additional-caveat)

---

## Current capability

The current model is **organization-level opt-in plus user-level OAuth consent**. There is no per-user delegation toggle today.

> [!IMPORTANT]
> The `delegatedPartnerAccess` API field currently supports only `DISALLOWED` and `READ_WRITE` for partner applications. The partner launch has full-delegation semantics and static permission handling — a connected app can act anywhere the authorizing user's Atlas permissions allow. (Separately, **AI clients** connecting through the Remote MCP server are governed by an organization-level read / read-write / disabled access mode — see [Manage AI Client Access](https://www.mongodb.com/docs/mcp-server/remote-mcp/manage-ai-client-access/).)

**Default state:** App connections are **disabled by default** for existing organizations and for new organizations an existing Atlas user creates. They are **enabled by default** only for organizations a brand-new user creates at the time they sign up for Atlas.

---

## How delegation works, step by step

### Step 1: MongoDB registers the partner OAuth application

For approved design partners, MongoDB manually creates the OAuth app and provides the partner with a `client_id` (plus a `client_secret` for confidential clients). Apply via the [Become a Partner](https://www.mongodb.com/company/partners/) form with "Partner API" in the request.

### Step 2: An Organization Owner enables third-party app connections

The Organization Owner enables app connections either in the Atlas UI — **Organization Settings → App Connections → Allow users to connect third-party apps** — or via the API:

```http
PATCH /api/atlas/v2/orgs/{orgId}/delegationSettings
Content-Type: application/vnd.atlas.2025-03-12+json

{
  "delegatedPartnerAccess": "READ_WRITE"
}
```

`delegatedPartnerAccess` currently supports only `DISALLOWED` and `READ_WRITE`. The endpoint requires Organization Owner privileges. Organization Owners can also set a **maximum refresh token lifetime** for the organization from the same App Connections settings (default: 30-day maximum, 7-day idle).

### Step 3: The user must belong to the organization

The user must already be an Atlas member and can delegate only access they possess through their Atlas roles. The partner does not receive global Atlas access.

### Step 4: The user authorizes the partner

The partner starts the OAuth Authorization Code + PKCE flow. The user signs in, reviews the consent screen, and approves the application. The consent screen tells the user the app can:

- Know which Atlas resources you have access to
- Act on your behalf in Atlas organizations

> [!NOTE]
> In the current model, consent is broad: the user grants the partner access to **all eligible** Atlas organizations/projects associated with the user. There is no organization, project, or cluster picker yet.

### Step 5: MongoDB issues delegated tokens

MongoDB stores the grant and issues access and refresh tokens to the partner application. The partner uses the access token as a bearer token when calling the Atlas Administration API on behalf of the user.

### Step 6: MongoDB evaluates every API request

Effective access is determined by:

```
User Atlas membership
+ User Atlas roles
+ Organization app-connections setting
+ Endpoint not blocked for delegated access
```

A completed authorization doesn't guarantee API calls succeed — Atlas evaluates the org's delegation setting and the user's roles **on every request**, not once at authorization time.

### Example

| Organization | User membership | App connections | Partner access |
|---|---|---|---|
| Org A | Yes | Enabled (`READ_WRITE`) | Yes |
| Org B | Yes | Disabled (`DISALLOWED`) | No |
| Org C | No | Enabled (`READ_WRITE`) | No |

A user who belongs to Org A, B, and C would not automatically expose all three organizations — only the organizations where app connections are enabled **and** the user has access. `GET /api/atlas/v2/orgs` returns only those organizations.

### Step 7: The user or Organization Owner can stop access

- The **user** can revoke the partner application at any time from **Atlas Settings → App Connections**. The refresh token is invalidated immediately; the current access token remains valid until it expires (up to 10 minutes).
- An **Organization Owner** can disable app connections org-wide (Organization Settings → App Connections). Control-plane access ends **immediately** — Atlas checks the setting on every Administration API call.
- Changing the organization setting removes that organization from existing grants **without requiring the user to authorize again**.

> [!WARNING]
> Revocation does **not** remove resources the app already created — database users (data plane) and service accounts or API keys (control plane) remain active until you remove them. See [Offboarding Best Practices](https://www.mongodb.com/docs/atlas/app-connections/manage-app-access/).

---

## Not available in the current model

- Per-user enablement inside an organization
- Selecting one organization during consent
- Selecting individual projects or clusters
- Partner-specific organization/project/cluster allowlists
- Custom read-only Partner API grants
- Admin approval workflows for each user authorization
- Organization admin revocation of only one user's grant

---

## Planned future capabilities

### 1. Self-service partner onboarding

Partners are planned to create and manage OAuth applications themselves through Atlas, including:

- Client ID and secret creation
- Redirect URI management
- Logo and application metadata
- Permission selection
- Secret regeneration
- Application lifecycle management

This is associated with the self-service ecosystem phase rather than the current manually onboarded model.

### 2. Scoped delegation

The planned scoped-delegation model allows the user to choose:

- Specific organizations
- Specific projects
- Specific clusters
- Specific roles or permissions
- Read-only versus read-write access
- Potentially delegation duration

#### Example

```
Partner X:
  Org A / Project 1 / Project Read Only
  Org B / Project 7 / Cluster Management
```

This replaces today's broad "all eligible organizations/projects" grant with least-privilege authorization.

### 3. Enterprise approval and governance

The enterprise phase is planned to support:

1. User requests partner access.
1. Atlas detects that organization approval is required.
1. Organization admin reviews the requested app, resources, and permissions.
1. Admin approves or denies the request.
1. The user and partner see the approval status.
1. Admins can enforce policies, audit delegated actions, and revoke access organization-wide.

Admins are also expected to pre-approve particular organizations, projects, clusters, applications, or permission types.

---

## Roadmap summary

| Capability | Current | Planned |
|---|---|---|
| MongoDB-managed client registration | Yes (design partners) | Self-service later |
| Organization opt-in/out | Yes (UI: Org Settings → App Connections) | Yes |
| User OAuth consent | Yes | Yes |
| Org-level max refresh token lifetime | Yes | Yes |
| All eligible orgs/projects | Yes | Replaced by resource selection |
| Per-project/cluster selection | No | Planned |
| Read-only Partner API access | No current launch support | Planned (read-only exists today only for AI clients via Remote MCP access modes) |
| Admin approval workflows | No | Planned enterprise phase |
| Per-user or per-grant admin revocation | No | Planned |
| Detailed permission policies | Static/broad launch model | Planned granular policies |

---

## Additional caveat

> [!WARNING]
> If a partner creates a new Atlas organization, that organization may still need its own app connections setting enabled before the partner can access it — per the official guide, enabling app connections for a partner-created organization is a manual step (contact MongoDB to have the organization allowlisted). Creating an organization does not make it automatically accessible to the existing delegated token.

---

## Next steps

- [Partner Integration Guide](README.md) — token flows, curl examples, and testing setup
- [Partner Onboarding](PARTNER.md) — register with MongoDB and integrate the flow into your product
- [End-to-End Tutorial](END-TO-END.md) — from OAuth token to the first database read/write
- [Production Readiness](PRODUCTION.md) — launch checklist, token lifecycle, responsibility matrix
