import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.error
import urllib.request
import urllib.parse
import webbrowser
from urllib.parse import urlparse, parse_qs

CALLBACK_PATH = "/oauth/callback"
TOKEN_STORE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_store.json")
REDIRECT_URI = None
CODE_VERIFIER = None
CODE_CHALLENGE = None
STATE = None
received_code = threading.Event()
auth_code = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env():
    # Always resolve .env relative to this script's directory,
    # regardless of which directory the script is invoked from.
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env = {}
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key.strip()] = val.strip()
    except FileNotFoundError:
        print(f"Warning: .env not found at {env_path}, using defaults.")
    return env


def save_tokens(token_data):
    """Persist access_token, refresh_token and metadata to TOKEN_STORE."""
    store = {}
    if os.path.exists(TOKEN_STORE):
        try:
            with open(TOKEN_STORE) as f:
                store = json.load(f)
        except (json.JSONDecodeError, OSError):
            store = {}

    if "access_token" in token_data:
        store["access_token"] = token_data["access_token"]
    if "refresh_token" in token_data:
        store["refresh_token"] = token_data["refresh_token"]
    if "expires_in" in token_data:
        import time
        store["expires_at"] = int(time.time()) + int(token_data["expires_in"])
    if "token_type" in token_data:
        store["token_type"] = token_data["token_type"]

    with open(TOKEN_STORE, "w") as f:
        json.dump(store, f, indent=2)
    print(f"Tokens saved to {TOKEN_STORE}")


def load_tokens():
    """Load stored tokens. Returns dict or empty dict if not found."""
    if not os.path.exists(TOKEN_STORE):
        return {}
    try:
        with open(TOKEN_STORE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def generate_pkce():
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def post_to_token_endpoint(oauth_base, body_params, client_secret=None):
    """
    POST to {OAUTH_BASE}/tokens.

    Public client  → client_id in body, no Authorization header.
    Confidential client → HTTP Basic auth header, client_id NOT in body.
    """
    data = urllib.parse.urlencode(body_params).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    if client_secret:
        raw = f"{body_params['client_id']}:{client_secret}"
        headers["Authorization"] = "Basic " + base64.b64encode(raw.encode()).decode()
        # client_id must not appear in body for confidential clients
        body_params_copy = {k: v for k, v in body_params.items() if k != "client_id"}
        data = urllib.parse.urlencode(body_params_copy).encode()

    req = urllib.request.Request(
        f"{oauth_base}/tokens",
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            error_json = json.loads(error_body)
        except json.JSONDecodeError:
            error_json = {"error": str(e.code), "error_description": error_body}
        return {"_http_error": e.code, **error_json}


def print_token_response(token_data):
    if "_http_error" in token_data or "error" in token_data:
        print(f"\n{'='*60}")
        print("Token request failed")
        print(f"{'='*60}")
        print(f"Error            : {token_data.get('error', 'unknown')}")
        print(f"Description      : {token_data.get('error_description', '')}")
        if "_http_error" in token_data:
            print(f"HTTP status      : {token_data['_http_error']}")
        print(f"{'='*60}")
        return

    save_tokens(token_data)

    print(f"\n{'='*60}")
    print("Token response")
    print(f"{'='*60}")
    print(f"Access Token     : {token_data.get('access_token', 'N/A')}")
    print(f"Token Type       : {token_data.get('token_type', 'N/A')}")
    print(f"Expires In       : {token_data.get('expires_in', 'N/A')} seconds")
    if "refresh_token" in token_data:
        print(f"Refresh Token    : {token_data['refresh_token']}")
    if "scope" in token_data:
        print(f"Scope            : {token_data['scope']}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Token flows
# ---------------------------------------------------------------------------

def exchange_code(client_id, oauth_base, redirect_uri, code, verifier, client_secret=None):
    """
    Authorization Code exchange (back-channel POST to /tokens).
    Used by both public clients (PKCE only) and confidential clients (Basic auth).
    """
    print("Exchanging authorization code for tokens...")
    params = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    return post_to_token_endpoint(oauth_base, params, client_secret)


def refresh_access_token(client_id, oauth_base, refresh_token, client_secret=None):
    """
    Refresh Token grant — exchange a refresh token for a new access token.
    The server may also rotate and return a new refresh token.
    """
    print("Refreshing access token using refresh token...")
    params = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    return post_to_token_endpoint(oauth_base, params, client_secret)


# ---------------------------------------------------------------------------
# Local callback server
# ---------------------------------------------------------------------------

def _extract_code(path, body=None):
    if body:
        params = parse_qs(body.decode())
    else:
        parsed = urlparse(path)
        params = parse_qs(parsed.query)
    if "code" in params:
        return params["code"][0], params.get("error", [None])[0]
    return None, params.get("error", [None])[0]


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def _handle_callback(self, body=None):
        global auth_code
        code, error = _extract_code(self.path, body)
        if code:
            auth_code = code
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authorization successful!</h1>"
                b"<p>You can close this tab and return to the terminal.</p></body></html>"
            )
            received_code.set()
        elif error:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h1>Authorization failed</h1><p>Error: {error}</p></body></html>".encode()
            )
            received_code.set()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        self._handle_callback()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None
        self._handle_callback(body)

    def log_message(self, format, *args):
        pass


def free_port(port):
    """Kill any process occupying the given port before binding."""
    import signal
    import subprocess
    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}"],
        capture_output=True, text=True
    )
    pids = result.stdout.strip().splitlines()
    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ProcessLookupError, ValueError):
            pass
    if pids:
        print(f"Freed port {port} (killed PID(s): {', '.join(pids)})")


def run_server(port):
    free_port(port)
    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(("", port), CallbackHandler)
    while not received_code.is_set():
        server.timeout = 0.5
        server.handle_request()
    server.server_close()


def build_auth_url(client_id, cloud_base, redirect_uri, resource, challenge):
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": STATE,
        "resource": resource,
    })
    return f"{cloud_base}/oauth/authorize?{params}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    env = load_env()
    default_client_id    = env.get("CLIENT_ID",     "")
    default_oauth_base   = env.get("OAUTH_BASE",    "https://authorize-dev.mongodb.com")
    default_cloud_base   = env.get("CLOUD_BASE",    "https://cloud-dev.mongodb.com")
    default_resource     = env.get("RESOURCE",      "https://api-dev.mongodb.com/api/atlas")
    default_client_secret = env.get("CLIENT_SECRET", None)

    parser = argparse.ArgumentParser(
        description="Obtain Atlas OAuth tokens via Authorization Code + PKCE or Refresh Token grant."
    )
    parser.add_argument("--client-id",      default=default_client_id,
                        help="OAuth client_id (default: from .env)")
    parser.add_argument("--client-secret",  default=default_client_secret,
                        help="Client secret — confidential clients only (default: from .env)")
    parser.add_argument("--oauth-base",     default=default_oauth_base,
                        help="Token endpoint base URL (default: from .env)")
    parser.add_argument("--cloud-base",     default=default_cloud_base,
                        help="Authorization endpoint base URL (default: from .env)")
    parser.add_argument("--resource",       default=default_resource,
                        help="Resource audience parameter (default: from .env)")
    parser.add_argument("--redirect-port",  type=int, default=3000,
                        help="Local port for the OAuth callback (default: 3000)")
    parser.add_argument("--refresh-token",  nargs="?", const="__stored__", default=None,
                        help="Exchange a refresh token for a new access token. "
                             "Pass a token value, or use the flag alone to load the stored token.")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Path 1: Refresh Token grant — no browser needed
    # ------------------------------------------------------------------
    if args.refresh_token is not None:
        refresh_token_value = args.refresh_token

        if refresh_token_value == "__stored__":
            stored = load_tokens()
            refresh_token_value = stored.get("refresh_token")
            if not refresh_token_value:
                if stored.get("access_token"):
                    print(
                        "Error: A stored access token exists but no refresh token was issued.\n"
                        "This client is registered with grant_types=[authorization_code] only\n"
                        "and maximum_refresh_token_lifetime=-1, so the server does not return\n"
                        "refresh tokens. Re-run without --refresh-token to do a fresh browser login."
                    )
                else:
                    print(
                        "Error: No token store found. Run without --refresh-token first\n"
                        "to complete the browser flow and store your tokens."
                    )
                return
            print(f"Using stored refresh token from {TOKEN_STORE}")

        token_data = refresh_access_token(
            client_id=args.client_id,
            oauth_base=args.oauth_base,
            refresh_token=refresh_token_value,
            client_secret=args.client_secret,
        )
        print_token_response(token_data)
        return

    # ------------------------------------------------------------------
    # Path 2: Authorization Code + PKCE — browser-based flow
    # ------------------------------------------------------------------
    global REDIRECT_URI, CODE_VERIFIER, CODE_CHALLENGE, STATE

    REDIRECT_URI   = f"http://localhost:{args.redirect_port}{CALLBACK_PATH}"
    CODE_VERIFIER, CODE_CHALLENGE = generate_pkce()
    STATE          = secrets.token_urlsafe(16)

    server_thread = threading.Thread(target=run_server, args=(args.redirect_port,), daemon=True)
    server_thread.start()

    auth_url = build_auth_url(args.client_id, args.cloud_base, REDIRECT_URI, args.resource, CODE_CHALLENGE)
    print(f"Opening browser for authorization...")
    print(f"Auth URL: {auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for callback (timeout: 5 min)...")
    received_code.wait(timeout=300)

    if not auth_code:
        print("Error: No authorization code received — timed out or user cancelled.")
        return

    token_data = exchange_code(
        client_id=args.client_id,
        oauth_base=args.oauth_base,
        redirect_uri=REDIRECT_URI,
        code=auth_code,
        verifier=CODE_VERIFIER,
        client_secret=args.client_secret,
    )
    print_token_response(token_data)

    # If a refresh token was returned, show how to use it
    if token_data.get("refresh_token"):
        print("\nTo refresh without the browser, run:")
        print(f"  python3 oauthdemo/get_token.py --refresh-token {token_data['refresh_token']}\n")


if __name__ == "__main__":
    main()
