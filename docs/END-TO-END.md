# End-to-End Tutorial — From OAuth to the First Database Operation

This tutorial is the missing bridge between *"the API call succeeded"* and *"the user can build something."* It takes a delegated OAuth token all the way to a real database read/write — the moment your product can show **"Connected to MongoDB Atlas."**

By the end you will have:

1. Selected or created a project
1. Created an M0 free-tier cluster
1. Polled until the cluster is `IDLE`
1. Created a database user
1. Opened network access (IP Access List)
1. Retrieved the connection string
1. Connected with a MongoDB driver
1. Created a collection and inserted a document

---

## On this page

- [The full journey](#the-full-journey)
- [Before you begin](#before-you-begin)
- [Option A — Run the automated demo](#option-a--run-the-automated-demo)
- [Option B — Step by step](#option-b--step-by-step)
- [Map this to your product](#map-this-to-your-product)
- [Cleanup](#cleanup)
- [Next steps](#next-steps)

---

## The full journey

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant App as Your product
    participant OAuth as Atlas OAuth
    participant API as Atlas Admin API
    participant DB as Atlas cluster

    User->>App: Click "Connect MongoDB Atlas"
    App->>OAuth: Redirect (Authorization Code + PKCE)
    User->>OAuth: Authenticate and consent
    OAuth-->>App: Authorization code
    App->>OAuth: Exchange code for tokens
    OAuth-->>App: access_token + refresh_token
    App->>API: GET /orgs → select organization
    App->>API: POST /groups → select or create project
    App->>API: POST /groups/{id}/clusters → create M0
    App->>API: GET cluster → poll until stateName = IDLE
    App->>API: POST /databaseUsers → create database user
    App->>API: POST /accessList → allow app egress IPs
    App->>API: GET cluster → connectionStrings.standardSrv
    App->>DB: Connect with MongoDB driver, insert + read
    App-->>User: "Connected to MongoDB Atlas"
```

> [!NOTE]
> Steps 1–5 are the **OAuth flow** covered in the [Partner Integration Guide](README.md). This tutorial picks up at step 6 and continues through the first real database operation (steps 9–14).

---

## Before you begin

- You have a `client_id` from MongoDB — see [Get Your OAuth Credentials](README.md#get-your-oauth-credentials).
- Delegated Partner Access is enabled on your test organization — see [Set Up a Test Atlas Environment](README.md#set-up-a-test-atlas-environment).
- You have obtained a delegated access token:

  ```bash
  python3 get_token.py
  ```

- Dependencies installed (adds the PyMongo driver used for the data-plane step):

  ```bash
  python3 -m venv .venv
  source .venv/bin/activate     # Windows: .venv\Scripts\activate
  pip install -r requirements.txt
  ```

> [!IMPORTANT]
> The `databaseUsers` and `accessList` endpoints used below work with delegated tokens **when the authenticated user holds a role that permits user and network management on the project** (e.g. `Project Owner`). If you receive `403 Forbidden`, check the user's Atlas roles and the org's delegation setting — see the [Recovery Guide](RECOVERY.md).

---

## Option A — Run the automated demo

`end_to_end.py` performs the entire journey with one command, reusing any resources that already exist:

```bash
python3 get_token.py        # browser login — writes .token_store.json
python3 end_to_end.py       # full journey: org → project → M0 → user → network → first write
```

Expected output (abridged):

```
[1/9] Authenticate with the delegated OAuth token
[2/9] Select the Atlas organization
[3/9] Select or create the project
[4/9] Select or create the M0 cluster
[5/9] Wait for the cluster to become IDLE
[6/9] Create the database user
[7/9] Configure network access (IP Access List)
[8/9] Retrieve the connection string
[9/9] First database operation (connect, create collection, insert, read)

SUCCESS — first successful outcome reached.
```

Useful flags:

| Flag | Purpose |
|---|---|
| `--org-id <id>` | Choose a specific organization |
| `--project-name` / `--cluster-name` | Reuse or create named resources (idempotent) |
| `--cidr <ip>/32` | Access-list entry (default: this machine's detected public IP) |
| `--cleanup` | Delete the cluster, database user, and access-list entry afterwards |
| `--show-secrets` | Print the full connection URI including the password |

> [!WARNING]
> `end_to_end.py` stores no database password between runs — each run generates a fresh one and rotates it onto the database user. In your product, database credentials are per-tenant secrets: see the [Production Readiness Guide](PRODUCTION.md).

---

## Option B — Step by step

Everything `end_to_end.py` does, as individual API calls you can map into your own backend.

### Setup

```bash
API_BASE=https://api-dev.mongodb.com
ACCESS_TOKEN=$(python3 -c \
  "import json; print(json.load(open('.token_store.json'))['access_token'])")
```

### Step 1: Select the organization

```bash
curl -s "${API_BASE}/api/atlas/v2/orgs" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .results

ORG_ID=<selected-org-id>
```

In your product this is the **organization picker** — let the user choose instead of defaulting to the first result.

### Step 2: Select or create the project

```bash
# List existing projects to offer in the picker
curl -s "${API_BASE}/api/atlas/v2/groups?orgId=${ORG_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .results

# Or create a new one
curl -s -X POST "${API_BASE}/api/atlas/v2/groups" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d "{\"name\": \"my-app-project\", \"orgId\": \"${ORG_ID}\"}" | jq .

PROJECT_ID=<project-id-from-response>
```

### Step 3: Create the M0 cluster

```bash
CLUSTER_NAME=my-app-cluster

curl -s -X POST "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d '{
    "name": "'"${CLUSTER_NAME}"'",
    "clusterType": "REPLICASET",
    "replicationSpecs": [{
      "regionConfigs": [{
        "providerName": "TENANT",
        "backingProviderName": "AWS",
        "regionName": "US_EAST_1",
        "priority": 7,
        "electableSpecs": { "instanceSize": "M0" }
      }]
    }]
  }' | jq .
```

> [!WARNING]
> A `201` response means provisioning **started**, not that the cluster is usable. Show a "Creating your cluster…" state in your UI and poll — never treat the POST itself as success.

### Step 4: Poll until the cluster is IDLE

```bash
until [ "$(curl -s "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq -r .stateName)" = "IDLE" ]; do
  echo "Provisioning..."; sleep 15
done && echo "Cluster is ready."
```

M0 provisioning typically takes 3–7 minutes. Keep polling on a backoff and surface progress to the user.

### Step 5: Create the database user

The connection string identifies the cluster — it does **not** authenticate your app. Create a SCRAM user scoped to the database your app will use:

```bash
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")

curl -s -X POST "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/databaseUsers" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d '{
    "databaseName": "admin",
    "username": "app_user",
    "password": "'"${DB_PASSWORD}"'",
    "roles": [{ "roleName": "readWrite", "databaseName": "app_data" }]
  }' | jq .
```

> [!WARNING]
> Generate the password server-side, store it in your secrets manager, and scope the role to the specific database — never reuse the end user's identity for data-plane access and never expose this password to the browser.

### Step 6: Open network access

Atlas rejects connections from IPs not on the project's IP Access List. Add your application's egress IPs:

```bash
curl -s -X POST "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/accessList" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d '[{ "cidrBlock": "<your-egress-ip>/32", "comment": "partner app egress" }]' | jq .
```

> [!WARNING]
> Never use `0.0.0.0/0` for real users — it opens the database to the entire internet. For a quick local test only, detect your current IP with `curl -s https://api.ipify.org` and allow `<ip>/32`.

### Step 7: Retrieve the connection string

No separate API call is needed — it is on the cluster response:

```bash
SRV=$(curl -s "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq -r .connectionStrings.standardSrv)

echo "${SRV}"
# mongodb+srv://my-app-cluster.abcde.mongodb.net
```

### Step 8: Connect and perform the first write

```python
from pymongo import MongoClient

uri = f"mongodb+srv://app_user:{DB_PASSWORD}@my-app-cluster.abcde.mongodb.net/app_data?retryWrites=true&w=majority"
client = MongoClient(uri)

collection = client["app_data"]["first_connection"]
result = collection.insert_one({
    "message": "Connected to MongoDB Atlas via delegated OAuth",
})
print(collection.find_one({"_id": result.inserted_id}))
```

If the connection fails immediately after Step 6, wait ~30–60 seconds and retry — access-list and user changes take a moment to propagate.

### Step 9: Show the result

This is the payoff screen in your product:

> **Connected to MongoDB Atlas**
> Cluster `my-app-cluster` is ready. We wrote and read back your first document in `app_data.first_connection`.

---

## Map this to your product

| Tutorial step | Partner product equivalent |
|---|---|
| Select org / project / cluster | Resource picker with "use existing" and "create new M0" paths |
| Poll until `IDLE` | "Creating your cluster…" progress state |
| Create database user + access list | Silent, server-side provisioning — never shown to the user |
| First insert + read | "Connected" confirmation with a real artifact |
| `--cleanup` | Disconnect flow: delete created resources and cached credentials |

For the screens and copy behind each state, see the [Partner UX Guide](UX-GUIDE.md). For token storage, rotation, and revocation handling, see the [Production Readiness Guide](PRODUCTION.md).

---

## Cleanup

Remove everything the demo created:

```bash
python3 end_to_end.py --project-name partner-connect-demo --cluster-name connect-demo-m0 --cleanup
```

Or individually:

```bash
# Delete the cluster (permanent)
curl -s -X DELETE "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json"

# Delete the database user
curl -s -X DELETE "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/databaseUsers/admin/app_user" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json"

# Remove the access-list entry (URL-encode the CIDR)
curl -s -X DELETE "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/accessList/<url-encoded-cidr>" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json"
```

---

## Next steps

- [Partner UX Guide](UX-GUIDE.md) — screens, states, and sample copy for the connect experience
- [Production Readiness Guide](PRODUCTION.md) — token storage, rotation, revocation, and launch checklist
- [Recovery Guide](RECOVERY.md) — user-centered handling for every failure mode
- [Partner Integration Guide](README.md) — OAuth flows and the full Atlas Admin API reference
