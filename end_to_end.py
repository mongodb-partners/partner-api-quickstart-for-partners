"""
Connect MongoDB Atlas — end-to-end demo (DEVELOPMENT DEMO, not production architecture).

Runs the complete "first successful outcome" journey with a delegated OAuth token:

    1. Load (and if needed refresh) the delegated access token from .token_store.json
    2. List organizations the token can access
    3. Select or create a project
    4. Select or create an M0 free-tier cluster
    5. Poll until the cluster reports stateName == IDLE
    6. Create (or update) a SCRAM database user
    7. Add an IP Access List entry so this machine can reach the cluster
    8. Read connectionStrings.standardSrv from the cluster response
    9. Connect with a MongoDB driver, create a collection, insert + read a document

Usage:
    python3 get_token.py                 # first: browser login, writes .token_store.json
    python3 end_to_end.py                # full journey with defaults
    python3 end_to_end.py --cleanup      # tear down everything it created afterwards

Prerequisites:
    pip install -r requirements.txt      # adds pymongo + dnspython

This script intentionally mirrors what a partner backend would do per-tenant —
see docs/PRODUCTION.md for how this maps to a production architecture.
"""

import argparse
import base64
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_STORE = os.path.join(SCRIPT_DIR, ".token_store.json")
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")

ATLAS_VERSION = "application/vnd.atlas.2025-03-12+json"

# Poll settings
CLUSTER_POLL_INTERVAL_S = 15
CLUSTER_TIMEOUT_S = 20 * 60       # M0 provisioning usually takes 3–7 minutes
CONNECT_RETRY_INTERVAL_S = 10
CONNECT_TIMEOUT_S = 3 * 60        # access-list / user propagation is usually < 60s


# ---------------------------------------------------------------------------
# Config / tokens (same conventions as get_token.py and api.py)
# ---------------------------------------------------------------------------

def load_env():
    env = {}
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip()
    except FileNotFoundError:
        pass
    return env


def get_api_base(env):
    cloud_base = env.get("CLOUD_BASE", "https://cloud-dev.mongodb.com")
    return (
        cloud_base
        .replace("cloud-dev.", "api-dev.")
        .replace("cloud-stage.", "api-stage.")
        .replace("//cloud.", "//api.")
    )


def load_token_store():
    if not os.path.exists(TOKEN_STORE):
        sys.exit(
            "No token store found. Run `python3 get_token.py` first to authenticate."
        )
    try:
        with open(TOKEN_STORE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        sys.exit("Token store is corrupted. Re-run `python3 get_token.py`.")


def save_token_store(store):
    with open(TOKEN_STORE, "w") as f:
        json.dump(store, f, indent=2)


def refresh_access_token(env, store):
    """Exchange the stored refresh token for a new access token (rotation-safe:
    always persists the newly returned refresh token)."""
    refresh_token = store.get("refresh_token")
    if not refresh_token:
        sys.exit(
            "Access token expired and no refresh token is stored.\n"
            "Re-run `python3 get_token.py` for a fresh browser login."
        )

    oauth_base = env.get("OAUTH_BASE", "https://authorize-dev.mongodb.com")
    client_id = env.get("CLIENT_ID", "")
    client_secret = env.get("CLIENT_SECRET") or None

    params = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if client_secret:
        raw = f"{client_id}:{client_secret}"
        headers["Authorization"] = "Basic " + base64.b64encode(raw.encode()).decode()
    else:
        params["client_id"] = client_id

    req = urllib.request.Request(
        f"{oauth_base}/tokens",
        data=urllib.parse.urlencode(params).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(
            f"Refresh failed (HTTP {e.code}): {e.read().decode()}\n"
            "Re-run `python3 get_token.py` for a fresh browser login."
        )

    store["access_token"] = token_data["access_token"]
    store["token_type"] = token_data.get("token_type", "Bearer")
    store["expires_at"] = int(time.time()) + int(token_data.get("expires_in", 600))
    if "refresh_token" in token_data:  # rotation: always persist the new value
        store["refresh_token"] = token_data["refresh_token"]
    save_token_store(store)
    print("  Access token refreshed (rotated refresh token persisted).")
    return store


def get_access_token(env):
    store = load_token_store()
    if store.get("expires_at", 0) and time.time() > store["expires_at"] - 30:
        print("  Access token expired (or expiring) — using refresh token...")
        store = refresh_access_token(env, store)
    token = store.get("access_token")
    if not token:
        sys.exit("No access token in store. Run `python3 get_token.py`.")
    return token


# ---------------------------------------------------------------------------
# Atlas Admin API helper
# ---------------------------------------------------------------------------

class AtlasApiError(Exception):
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload
        message = payload.get("detail") or payload.get("error") or str(payload)
        super().__init__(f"HTTP {status}: {message}")


class AtlasClient:
    def __init__(self, api_base, token):
        self.api_base = api_base
        self.token = token

    def request(self, method, path, body=None):
        url = f"{self.api_base}{path}"
        payload = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": ATLAS_VERSION,
        }
        if payload is not None:
            headers["Content-Type"] = ATLAS_VERSION
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                detail = json.loads(raw)
            except json.JSONDecodeError:
                detail = {"detail": raw}
            raise AtlasApiError(e.code, detail) from e

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body):
        return self.request("POST", path, body)

    def patch(self, path, body):
        return self.request("PATCH", path, body)

    def delete(self, path):
        return self.request("DELETE", path)


# ---------------------------------------------------------------------------
# Journey steps
# ---------------------------------------------------------------------------

def step(n, total, label):
    print(f"\n[{n}/{total}] {label}")


def pick_organization(atlas, org_id=None):
    orgs = atlas.get("/api/atlas/v2/orgs").get("results", [])
    if not orgs:
        sys.exit(
            "No organizations returned. Delegated Partner Access may be disabled on\n"
            "your org — see docs/RECOVERY.md#no-organizations-returned."
        )
    if org_id:
        for org in orgs:
            if org["id"] == org_id:
                print(f"  Using organization: {org['name']} ({org['id']})")
                return org
        sys.exit(f"Organization {org_id} not found in delegated token scope.")
    org = orgs[0]
    print(f"  Using organization: {org['name']} ({org['id']})")
    if len(orgs) > 1:
        print(f"  ({len(orgs)} orgs accessible — pass --org-id to choose another)")
    return org


def find_or_create_project(atlas, org_id, project_name):
    projects = atlas.get(f"/api/atlas/v2/groups?orgId={org_id}").get("results", [])
    for p in projects:
        if p["name"] == project_name:
            print(f"  Reusing existing project: {p['name']} ({p['id']})")
            return p, False
    project = atlas.post("/api/atlas/v2/groups", {"name": project_name, "orgId": org_id})
    print(f"  Created project: {project['name']} ({project['id']})")
    return project, True


def find_or_create_cluster(atlas, project_id, cluster_name, provider, region, instance_size):
    try:
        cluster = atlas.get(f"/api/atlas/v2/groups/{project_id}/clusters/{cluster_name}")
        print(f"  Reusing existing cluster: {cluster['name']} (state: {cluster.get('stateName')})")
        return cluster, False
    except AtlasApiError as e:
        if e.status != 404:
            raise

    body = {
        "name": cluster_name,
        "clusterType": "REPLICASET",
        "replicationSpecs": [{
            "regionConfigs": [{
                "providerName": "TENANT",
                "backingProviderName": provider,
                "regionName": region,
                "priority": 7,
                "electableSpecs": {"instanceSize": instance_size},
            }],
        }],
    }
    cluster = atlas.post(f"/api/atlas/v2/groups/{project_id}/clusters", body)
    print(f"  Cluster creation accepted: {cluster['name']} — provisioning started.")
    print("  (The POST returning 201 does NOT mean the cluster is ready — polling next.)")
    return cluster, True


def wait_for_cluster_idle(atlas, project_id, cluster_name):
    deadline = time.time() + CLUSTER_TIMEOUT_S
    while True:
        cluster = atlas.get(f"/api/atlas/v2/groups/{project_id}/clusters/{cluster_name}")
        state = cluster.get("stateName", "UNKNOWN")
        if state == "IDLE":
            print("  Cluster is IDLE — ready for connections.")
            return cluster
        if time.time() > deadline:
            sys.exit(f"Timed out waiting for cluster to become IDLE (still {state}).")
        print(f"  Cluster state: {state} — checking again in {CLUSTER_POLL_INTERVAL_S}s...")
        time.sleep(CLUSTER_POLL_INTERVAL_S)


def ensure_database_user(atlas, project_id, username, password, db_name):
    body = {
        "databaseName": "admin",          # authentication database
        "username": username,
        "password": password,
        "roles": [{"roleName": "readWrite", "databaseName": db_name}],
    }
    try:
        atlas.post(f"/api/atlas/v2/groups/{project_id}/databaseUsers", body)
        print(f"  Created database user: {username} (readWrite on '{db_name}')")
    except AtlasApiError as e:
        if e.status == 409:
            # User exists from a previous run — rotate to the freshly generated password.
            atlas.patch(f"/api/atlas/v2/groups/{project_id}/databaseUsers/admin/{username}",
                        {"password": password})
            print(f"  Database user {username} already existed — password updated.")
        else:
            raise


def detect_public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as resp:
            return resp.read().decode().strip()
    except Exception:
        return None


def ensure_access_list_entry(atlas, project_id, cidr):
    entries = atlas.get(f"/api/atlas/v2/groups/{project_id}/accessList").get("results", [])
    for entry in entries:
        if entry.get("cidrBlock") == cidr:
            print(f"  Access list already contains {cidr}.")
            return
    atlas.post(f"/api/atlas/v2/groups/{project_id}/accessList",
               [{"cidrBlock": cidr, "comment": "end_to_end.py demo"}])
    print(f"  Added IP Access List entry: {cidr}")


def first_database_operation(srv_host, username, password, db_name, collection_name, show_secrets):
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    uri = f"mongodb+srv://{urllib.parse.quote_plus(username)}:{urllib.parse.quote_plus(password)}@{srv_host}/{db_name}?retryWrites=true&w=majority"
    display_uri = uri if show_secrets else uri.replace(password, "****")
    print(f"  Connection URI: {display_uri}")

    client = MongoClient(uri, serverSelectionTimeoutMS=15000, tls=True,
                         tlsAllowInvalidCertificates=False)
    deadline = time.time() + CONNECT_TIMEOUT_S
    while True:
        try:
            client.admin.command("ping")
            break
        except PyMongoError as e:
            if time.time() > deadline:
                sys.exit(
                    f"Could not connect after {CONNECT_TIMEOUT_S}s: {e}\n"
                    "Check the IP Access List entry and database user, then retry."
                )
            print(f"  Waiting for access list / user propagation ({type(e).__name__})...")
            time.sleep(CONNECT_RETRY_INTERVAL_S)

    collection = client[db_name][collection_name]
    doc = {
        "message": "Connected to MongoDB Atlas via delegated OAuth",
        "createdBy": "end_to_end.py",
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    result = collection.insert_one(doc)
    fetched = collection.find_one({"_id": result.inserted_id})
    fetched["_id"] = str(fetched["_id"])
    client.close()
    return fetched


def cleanup(atlas, project_id, cluster_name, username, cidr):
    print("\nCleaning up resources created by this run...")
    try:
        atlas.delete(f"/api/atlas/v2/groups/{project_id}/clusters/{cluster_name}")
        print(f"  Cluster {cluster_name} deletion initiated.")
    except AtlasApiError as e:
        print(f"  Cluster delete skipped ({e}).")
    try:
        atlas.delete(f"/api/atlas/v2/groups/{project_id}/databaseUsers/admin/{username}")
        print(f"  Database user {username} deleted.")
    except AtlasApiError as e:
        print(f"  Database user delete skipped ({e}).")
    try:
        encoded = urllib.parse.quote(cidr, safe="")
        atlas.delete(f"/api/atlas/v2/groups/{project_id}/accessList/{encoded}")
        print(f"  Access list entry {cidr} removed.")
    except AtlasApiError as e:
        print(f"  Access list delete skipped ({e}).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="End-to-end demo: provision Atlas resources with a delegated OAuth "
                    "token and perform the first database read/write."
    )
    parser.add_argument("--org-id", default=None,
                        help="Organization ID (default: first org the token can access)")
    parser.add_argument("--project-name", default="partner-connect-demo",
                        help="Project to select or create (default: partner-connect-demo)")
    parser.add_argument("--cluster-name", default="connect-demo-m0",
                        help="Cluster to select or create (default: connect-demo-m0)")
    parser.add_argument("--provider", default="AWS", choices=["AWS", "GCP", "AZURE"],
                        help="Backing cloud provider for M0 (default: AWS)")
    parser.add_argument("--region", default="US_EAST_1",
                        help="Provider region (default: US_EAST_1)")
    parser.add_argument("--instance-size", default="M0",
                        help="Atlas instance size (default: M0 free tier)")
    parser.add_argument("--db-name", default="connect_demo",
                        help="Database for the first write (default: connect_demo)")
    parser.add_argument("--collection-name", default="first_connection",
                        help="Collection to create (default: first_connection)")
    parser.add_argument("--db-username", default="partner_demo_user",
                        help="SCRAM database user to create (default: partner_demo_user)")
    parser.add_argument("--cidr", default=None,
                        help="CIDR to allow in the IP Access List "
                             "(default: this machine's detected public IP /32)")
    parser.add_argument("--allow-all-ips", action="store_true",
                        help="Allow 0.0.0.0/0 in the access list — DEMO ONLY, never do "
                             "this for real users")
    parser.add_argument("--show-secrets", action="store_true",
                        help="Print the full connection URI including the password")
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete cluster, database user, and access list entry after "
                             "a successful run")
    args = parser.parse_args()

    if args.allow_all_ips:
        cidr = "0.0.0.0/0"
    elif args.cidr:
        cidr = args.cidr
    else:
        ip = detect_public_ip()
        if not ip:
            sys.exit("Could not detect this machine's public IP. Pass --cidr <ip>/32.")
        cidr = f"{ip}/32"

    db_password = secrets.token_urlsafe(24)
    total = 9

    print("=" * 64)
    print("Connect MongoDB Atlas — end-to-end demo")
    print("=" * 64)

    step(1, total, "Authenticate with the delegated OAuth token")
    env = load_env()
    token = get_access_token(env)
    atlas = AtlasClient(get_api_base(env), token)
    print("  Delegated access token is valid.")

    step(2, total, "Select the Atlas organization")
    org = pick_organization(atlas, args.org_id)

    step(3, total, "Select or create the project")
    project, _ = find_or_create_project(atlas, org["id"], args.project_name)
    project_id = project["id"]

    step(4, total, f"Select or create the {args.instance_size} cluster")
    find_or_create_cluster(atlas, project_id, args.cluster_name,
                           args.provider, args.region, args.instance_size)

    step(5, total, "Wait for the cluster to become IDLE")
    cluster = wait_for_cluster_idle(atlas, project_id, args.cluster_name)

    step(6, total, "Create the database user")
    ensure_database_user(atlas, project_id, args.db_username, db_password, args.db_name)

    step(7, total, "Configure network access (IP Access List)")
    ensure_access_list_entry(atlas, project_id, cidr)

    step(8, total, "Retrieve the connection string")
    srv = (cluster.get("connectionStrings") or {}).get("standardSrv")
    if not srv:
        sys.exit("Cluster response has no connectionStrings.standardSrv yet — re-run.")
    srv_host = srv.replace("mongodb+srv://", "")
    print(f"  SRV host: {srv_host}")

    step(9, total, "First database operation (connect, create collection, insert, read)")
    fetched = first_database_operation(srv_host, args.db_username, db_password,
                                       args.db_name, args.collection_name,
                                       args.show_secrets)

    print("\n" + "=" * 64)
    print("SUCCESS — first successful outcome reached.")
    print("=" * 64)
    print("Document written and read back from Atlas:")
    print(json.dumps(fetched, indent=2))
    print()
    print("In your product, this is the moment to show:")
    print(f'  "Connected to MongoDB Atlas — cluster {args.cluster_name} is ready."')
    if not args.cleanup:
        print()
        print("Resources left running (M0 is free). Tear down with:")
        print(f"  python3 end_to_end.py --project-name {args.project_name} "
              f"--cluster-name {args.cluster_name} --cleanup")

    if args.cleanup:
        cleanup(atlas, project_id, args.cluster_name, args.db_username, cidr)


if __name__ == "__main__":
    main()
