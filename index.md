# Connect MongoDB Atlas — Integration Kit for Partners

**Add "Connect MongoDB Atlas" as a first-class database option in your product.** Users authorize access, select or create an Atlas resource, and begin building — without copying connection strings.

This kit shows ISV and Technology Partners how to build that experience on the MongoDB Atlas Admin API - V2 with OAuth 2.1 delegated access: your users log in to Atlas directly, and your app receives short-lived, user-scoped tokens — you never see their credentials and never need an org-level API key.

---

## The experience you're building

```
1.  User selects "Connect MongoDB Atlas" in your product
2.  Your app redirects the user to Atlas OAuth
3.  User authenticates and reviews permissions
4.  Your app receives delegated tokens
5.  User selects an existing project/cluster — or creates a new M0 cluster
6.  Your app provisions the database user and connection, server-side
7.  The application performs its first successful read/write
8.  User can view or revoke access from Atlas at any time
```

> [!TIP]
> **Open the [interactive docs site](docs/)** — a guided walkthrough with an interactive OAuth flow explorer, architecture diagram, and rendered guides.

## Choose your path

| I am a… | Start here |
|---|---|
| **Partner developer** | [Partner Integration Guide](docs/README.md) → [End-to-End Tutorial](docs/END-TO-END.md) → [Production Readiness](docs/PRODUCTION.md) — OAuth, token storage, Admin API calls, provisioning, data-plane access, refresh, revocation |
| **Partner product / UX** | [Partner UX Guide](docs/UX-GUIDE.md) — connect button, consent handoff, resource picker, provisioning states, errors, and disconnect experience, with sample copy |
| **Atlas user / admin** | [Partner Delegation: Current & Future State](docs/partner-delegations.md) — delegated access, organization controls, auditability, and revocation |

## Choose your integration pattern

Before writing code, decide which shape your product needs:

| Integration shape | Use case | Guides |
|---|---|---|
| **Control plane** | List organizations, create projects/clusters, retrieve connection details | [Integration Guide](docs/README.md) |
| **Data plane** | Your application or agent reads/writes cluster data | [End-to-End Tutorial](docs/END-TO-END.md) |
| **Scoped / RBAC access** | Read-only, resource-scoped, or enterprise-controlled access | [Delegation roadmap](docs/partner-delegations.md) (planned) |

## Get to the first successful outcome

The fastest path through the kit:

1. **[Onboard](docs/PARTNER.md)** — receive OAuth credentials from MongoDB (invite-only Early Access).
1. **[Get a token](docs/README.md#obtain-an-access-token)** — `python3 get_token.py` runs the OAuth 2.1 Authorization Code + PKCE flow.
1. **[Complete the journey](docs/END-TO-END.md)** — `python3 end_to_end.py` provisions a project, M0 cluster, database user, and network access, then performs the first read/write.
1. **[Design the experience](docs/UX-GUIDE.md)** — screens, states, and copy for your product.
1. **[Go to production](docs/PRODUCTION.md)** — encrypted per-tenant token storage, refresh-token rotation, revocation cleanup, and the launch checklist.

## Documentation

| Guide | Description |
|---|---|
| [Partner Onboarding](docs/PARTNER.md) | Register with MongoDB, receive OAuth credentials, promote from dev to production |
| [Partner Integration Guide](docs/README.md) | OAuth flows, environments, Atlas Admin API reference, FastAPI demo server, test setup |
| [End-to-End Tutorial](docs/END-TO-END.md) | From OAuth token to the first database read/write — the complete "Connect MongoDB Atlas" journey |
| [Partner UX Guide](docs/UX-GUIDE.md) | Connect experience screens, states, and sample copy |
| [Production Readiness](docs/PRODUCTION.md) | Demo vs. production, security checklist, token lifecycle, responsibility matrix |
| [Recovery Guide](docs/RECOVERY.md) | User-centered handling for every error and lifecycle condition |
| [Partner Delegation](docs/partner-delegations.md) | How delegation works today (M1) and what's planned next |

## Resources

- [Atlas Administration API reference](https://www.mongodb.com/docs/api/doc/atlas-admin-api-v2) — official endpoint documentation
- [MongoDB Documentation](https://www.mongodb.com/docs/) — product documentation home
- [GitHub repository](https://github.com/mongodb-partners/partner-api-quickstart-for-partners) — code and examples
- Atlas App Connections overview, branding assets, and support/escalation path — available from your MongoDB partner contact during Early Access

> [!IMPORTANT]
> **The runnable code in this repository is a development demo.** Tokens are stored in a plaintext `.token_store.json`, the OAuth callback is a local HTTP server, and all requests share one local token. Before building for real users, read the [Production Readiness Guide](docs/PRODUCTION.md).
