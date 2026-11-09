"""Make a short-lived App Store Connect API token (ES256 JWT).

Uses openssl for signing so no extra Python packages are needed.

    python3 asc_jwt.py <key.p8> <key_id> <issuer_id>
"""
import base64
import json
import subprocess
import sys
import time


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _der_to_raw(der: bytes) -> bytes:
    """openssl writes a DER ECDSA signature; JWT wants the raw 64-byte r||s."""
    i, out = 2, b""
    for _ in range(2):
        assert der[i] == 2, "unexpected DER signature"
        n = der[i + 1]
        out += der[i + 2:i + 2 + n].lstrip(b"\x00").rjust(32, b"\x00")
        i += 2 + n
    return out


def make_token(key_file: str, key_id: str, issuer_id: str, ttl: int = 900) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "ES256", "kid": key_id, "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"iss": issuer_id, "iat": now, "exp": now + ttl,
                               "aud": "appstoreconnect-v1"}).encode())
    signing_input = f"{header}.{payload}".encode()
    der = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key_file],
                         input=signing_input, capture_output=True, check=True).stdout
    return f"{header}.{payload}.{_b64(_der_to_raw(der))}"


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    print(make_token(*sys.argv[1:]))
