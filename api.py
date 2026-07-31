"""
Atlas OAuth Demo — FastAPI proxy server

Reads the access token from .token_store.json (written by get_token.py) and
proxies requests to the Atlas Admin API.

Start:
    source oauthdemo/.venv/bin/activate
    uvicorn oauthdemo.api:app --reload --port 8080

Or from inside the oauthdemo/ directory:
    source .venv/bin/activate
    uvicorn api:app --reload --port 8080
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
TOKEN_STORE  = os.path.join(SCRIPT_DIR, ".token_store.json")
ENV_FILE     = os.path.join(SCRIPT_DIR, ".env")

ATLAS_VERSION = "application/vnd.atlas.2025-03-12+json"


def load_env() -> dict:
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


def get_api_base() -> str:
    env = load_env()
    cloud_base = env.get("CLOUD_BASE", "https://cloud-dev.mongodb.com")
    return (
        cloud_base
        .replace("cloud-dev.", "api-dev.")
        .replace("cloud-stage.", "api-stage.")
        .replace("//cloud.", "//api.")
    )


def get_access_token() -> str:
    if not os.path.exists(TOKEN_STORE):
        raise HTTPException(
            status_code=401,
            detail="No token store found. Run `python3 get_token.py` first to authenticate.",
        )
    try:
        with open(TOKEN_STORE) as f:
            store = json.load(f)
    except (json.JSONDecodeError, OSError):
        raise HTTPException(status_code=500, detail="Token store is corrupted.")

    token = store.get("access_token")
    if not token:
        raise HTTPException(
            status_code=401,
            detail="No access token in store. Run `python3 get_token.py` to refresh.",
        )

    import time
    expires_at = store.get("expires_at", 0)
    if expires_at and time.time() > expires_at:
        raise HTTPException(
            status_code=401,
            detail=f"Access token expired. Re-run `python3 get_token.py` to get a new one.",
        )

    return token


def atlas_request(method: str, path: str, body: dict = None):
    """Make a request to the Atlas Admin API using the stored access token."""
    token    = get_access_token()
    api_base = get_api_base()
    url      = f"{api_base}{path}"

    payload = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": ATLAS_VERSION,
    }
    if payload:
        headers["Content-Type"] = ATLAS_VERSION

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = {"message": raw}
        raise HTTPException(status_code=e.code, detail=detail)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None


class CreateProjectRequest(BaseModel):
    name: str
    org_id: str


class CreateClusterRequest(BaseModel):
    name: str
    provider: Optional[str] = "AWS"
    region: Optional[str] = "US_EAST_1"
    instance_size: Optional[str] = "M0"


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Atlas OAuth Demo API",
    description="FastAPI proxy for the MongoDB Atlas Admin API using delegated OAuth tokens.",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------

@app.get("/orgs", summary="List Organizations")
def list_orgs(name: Optional[str] = Query(default=None, description="Filter by org name")):
    """
    List all Atlas Organizations accessible with the current access token.
    Optionally filter by name using the `?name=` query parameter.
    """
    path = f"/api/atlas/v2/orgs?name={urllib.parse.quote(name)}" if name else "/api/atlas/v2/orgs"
    status, data = atlas_request("GET", path)
    return JSONResponse(status_code=status, content=data)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@app.get("/orgs/{org_id}/projects", summary="List Projects in an Organization")
def list_projects(org_id: str):
    """List all projects (groups) in a given Organization."""
    status, data = atlas_request("GET", f"/api/atlas/v2/groups?orgId={org_id}")
    return JSONResponse(status_code=status, content=data)


@app.post("/projects", summary="Create a Project", status_code=201)
def create_project(body: CreateProjectRequest):
    """
    Create a new Atlas project inside the specified Organization.

    - **name**: Name of the new project
    - **org_id**: Organization ID the project belongs to
    """
    status, data = atlas_request("POST", "/api/atlas/v2/groups", {
        "name": body.name,
        "orgId": body.org_id,
    })
    return JSONResponse(status_code=status, content=data)


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------

@app.get("/projects/{project_id}/clusters", summary="List Clusters in a Project")
def list_clusters(project_id: str):
    """List all clusters in a given project."""
    status, data = atlas_request("GET", f"/api/atlas/v2/groups/{project_id}/clusters")
    return JSONResponse(status_code=status, content=data)


@app.post("/projects/{project_id}/clusters", summary="Create a Cluster", status_code=201)
def create_cluster(project_id: str, body: CreateClusterRequest):
    """
    Create a new Atlas cluster in the specified project.

    - **name**: Cluster name
    - **provider**: Cloud provider — `AWS`, `GCP`, or `AZURE` (default: `AWS`)
    - **region**: Provider region (default: `US_EAST_1`)
    - **instance_size**: Atlas instance size (default: `M0` free tier)
    """
    status, data = atlas_request("POST", f"/api/atlas/v2/groups/{project_id}/clusters", {
        "name": body.name,
        "clusterType": "REPLICASET",
        "replicationSpecs": [{
            "regionConfigs": [{
                "providerName": "TENANT",
                "backingProviderName": body.provider,
                "regionName": body.region,
                "priority": 7,
                "electableSpecs": {
                    "instanceSize": body.instance_size,
                },
            }],
        }],
    })
    return JSONResponse(status_code=status, content=data)


@app.get("/projects/{project_id}/clusters/{cluster_name}", summary="Get Cluster Status")
def get_cluster(project_id: str, cluster_name: str):
    """Get the current status and configuration of a specific cluster."""
    status, data = atlas_request("GET", f"/api/atlas/v2/groups/{project_id}/clusters/{cluster_name}")
    return JSONResponse(status_code=status, content=data)


@app.delete("/projects/{project_id}/clusters/{cluster_name}", summary="Delete a Cluster")
def delete_cluster(project_id: str, cluster_name: str):
    """Terminate and permanently delete a cluster. This action is irreversible."""
    status, data = atlas_request("DELETE", f"/api/atlas/v2/groups/{project_id}/clusters/{cluster_name}")
    return JSONResponse(status_code=200, content=data or {"message": "Cluster deletion initiated."})


# ---------------------------------------------------------------------------
# Token — Refresh
# ---------------------------------------------------------------------------

@app.post("/auth/refresh", summary="Refresh Access Token")
def refresh_token(body: RefreshTokenRequest = RefreshTokenRequest()):
    """
    Exchange a refresh token for a new access token and update the token store.

    - If `refresh_token` is provided in the request body it is used directly.
    - If omitted the stored refresh token from `.token_store.json` is used.

    Returns an error if this client does not support the refresh_token grant
    (e.g. the Partner Test SPA has `maximum_refresh_token_lifetime: -1`).
    """
    env = load_env()
    oauth_base = env.get("OAUTH_BASE", "https://authorize-dev.mongodb.com")
    client_id  = env.get("CLIENT_ID",  "")
    client_secret = env.get("CLIENT_SECRET") or None

    # Resolve which refresh token to use
    refresh_token_value = body.refresh_token
    if not refresh_token_value:
        if not os.path.exists(TOKEN_STORE):
            raise HTTPException(
                status_code=401,
                detail="No token store found. Run `python3 get_token.py` first.",
            )
        try:
            store = json.load(open(TOKEN_STORE))
        except (json.JSONDecodeError, OSError):
            raise HTTPException(status_code=500, detail="Token store is corrupted.")

        refresh_token_value = store.get("refresh_token")
        if not refresh_token_value:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No refresh token available. This client is registered with "
                    "grant_types=[authorization_code] only and "
                    "maximum_refresh_token_lifetime=-1, so the server does not issue "
                    "refresh tokens. Re-run `python3 get_token.py` for a fresh browser login."
                ),
            )

    # Build POST body
    params = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_value,
        "client_id": client_id,
    }
    data = urllib.parse.urlencode(params).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    if client_secret:
        import base64
        raw = f"{client_id}:{client_secret}"
        headers["Authorization"] = "Basic " + base64.b64encode(raw.encode()).decode()
        params.pop("client_id")
        data = urllib.parse.urlencode(params).encode()

    req = urllib.request.Request(
        f"{oauth_base}/tokens",
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = {"message": raw}
        raise HTTPException(status_code=e.code, detail=detail)

    # Persist updated tokens to store
    store = {}
    if os.path.exists(TOKEN_STORE):
        try:
            store = json.load(open(TOKEN_STORE))
        except (json.JSONDecodeError, OSError):
            store = {}

    store["access_token"]  = token_data.get("access_token", store.get("access_token"))
    store["token_type"]    = token_data.get("token_type", "Bearer")
    store["expires_at"]    = int(time.time()) + int(token_data.get("expires_in", 600))
    if "refresh_token" in token_data:
        store["refresh_token"] = token_data["refresh_token"]

    with open(TOKEN_STORE, "w") as f:
        json.dump(store, f, indent=2)

    return {
        "access_token":  store["access_token"],
        "token_type":    store["token_type"],
        "expires_in":    token_data.get("expires_in"),
        "refresh_token": store.get("refresh_token"),
        "token_store":   TOKEN_STORE,
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health Check", include_in_schema=False)
def health():
    """Returns token store status without making an Atlas API call."""
    if not os.path.exists(TOKEN_STORE):
        return {"status": "unauthenticated", "message": "No token store found."}
    try:
        store = json.load(open(TOKEN_STORE))
        expires_at = store.get("expires_at", 0)
        remaining  = max(0, int(expires_at - time.time()))
        return {
            "status":                  "ok" if remaining > 0 else "expired",
            "token_expires_in_seconds": remaining,
            "has_refresh_token":        "refresh_token" in store,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
