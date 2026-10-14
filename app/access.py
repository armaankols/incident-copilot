"""Link-based access to paid investigations; read-only demo routes stay public."""
import hashlib
import hmac
import os
import re
import secrets
import time
from urllib.parse import urlsplit

from fastapi import HTTPException

COOKIE = "copilot_access"
SESSION_SECONDS = 2 * 60 * 60


def access_key():
    token = os.getenv("DEMO_ACCESS_TOKEN", "")
    return hashlib.sha256(token.encode()).digest() if len(token) >= 32 else None


def check_origin(request):
    origin = request.headers.get("origin")
    if origin is None:
        return
    try:
        parsed = urlsplit(origin)
    except ValueError as error:
        raise HTTPException(403, "Request origin is not allowed") from error
    local = request.url.hostname in ("localhost", "127.0.0.1", "::1")
    if (parsed.netloc.lower() != request.url.netloc.lower()
            or parsed.scheme not in (("http", "https") if local else ("https",))
            or parsed.path or parsed.query or parsed.fragment):
        raise HTTPException(403, "Request origin is not allowed")


def sign(payload, key):
    return hmac.new(key, ("copilot-access-v1|" + payload).encode(), hashlib.sha256).hexdigest()


def make_session():
    key = access_key()
    if key is None:
        raise HTTPException(503, "Agent access is not configured")
    payload = f"{int(time.time()) + SESSION_SECONDS}.{secrets.token_hex(16)}"
    return f"{payload}.{sign(payload, key)}"


def has_access(request):
    key = access_key()
    cookie = request.cookies.get(COOKIE, "")
    if key is None or len(cookie) > 160:
        return False
    match = re.fullmatch(r"([0-9]{1,12})\.([0-9a-f]{32})\.([0-9a-f]{64})", cookie)
    if match is None:
        return False
    expiry, nonce, signature = match.groups()
    expires = int(expiry)
    now = int(time.time())
    return (now < expires <= now + SESSION_SECONDS and len(nonce) == 32
            and hmac.compare_digest(signature, sign(f"{expiry}.{nonce}", key)))


def require_access(request):
    check_origin(request)
    if not has_access(request):
        raise HTTPException(401, "Agent access required")


def valid_link_token(token):
    key = access_key()
    return key is not None and len(token) <= 256 and hmac.compare_digest(
        hashlib.sha256(token.encode()).digest(), key)


def valid_sonnet_passcode(passcode):
    expected = os.getenv("SONNET_PASSCODE", "")
    if not expected or len(expected) > 256:
        return False
    key = hashlib.sha256(expected.encode()).digest()
    public_key = access_key()
    # The portfolio link is public; it cannot also be the owner's password.
    if public_key is not None and hmac.compare_digest(key, public_key):
        return False
    return hmac.compare_digest(hashlib.sha256(passcode.encode()).digest(), key)
