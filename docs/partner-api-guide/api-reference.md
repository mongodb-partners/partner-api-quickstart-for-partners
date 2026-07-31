---
id: api-reference
sidebar_position: 3
title: Atlas API Reference
description: curl and Python examples for all Partner API endpoints — orgs, projects, and clusters.
---

# Atlas API Reference

All requests require:

```
Authorization: Bearer <access_token>
Accept: application/vnd.atlas.2025-03-12+json
```

Set these variables before running any command:

```bash
API_BASE=https://api-dev.mongodb.com
ORG_ID=<your-org-id>
PROJECT_ID=<your-project-id>
CLUSTER_NAME=<your-cluster-name>

ACCESS_TOKEN=$(python3 -c \
  "import json; print(json.load(open('oauthdemo/.token_store.json'))['access_token'])")
```

---

## List Organizations

Returns all Atlas Organizations the user belongs to that have Delegated Partner Access enabled.

```bash
curl -s "${API_BASE}/api/atlas/v2/orgs" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

Filter by name:

```bash
curl -s "${API_BASE}/api/atlas/v2/orgs?name=Acme" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

<details>
<summary>Python example</summary>

```python
import json, urllib.request

API_BASE     = "https://api-dev.mongodb.com"
ACCESS_TOKEN = json.load(open("oauthdemo/.token_store.json"))["access_token"]

req = urllib.request.Request(
    f"{API_BASE}/api/atlas/v2/orgs",
    headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/vnd.atlas.2025-03-12+json",
    },
)
with urllib.request.urlopen(req) as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))
```

</details>

---

## List Projects in an Organization

```bash
curl -s "${API_BASE}/api/atlas/v2/groups?orgId=${ORG_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

---

## Create a Project

```bash
curl -s -X POST "${API_BASE}/api/atlas/v2/groups" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" \
  -H "Content-Type: application/vnd.atlas.2025-03-12+json" \
  -d "{\"name\": \"my-project\", \"orgId\": \"${ORG_ID}\"}" | jq .
```

Copy the `id` field from the response — this is your `PROJECT_ID`.

<details>
<summary>Python example</summary>

```python
import json, urllib.request

payload = json.dumps({"name": "my-project", "orgId": ORG_ID}).encode()
req = urllib.request.Request(
    f"{API_BASE}/api/atlas/v2/groups",
    data=payload,
    method="POST",
    headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Accept": "application/vnd.atlas.2025-03-12+json",
        "Content-Type": "application/vnd.atlas.2025-03-12+json",
    },
)
with urllib.request.urlopen(req) as resp:
    print(json.dumps(json.loads(resp.read()), indent=2))
```

</details>

---

## Create a Cluster

Creates a free **M0** cluster (shared, no charge). Change `instanceSize` to `M10` or higher for dedicated clusters.

```bash
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

Available cluster options:

| Field | Options | Default |
|---|---|---|
| `backingProviderName` | `AWS`, `GCP`, `AZURE` | `AWS` |
| `regionName` | `US_EAST_1`, `EU_WEST_1`, `AP_SOUTHEAST_1`, etc. | `US_EAST_1` |
| `instanceSize` | `M0` (free), `M10`, `M20`, `M30`, … | `M0` |

---

## Get Cluster Status

```bash
curl -s "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .stateName
```

| `stateName` | Meaning |
|---|---|
| `CREATING` | Cluster is being provisioned |
| `IDLE` | Cluster is running and ready |
| `UPDATING` | Configuration change in progress |
| `DELETING` | Cluster is being deleted |
| `DELETED` | Cluster no longer exists |

Poll until ready:

```bash
until [ "$(curl -s "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq -r .stateName)" = "IDLE" ]; do
  echo "Waiting for cluster..."; sleep 15
done
echo "Cluster is ready."
```

---

## Delete a Cluster

:::danger
Deletion is **permanent and irreversible**. The cluster moves to `DELETING` state and disappears after a few minutes.
:::

```bash
curl -s -X DELETE \
  "${API_BASE}/api/atlas/v2/groups/${PROJECT_ID}/clusters/${CLUSTER_NAME}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```
