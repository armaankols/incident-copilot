"""Bound requests before FastAPI parses them; preserve the raw socket peer."""
import asyncio
import hashlib
import ipaddress
import os

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.access import require_access

MAX_BODY_BYTES = 8192
REQUESTS_PER_MINUTE = 240
GLOBAL_REQUESTS_PER_MINUTE = 1200
ACCESS_REQUESTS_PER_MINUTE = 20


def client_ip(request):
    peer = request.scope.get("socket_peer", request.scope.get("client"))
    host = peer[0] if peer else "unknown"
    # Explicit peer allowlist, not an environment switch alone. Uvicorn must
    # not rewrite the socket peer from X-Forwarded-For.
    if os.getenv("TRUST_FLY_PROXY") == "1" and os.getenv("FLY_APP_NAME"):
        try:
            address = ipaddress.ip_address(host)
            trusted = any(address in ipaddress.ip_network(cidr.strip())
                          for cidr in os.getenv("TRUSTED_PROXY_CIDRS", "").split(",") if cidr.strip())
            values = request.headers.getlist("fly-client-ip")
            if trusted and len(values) == 1:
                return str(ipaddress.ip_address(values[0]))
        except ValueError:
            pass
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return host


def visitor_id(request):
    return hashlib.sha256(client_ip(request).encode()).hexdigest()


class RequestGuard:
    def __init__(self, app, ledger_factory):
        self.app = app
        self.ledger_factory = ledger_factory

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        scope["socket_peer"] = scope.get("client")
        request = Request(scope)
        path = scope["path"]

        async def reject(status, detail, headers=None):
            response = JSONResponse({"detail": detail}, status_code=status,
                                    headers={"Cache-Control": "no-store", **(headers or {})})
            await response(scope, receive, send)

        length = request.headers.get("content-length")
        if length is not None:
            try:
                if int(length) < 0:
                    raise ValueError
                if int(length) > MAX_BODY_BYTES:
                    return await reject(413, "Request body is too large")
            except ValueError:
                return await reject(400, "Invalid Content-Length")

        def throttle():
            visitor = visitor_id(request)
            # Public traffic must not exhaust the readiness probe's allowance.
            # The health route keeps its own per-visitor quota, not the public
            # global/visitor buckets. Body and connection limits still apply.
            if path == "/healthz" and scope["method"] in ("GET", "HEAD"):
                return self.ledger_factory().allow_request([("health:" + visitor, REQUESTS_PER_MINUTE)])
            buckets = [("all", GLOBAL_REQUESTS_PER_MINUTE),
                       ("visitor:" + visitor, REQUESTS_PER_MINUTE)]
            if path == "/api/access":
                buckets.append(("access:" + visitor, ACCESS_REQUESTS_PER_MINUTE))
            return self.ledger_factory().allow_request(buckets)

        retry_after = await asyncio.to_thread(throttle)
        if retry_after:
            return await reject(429, "Request rate limit reached", {"Retry-After": str(retry_after)})

        if scope["method"] == "POST" and path in ("/api/runs", "/api/investigate"):
            try:
                require_access(request)
            except HTTPException as error:
                return await reject(error.status_code, error.detail)

        body = bytearray()
        deadline = asyncio.get_running_loop().time() + 10
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=max(0, deadline - asyncio.get_running_loop().time()))
            except TimeoutError:
                return await reject(408, "Request body timed out")
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                return await reject(413, "Request body is too large")
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
