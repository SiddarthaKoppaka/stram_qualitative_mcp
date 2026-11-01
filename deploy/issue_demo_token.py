"""Issue a short-lived token for the loopback demonstration. It is not for staging.

Run with any Python that has PyJWT and cryptography:

    python issue_demo_token.py KEY_DIR [--jwks-out PATH]

The private key stays in KEY_DIR with mode 0600. Only the public JWKS is given to the service.
The token goes to KEY_DIR/token with mode 0600 and is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ENDPOINT = "http://127.0.0.1:8801"
KEY_ID = "stram-qual-demo"
LIFETIME_SECONDS = 3600
SCOPES = "qual:discover qual:read qual:text qual:analytics"


def _write_private(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


def _private_key(path: Path) -> rsa.RSAPrivateKey:
    if not path.exists():
        created = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        _write_private(
            path,
            created.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        )
    loaded = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(loaded, rsa.RSAPrivateKey):
        raise SystemExit("demo key is not RSA")
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("key_dir", type=Path)
    parser.add_argument("--jwks-out", type=Path)
    args = parser.parse_args()
    args.key_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = _private_key(args.key_dir / "signing-key.pem")
    if args.jwks_out:
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        public.update({"kid": KEY_ID, "use": "sig", "alg": "RS256"})
        args.jwks_out.write_text(json.dumps({"keys": [public]}) + "\n")
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": f"{ENDPOINT}/issuer",
            "aud": f"{ENDPOINT}/mcp",
            "sub": "stream-owner",
            "client_id": "qual-demo",
            "tenant_id": "stram",
            "scope": SCOPES,
            "iat": now - 1,
            "exp": now + LIFETIME_SECONDS,
        },
        key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
    _write_private(args.key_dir / "token", token.encode())
    print(f"token written, valid for {LIFETIME_SECONDS // 60} minutes")


if __name__ == "__main__":
    main()
