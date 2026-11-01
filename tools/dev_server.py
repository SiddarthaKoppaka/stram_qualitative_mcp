"""Run the service locally on the synthetic news lake, with a throwaway identity.

    uv run python tools/dev_server.py

It creates `.local/` (ignored by Git), serves a public key on loopback, writes a one-hour token to
`.local/token`, and starts the real server. Nothing here is suitable for a shared environment.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from stram_qualitative_mcp.app import main as serve

ROOT = Path(__file__).parents[1]
LOCAL = ROOT / ".local"
KEY_ID = "local-dev"
TENANT = "local-stram"
SCOPES = "qual:discover qual:read qual:text qual:analytics"
TOKEN_SECONDS = 3600


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def _write_private(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def _serve_keys(key: rsa.RSAPrivateKey, port: int) -> None:
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update({"kid": KEY_ID, "use": "sig", "alg": "RS256"})
    directory = LOCAL / "jwks"
    directory.mkdir(exist_ok=True)
    (directory / "jwks.json").write_text(json.dumps({"keys": [public]}))
    handler = partial(QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--keys-port", type=int, default=8766)
    parser.add_argument("--parquet-root", type=Path, default=ROOT / "tests/fixtures/news/parquet")
    args = parser.parse_args()

    LOCAL.mkdir(exist_ok=True)
    audit_key = LOCAL / "audit.key"
    if not audit_key.exists():
        _write_private(audit_key, secrets.token_bytes(48).hex().encode())
    # The journal is chained to its key, so a fresh run keeps both or neither.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _serve_keys(key, args.keys_port)

    issuer = f"http://127.0.0.1:{args.keys_port}/issuer"
    endpoint = f"http://127.0.0.1:{args.port}"
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": f"{endpoint}/mcp",
            "sub": "local-developer",
            "client_id": "local-dev",
            "tenant_id": TENANT,
            "scope": SCOPES,
            "iat": now - 1,
            "exp": now + TOKEN_SECONDS,
        },
        key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
    _write_private(LOCAL / "token", token.encode())

    os.environ.update(
        {
            "STRAM_QUAL_MCP_PARQUET_ROOT": str(args.parquet_root.resolve()),
            "STRAM_QUAL_MCP_AUDIT_DB": str(LOCAL / "audit.sqlite3"),
            "STRAM_QUAL_MCP_AUDIT_KEY_FILE": str(audit_key),
            "STRAM_QUAL_MCP_ISSUER_URL": issuer,
            "STRAM_QUAL_MCP_RESOURCE_URL": f"{endpoint}/mcp",
            "STRAM_QUAL_MCP_JWKS_URL": f"http://127.0.0.1:{args.keys_port}/jwks.json",
            "STRAM_QUAL_MCP_TENANT_ID": TENANT,
            "STRAM_QUAL_MCP_ALLOWED_HOSTS": f"127.0.0.1:{args.port}",
            "STRAM_QUAL_MCP_ALLOW_INSECURE_HTTP": "1",
            "STRAM_QUAL_MCP_BIND_HOST": "127.0.0.1",
            "STRAM_QUAL_MCP_BIND_PORT": str(args.port),
        }
    )
    print(f"MCP endpoint: {endpoint}/mcp", flush=True)
    print(f"Token, valid for one hour: {LOCAL / 'token'}", flush=True)
    serve()


if __name__ == "__main__":
    main()
