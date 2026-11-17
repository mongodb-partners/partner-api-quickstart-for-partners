# Lovable + MongoDB Integration — Implementation Guide

Companion to the project plan *"Lovable + MongoDB Integration: Goal, Phases, and
Roadmap"*. This guide turns **Phase 0**, **Phase 1**, and the **roadmap
(Phases 2–4)** into concrete, executable work items.

**Goal:** let a published Lovable app read data from a customer's existing
MongoDB database, starting with a read-only dashboard. The initial scope is
**runtime, read-only access**. Lovable's custom MCP is a build/chat-context
feature and does **not** give a published app database access — the data path
must be a server-side runtime using the **official MongoDB driver** with a
customer-supplied connection string.

> **Status:** the driver path is a *proposed* direction. Direct TCP/driver
> connectivity, egress requirements, and secure connection-string handling must
> be validated in Phase 0 before committing to the pilot design.

---

## Architecture at a glance

```
┌──────────────────────┐   HTTPS (app reads via API)   ┌───────────────────────────┐
│  Published Lovable   │ ────────────────────────────▶ │  Server-side runtime      │
│  app (browser)       │                               │  (official MongoDB driver)│
└──────────────────────┘                               └─────────────┬─────────────┘
        no credentials in browser code                               │ direct TCP
                                                                     ▼
                                                        ┌───────────────────────────┐
                                                        │  Customer's MongoDB Atlas │
                                                        │  (least-privilege RO user)│
                                                        └───────────────────────────┘
```

- The **browser never sees** a connection string or credential.
- A **dedicated least-privilege read-only** database user is created by the
  customer.
- The customer **allowlists the runtime's egress IPs** in Atlas where required.
- The **chat MCP** stays a build-time/context tool — not the published-app data
  path.

---

## Phase 0 — Feasibility & alignment

**Objective:** confirm the driver runtime is viable and agree on pilot security
boundaries. Nothing is built for production here — we validate assumptions and
run one connectivity spike.

### 0.1 Confirm the execution model (with Lovable engineering)

Open questions to get **written** answers to:

- Can a published-app runtime use the official MongoDB driver over **direct
  TCP**, or must the driver live in a **separate server-side service**?
- What are the **egress IP ranges**, are they **stable**, and how does a
  customer allowlist them? Any plan/network constraints?
- Where are **customer connection strings stored**, and how are they accessed
  at runtime? Define handling, logging, rotation, and deletion expectations.
- Why was the retired **Data API** path ruled out, and does that change any
  design assumption?

### 0.2 Document the request flow & trust boundaries

Produce a one-page diagram covering: the driver request flow, trust boundaries,
where credentials live, the network path (app → runtime → Atlas), and failure
modes (timeout, auth failure, network block, secret missing).

### 0.3 Connectivity spike

Prove the riskiest assumption — that the runtime can actually open a driver
connection and run a scoped read. Minimal spike (Node.js example):

```js
// spike.mjs — run in the candidate runtime. Connection string comes from the
// runtime's secret store, never from browser code.
import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI;            // least-privilege, read-only user
const client = new MongoClient(uri, {
  serverSelectionTimeoutMS: 5000,
  maxPoolSize: 5,
});

async function main() {
  await client.connect();                        // proves direct TCP works
  const db = client.db("sample_mflix");
  // narrowly scoped read only
  const docs = await db.collection("movies")
    .find({ year: 1999 }, { projection: { title: 1, year: 1 } })
    .limit(5)
    .toArray();
  console.log("read ok:", docs.length, "docs");
  await client.close();
}

main().catch((e) => { console.error("spike failed:", e.message); process.exit(1); });
```

Run it from the **actual candidate runtime** (not your laptop) to validate
egress + TCP + driver support together.

### 0.4 Security review

Review Atlas authorization and network controls with the security team; record
unresolved constraints and an owner for each.

**Phase 0 exit criteria:** written confirmation of the runtime/network model,
credential-handling approach, egress instructions, and pilot security
boundaries — **or** a documented blocker and the next step.

---

## Phase 1 — Design-partner driver pilot

**Objective:** demonstrate secure, read-only access from a published Lovable app
to **one** customer's existing MongoDB deployment.

### 1.1 Customer setup (customer does these)

1. **Create a dedicated read-only database user**, scoped to the required
   database/collections only. In Atlas:

   ```javascript
   // Run in the customer's Atlas (mongosh against admin):
   use admin;
   db.createUser({
     user: "lovable_readonly",
     pwd:  "<GENERATED_STRONG_PASSWORD>",     // store in the secret manager
     roles: [
       { role: "read", db: "appdb" }           // narrowest scope that works
     ]
   });
   ```

2. **Allowlist the runtime's egress IP range** in Atlas → Network Access, if
   required.

3. **Provide the connection string** through Lovable's approved
   secret/configuration mechanism — never as a browser-visible value:

   ```
   mongodb+srv://lovable_readonly:<password>@<cluster>.mongodb.net/appdb?retryWrites=true&w=majority
   ```

### 1.2 Runtime (server-side) implementation

The runtime reads the secret, validates inputs, and runs only the agreed read
operations.

```js
// server/data.js — server-side only. Never shipped to the browser.
import { MongoClient } from "mongodb";

let client;
async function getClient() {
  if (!client) {
    client = new MongoClient(process.env.MONGODB_URI, {
      maxPoolSize: 10,
      serverSelectionTimeoutMS: 5000,
    });
    await client.connect();
  }
  return client;
}

const ALLOWED = {                            // allowlist collections
  appdb: new Set(["products", "orders"]),
};
const MAX_LIMIT = 100;

export async function readData({ db, collection, filter = {}, limit = 50 }) {
  if (!ALLOWED[db]?.has(collection)) {
    throw new Error("collection not allowed");
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > MAX_LIMIT) {
    throw new Error(`limit must be 1..${MAX_LIMIT}`);
  }
  const safeFilter = validateFilter(filter); // allowlist operators, no $where
  const c = await getClient();
  return c.db(db).collection(collection)
    .find(safeFilter).limit(limit).toArray();
}

function validateFilter(raw) {
  if (raw == null || typeof raw !== "object" || Array.isArray(raw)) return {};
  for (const [k, v] of Object.entries(raw)) {
    if (k.startsWith("$")) throw new Error(`operator not allowed: ${k}`);
  }
  return raw;
}
```

### 1.3 Validation checklist

- Connection behavior, **data refresh**, and access boundaries.
- Least-privilege behavior (reads only; writes rejected).
- **Connection failures and timeouts** handled gracefully.
- **Secret redaction** — no connection strings or document content in logs.
- Customer **teardown** and **credential-rotation** steps documented.

### 1.4 Deliverables & decision

Produce a one-page **reference architecture** and a **customer setup guide**.
Capture setup friction, operational needs, and security findings, then make a
**go/no-go** recommendation for broader availability.

**Pilot guardrails:** no credentials in client-side code; no broad write
permissions; access limited to the agreed read-only scope. Do not assume OAuth
client credentials or the chat MCP provide database authorization for the
published app.

---

## Roadmap after the pilot

### Phase 2 — Safer onboarding

**Focus:** reduce customer setup effort without expanding access.

- Evaluate **Atlas Admin API** automation for database-user creation and
  credential rotation; design scoped roles and per-database/collection access.
- Keep provisioning credentials **separate** from the runtime data path — the
  Admin API does not replace the driver data path.
- Pilot the automation in a controlled environment with explicit customer
  consent and teardown.

```js
// Illustrative: create a scoped read-only user via the Atlas Admin API.
// Provisioning credentials are separate from the runtime data path.
const resp = await fetch(
  `https://cloud.mongodb.com/api/atlas/v2/groups/${PROJECT_ID}/databaseUsers`,
  {
    method: "POST",
    headers: { "Content-Type": "application/json",
               "Authorization": `Digest ${digestAuth}` }, // Admin API creds
    body: JSON.stringify({
      databaseName: "admin",
      username: `lovable_ro_${customerId}`,
      roles: [{ roleName: "read", databaseName: "appdb" }],
    }),
  });
```

### Phase 3 — Enterprise identity & networking

**Focus:** support enterprise security requirements.

- Validate **workload identity federation (WIF)** against customer IdPs, trust
  models, and the selected driver runtime.
- Evaluate **private networking / private endpoints** for supported deployment
  shapes; define **audit event** requirements.
- Treat WIF and private connectivity as **discovery items** until feasibility
  and product support are confirmed.

### Phase 4 — Scale & productization

**Focus:** operationalize multi-customer usage.

- Define **tenant isolation**, per-customer secret lifecycle, **connection
  pooling/limits**, observability, incident response, support ownership, and
  onboarding automation.
- **Load-test** the driver path and establish service-level expectations.
- Revisit **Partner API** or runtime **MCP** options if Lovable capabilities
  evolve.

---

## Open decisions & risks

- Is direct TCP/driver connectivity supported in Lovable's published-app
  runtime, or must the driver run in a separate server-side service?
- Are Lovable egress IPs stable and allowlistable for target customer plans?
- Which secret store and access controls are available for customer connection
  strings?
- What is the supported scope for database/collection restrictions, auditing,
  and credential rotation?
- What networking, identity, and usage constraints apply to target Atlas tiers
  and Lovable plans?

---

## Related: JRPC HTTP API gateway (independent alternative)

The JRPC Remote MCP quickstart is an **independent alternative** to the
driver-based plan above — not part of Phases 0–4. It runs as a secured HTTPS
service in front of Atlas Managed Remote MCP; the published app calls its HTTP
API instead of using a direct driver connection. See `README.md` and
`IMPLEMENTATION.md` in this folder for its implementation. Treat it as an
alternative pending security, product-fit, and multi-tenant validation — not as
an already production-ready BYOK service.

## References

- Project plan: *Lovable + MongoDB integration* (Google Doc)
- MongoDB Atlas: [database users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/),
  [IP access list](https://www.mongodb.com/docs/atlas/security/ip-access-list/),
  [Atlas Admin API](https://www.mongodb.com/docs/atlas/api/)
- Lovable custom MCP guidance
