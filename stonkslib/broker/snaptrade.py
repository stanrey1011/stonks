"""
SnapTrade REST client (hand-rolled, signed) — read-only brokerage aggregation.

Why hand-rolled instead of the official SDK: `snaptrade-python-sdk` fails to
import on Python 3.13 (uses `typing.Type[typing_extensions.TypedDict]`), and older
versions downgrade typing-extensions/urllib3 and conflict with Streamlit in the
shared venv. This module depends only on `requests`.

Set in .env:
    SNAPTRADE_CLIENT_ID=...
    SNAPTRADE_CONSUMER_KEY=...      # the secret; never commit

Per-user credentials (userId + userSecret) are created by register_user() and
persisted to data/snaptrade_user.json (gitignored, chmod 600). The userSecret is
shown by SnapTrade only once at registration, so it must be stored.

Request signing (matches SnapTrade SDK exactly): HMAC-SHA256 with the consumer key
over a compact, sorted-keys JSON of {content, path, query}, base64-encoded, sent in
the `Signature` header. Every request also carries clientId + timestamp query params.
"""
import os
import time
import json
import hmac
import hashlib
import stat
from base64 import b64encode
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

_CLIENT_ID    = os.getenv("SNAPTRADE_CLIENT_ID", "")
_CONSUMER_KEY = os.getenv("SNAPTRADE_CONSUMER_KEY", "")
_BASE         = "https://api.snaptrade.com/api/v1"
_USER_FILE    = _ROOT / "data" / "snaptrade_user.json"
_DEFAULT_USER_ID = "stonks-local"


def is_configured() -> bool:
    return bool(_CLIENT_ID and _CONSUMER_KEY)


def is_registered() -> bool:
    """True if user credentials are available (env vars or credential file)."""
    return _load_user() is not None


# ── signed request plumbing ─────────────────────────────────────────────────────

def _sign(subpath: str, query: str, body) -> str:
    sig_object = {
        "content": None if body is None or body == {} else body,
        "path": "/api/v1" + subpath,
        "query": query,
    }
    sig_content = json.dumps(sig_object, separators=(",", ":"), sort_keys=True)
    digest = hmac.new(_CONSUMER_KEY.encode(), sig_content.encode(), hashlib.sha256).digest()
    return b64encode(digest).decode()


def _request(method: str, subpath: str, query: dict | None = None, body=None):
    if not is_configured():
        raise RuntimeError(
            "SnapTrade not configured — set SNAPTRADE_CLIENT_ID and "
            "SNAPTRADE_CONSUMER_KEY in .env"
        )
    params = {"clientId": _CLIENT_ID, "timestamp": str(int(time.time()))}
    if query:
        params.update(query)
    # The signed query string must byte-match what is sent; quote values consistently.
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    url = f"{_BASE}{subpath}?{qs}"
    headers = {"Signature": _sign(subpath, qs, body), "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":"), sort_keys=True)
        headers["Content-Type"] = "application/json"
    r = requests.request(method, url, headers=headers, data=data, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(
            f"SnapTrade {method} {subpath} -> HTTP {r.status_code}: {r.text[:300]}"
        )
    return r.json() if r.text else None


# ── per-user credential persistence ─────────────────────────────────────────────

def _load_user() -> dict | None:
    # Env vars take precedence — lets credentials travel with .env across environments.
    uid = os.getenv("SNAPTRADE_USER_ID", "")
    secret = os.getenv("SNAPTRADE_USER_SECRET", "")
    if uid and secret:
        return {"userId": uid, "userSecret": secret}
    if not _USER_FILE.exists():
        return None
    try:
        with open(_USER_FILE) as f:
            data = json.load(f)
        if data.get("userId") and data.get("userSecret"):
            return data
    except Exception:
        pass
    return None


def _save_user(user_id: str, user_secret: str) -> None:
    _USER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_USER_FILE, "w") as f:
        json.dump({"userId": user_id, "userSecret": user_secret}, f)
    os.chmod(_USER_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 600


def register_user(user_id: str = _DEFAULT_USER_ID) -> dict:
    """Register a SnapTrade user and persist the returned secret. Idempotent-ish:
    if a user is already saved, returns it without re-registering."""
    existing = _load_user()
    if existing:
        return existing
    resp = _request("POST", "/snapTrade/registerUser", body={"userId": user_id})
    user_secret = resp["userSecret"]
    _save_user(resp["userId"], user_secret)
    return {"userId": resp["userId"], "userSecret": user_secret}


def is_connected() -> bool:
    """True if a user is registered and has at least one linked account."""
    if not is_configured() or _load_user() is None:
        return False
    try:
        return len(list_accounts()) > 0
    except Exception:
        return False


# ── connection portal ───────────────────────────────────────────────────────────

def connection_portal_url(connection_type: str = "read", broker: str | None = None,
                          custom_redirect: str | None = None) -> str:
    """Return a SnapTrade Connection Portal URL (expires in ~5 min). The user opens
    it, logs into their brokerage, and authorizes access. connection_type 'read'
    requests read-only access."""
    user = register_user()
    body: dict = {}
    if broker:
        body["broker"] = broker
    if custom_redirect:
        body["customRedirect"] = custom_redirect
    resp = _request(
        "POST", "/snapTrade/login",
        query={"userId": user["userId"], "userSecret": user["userSecret"],
               "connectionType": connection_type},
        body=body or None,
    )
    # Response is either a string URL or {"redirectURI": "..."}.
    if isinstance(resp, str):
        return resp
    return resp.get("redirectURI") or resp.get("redirect_uri") or str(resp)


# ── account data ─────────────────────────────────────────────────────────────────

def _user_query() -> dict:
    user = _load_user()
    if user is None:
        raise RuntimeError("No SnapTrade user registered yet — run register_user()")
    return {"userId": user["userId"], "userSecret": user["userSecret"]}


def list_accounts() -> list[dict]:
    return _request("GET", "/accounts", query=_user_query()) or []


def find_accounts(institution_substr: str) -> list[dict]:
    """Accounts whose institution name contains the substring (case-insensitive)."""
    sub = institution_substr.lower()
    return [a for a in list_accounts()
            if sub in str(a.get("institution_name", "")).lower()]


def account_positions(account_id: str) -> list[dict]:
    return _request("GET", f"/accounts/{account_id}/positions", query=_user_query()) or []


def account_options(account_id: str) -> list[dict]:
    """Option holdings for an account. SnapTrade returns either a bare list or an
    object wrapping it under `option_positions`/`positions` depending on the
    brokerage integration — normalize to a list."""
    resp = _request("GET", f"/accounts/{account_id}/options", query=_user_query())
    if isinstance(resp, dict):
        return resp.get("option_positions") or resp.get("positions") or []
    return resp or []


def account_balances(account_id: str) -> list[dict]:
    return _request("GET", f"/accounts/{account_id}/balances", query=_user_query()) or []


def account_orders(account_id: str) -> list[dict]:
    return _request("GET", f"/accounts/{account_id}/orders", query=_user_query()) or []


def account_return_rates(account_id: str):
    """Performance/return rates for an account. Brokerage-dependent — Robinhood may
    not support it. Returns whatever SnapTrade sends (dict or list) for inspection."""
    return _request("GET", f"/accounts/{account_id}/returnRates", query=_user_query())


def account_activities(account_id: str) -> list[dict]:
    """Transactions/activities (dividends, deposits, trades). Robinhood syncs
    holdings only, so this is typically empty. Normalizes the list/wrapped shapes."""
    resp = _request("GET", f"/accounts/{account_id}/activities", query=_user_query())
    if isinstance(resp, dict):
        return resp.get("data") or resp.get("activities") or []
    return resp or []
