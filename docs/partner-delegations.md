# Partner Delegation — Current State and Future State

This guide describes how partner delegation works today (Milestone 1), what is intentionally not available yet, and what MongoDB has planned for future phases.

---

## On this page

- [Current capability: Milestone 1](#current-capability-milestone-1)
- [How delegation works, step by step](#how-delegation-works-step-by-step)
- [Not available in the current model](#not-available-in-the-current-model)
- [Planned future capabilities](#planned-future-capabilities)
- [Roadmap summary](#roadmap-summary)
- [Additional caveat](#additional-caveat)

---

## Current capability: Milestone 1

The current model is **organization-level opt-in plus user-level OAuth consent**. There is no per-user delegation toggle today.

> [!IMPORTANT]
> The `READ_ONLY` option shown in the delegation API applies to MCP. Partner API delegation currently supports only `DISALLOWED` and `READ_WRITE`. The current Partner API launch has full-delegation semantics and static permission handling.

---

## How delegation works, step by step

### Step 1: MongoDB registers the partner OAuth application

For invited partners, MongoDB manually creates the OAuth app and provides the partner with a `client_id` and secret. The app is initially configured for testing.

### Step 2: An Organization Owner enables partner delegation

Existing organizations default to delegation disabled. The Organization Owner enables it using:

```http
PATCH /api/atlas/v2/orgs/{orgId}/delegationSettings
Content-Type: application/vnd.atlas.2025-03-12+json

{
  "delegatedPartnerAccess": "READ_WRITE"
}
```

`delegatedPartnerAccess` currently supports only `DISALLOWED` and `READ_WRITE`. The endpoint requires Organization Owner privileges.

### Step 3: The user must belong to the organization

The user must already be an Atlas member and can delegate only access they possess through their Atlas roles. The partner does not receive global Atlas access.

### Step 4: The user authorizes the partner

The partner starts the OAuth Authorization Code + PKCE flow. The user signs in, reviews the consent screen, and approves the application.

> [!NOTE]
> In the current M1 model, consent is broad: the user grants the partner access to **all eligible** Atlas organizations/projects associated with the user. There is no organization, project, or cluster picker yet.

### Step 5: MongoDB issues delegated tokens

MongoDB stores the grant and issues access and refresh tokens to the partner application. The partner uses the access token as a bearer token when calling the Atlas Admin API on behalf of the user.

### Step 6: MongoDB evaluates every API request

Effective access is determined by:

```
User Atlas membership
+ User Atlas roles
+ Organization delegation setting
+ Supported Partner API endpoint
```

### Example

| Organization | User membership | Delegation setting | Partner access |
|---|---|---|---|
| Org A | Yes | `READ_WRITE` | Yes |
| Org B | Yes | `DISALLOWED` | No |
| Org C | No | `READ_WRITE` | No |

A user who belongs to Org A, B, and C would not automatically expose all three organizations — only the organizations where delegation is enabled **and** the user has access.

### Step 7: The user or Organization Owner can stop access

- The **user** can revoke the partner application from their authorized applications.
- An **Organization Owner** can set the organization back to `DISALLOWED`.
- Changing the organization setting removes that organization from existing grants **without requiring the user to authorize again**.

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
| MongoDB-managed client registration | Yes | Self-service later |
| Organization opt-in/out | Yes | Yes |
| User OAuth consent | Yes | Yes |
| All eligible orgs/projects | Yes | Replaced by resource selection |
| Per-project/cluster selection | No | Planned |
| Read-only Partner API access | No current launch support | Planned |
| Admin approval workflows | No | Planned enterprise phase |
| Per-user or per-grant admin revocation | No | Planned |
| Detailed permission policies | Static/broad launch model | Planned granular policies |

---

## Additional caveat

> [!WARNING]
> If a partner creates a new Atlas organization, that organization may still need its own delegation setting enabled before the partner can access it. Creating an organization does not necessarily make it automatically accessible to the existing delegated token.

---

## Next steps

- [Partner Integration Guide](README.md) — token flows, curl examples, and testing setup
- [Partner Onboarding](PARTNER.md) — register with MongoDB and integrate the flow into your product
- [End-to-End Tutorial](END-TO-END.md) — from OAuth token to the first database read/write
- [Production Readiness](PRODUCTION.md) — launch checklist, token lifecycle, responsibility matrix
