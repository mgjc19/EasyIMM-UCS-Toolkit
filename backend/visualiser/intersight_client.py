"""
Cisco Intersight REST API client with HTTP Signature authentication.
Supports both v2 (RSA) and v3 (ECDSA) API keys.
"""

import hashlib
import base64
import datetime
import logging
import urllib.parse
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding

logger = logging.getLogger(__name__)


class IntersightAuthError(Exception):
    pass


class IntersightAPIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Intersight API {status_code}: {detail}")


class IntersightClient:
    """Lightweight async client for the Cisco Intersight REST API."""

    def __init__(
        self,
        api_key_id: str,
        secret_key_path: str,
        base_url: str = "https://intersight.com",
    ):
        self.api_key_id = api_key_id
        self.base_url = base_url.rstrip("/")
        self._host = urllib.parse.urlparse(self.base_url).hostname
        self._private_key = self._load_key(secret_key_path)
        self._is_ec = isinstance(self._private_key, ec.EllipticCurvePrivateKey)
        self._client = httpx.AsyncClient(verify=True, timeout=60.0)

    @staticmethod
    def _load_key(path: str):
        key_path = Path(path).expanduser().resolve()
        if not key_path.is_file():
            raise IntersightAuthError(f"Secret key file not found: {key_path}")
        try:
            return serialization.load_pem_private_key(
                key_path.read_bytes(), password=None
            )
        except Exception as exc:
            raise IntersightAuthError(f"Failed to load PEM key: {exc}") from exc

    def _build_auth_headers(self, method: str, request_path: str, body: str = "") -> dict:
        body_bytes = body.encode("utf-8") if body else b""
        body_digest = base64.b64encode(hashlib.sha256(body_bytes).digest()).decode()

        date_str = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )

        signing_string = "\n".join([
            f"(request-target): {method.lower()} {request_path}",
            f"date: {date_str}",
            f"digest: SHA-256={body_digest}",
            f"host: {self._host}",
        ])

        if self._is_ec:
            sig = self._private_key.sign(
                signing_string.encode(), ec.ECDSA(hashes.SHA256())
            )
            algorithm = "hs2019"
        else:
            sig = self._private_key.sign(
                signing_string.encode(), padding.PKCS1v15(), hashes.SHA256()
            )
            algorithm = "rsa-sha256"

        sig_b64 = base64.b64encode(sig).decode()

        return {
            "Date": date_str,
            "Digest": f"SHA-256={body_digest}",
            "Content-Type": "application/json",
            "Host": self._host,
            "Authorization": (
                f'Signature keyId="{self.api_key_id}",'
                f'algorithm="{algorithm}",'
                f'headers="(request-target) date digest host",'
                f'signature="{sig_b64}"'
            ),
        }

    def _build_query_string(self, params: dict | None) -> str:
        if not params:
            return ""
        parts = []
        for k, v in params.items():
            if v is None:
                continue
            parts.append(f"{k}={v}")
        return "&".join(parts)

    async def get(self, resource_path: str, params: dict | None = None) -> dict:
        api_path = f"/api/v1/{resource_path}"
        qs = self._build_query_string(params)
        full_path = f"{api_path}?{qs}" if qs else api_path

        headers = self._build_auth_headers("GET", full_path)
        url = f"{self.base_url}{full_path}"

        logger.debug("GET %s", url)
        resp = await self._client.get(url, headers=headers)

        if resp.status_code == 401:
            raise IntersightAuthError("Authentication failed — check API key and secret key")
        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise IntersightAPIError(resp.status_code, detail)

        return resp.json()

    async def get_all(
        self,
        resource_path: str,
        params: dict | None = None,
        page_size: int = 100,
        max_pages: int = 50,
    ) -> list:
        """Paginated GET that fetches all results."""
        all_results: list = []
        skip = 0

        for _ in range(max_pages):
            p = dict(params or {})
            p["$top"] = str(page_size)
            p["$skip"] = str(skip)

            data = await self.get(resource_path, p)
            page = data.get("Results") or []
            all_results.extend(page)

            if len(page) < page_size:
                break
            skip += page_size

        return all_results

    async def get_by_moid(
        self, resource_path: str, moid: str, params: dict | None = None
    ) -> dict:
        return await self.get(f"{resource_path}/{moid}", params)

    async def test_connection(self) -> dict:
        """Verify credentials by querying the IAM account."""
        data = await self.get("iam/Accounts", {"$select": "Name,Moid", "$top": "1"})
        results = data.get("Results", [])
        name = results[0].get("Name", "Unknown") if results else "Unknown"
        return {"status": "connected", "account_name": name}

    async def close(self):
        await self._client.aclose()
