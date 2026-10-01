"""Login for the web UI and API keys for the REST API.

Configure with environment variables (put them in .env):
  LEGALEASE_REQUIRE_LOGIN=1     refuse anonymous use (set this in production)
  LEGALEASE_USERS=alice=<hash>,bob=<hash>      web logins; make a hash with:  python auth.py hash-password
  LEGALEASE_API_KEYS=<key>=alice,<key>=bob     API keys;   make one with:     python auth.py new-api-key alice

With neither set (and REQUIRE_LOGIN off) the app runs in open "local" mode for development.

For a public deployment prefer real sign-in (Streamlit's st.login with Google/Microsoft OIDC, >= 1.42, or an
auth proxy such as Cloudflare Access) over a shared password list - this module is the simple built-in option.
"""
import hashlib
import hmac
import os
import secrets
import sys

LOCAL_USER = "local"


def _truthy(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------ passwords (scrypt, salted)
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _pairs(env_name: str) -> dict[str, str]:
    out = {}
    for item in os.getenv(env_name, "").split(","):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


def load_users() -> dict[str, str]:
    return _pairs("LEGALEASE_USERS")


def login_required() -> bool:
    return _truthy(os.getenv("LEGALEASE_REQUIRE_LOGIN", "")) or bool(load_users())


_DUMMY = hash_password("not-a-real-password")


def authenticate(username: str, password: str) -> bool:
    """Constant-ish time check; an unknown user costs the same as a wrong password."""
    stored = load_users().get(username.strip())
    ok = verify_password(password, stored or _DUMMY)
    return bool(stored) and ok


# ------------------------------------------------------------------ API keys
def api_user(key: str | None) -> str:
    """Owner name for an API key. Raises PermissionError when a key is required but missing/wrong."""
    keys = _pairs("LEGALEASE_API_KEYS")
    if not keys:
        if login_required():
            raise PermissionError("The server requires login but no API keys are configured (LEGALEASE_API_KEYS).")
        return LOCAL_USER
    for known, owner in keys.items():     # compare against every key so timing does not reveal which matched
        if key and hmac.compare_digest(known, key):
            return owner
    raise PermissionError("Missing or invalid API key.")


if __name__ == "__main__":
    import getpass
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "hash-password":
        name = input("username: ").strip()
        print(f"\nAdd to LEGALEASE_USERS (comma-separated):\n{name}={hash_password(getpass.getpass('password: '))}")
    elif cmd == "new-api-key":
        print(f"\nAdd to LEGALEASE_API_KEYS (comma-separated):\n{secrets.token_urlsafe(32)}={sys.argv[2] if len(sys.argv) > 2 else 'user'}")
    else:
        print(__doc__)
