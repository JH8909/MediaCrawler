# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx


TENANT_ACCESS_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)
BATCH_CREATE_URL = (
    "https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}"
    "/tables/{table_id}/records/batch_create"
)
LIST_RECORDS_URL = (
    "https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}"
    "/tables/{table_id}/records"
)
UPDATE_RECORD_URL = (
    "https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}"
    "/tables/{table_id}/records/{record_id}"
)


class FeishuAPIError(RuntimeError):
    """Raised when Feishu OpenAPI returns an HTTP or business error."""


class FeishuBitableClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        http_client: Optional[httpx.Client] = None,
        max_retries: int = 3,
        retry_interval: float = 1.0,
        timeout: float = 15.0,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.http_client = http_client or httpx.Client(timeout=timeout)
        self.max_retries = max(1, max_retries)
        self.retry_interval = retry_interval
        self._tenant_access_token: Optional[str] = None

    @classmethod
    def from_env(cls) -> "FeishuBitableClient":
        env = {
            "FEISHU_APP_ID": os.getenv("FEISHU_APP_ID", "").strip(),
            "FEISHU_APP_SECRET": os.getenv("FEISHU_APP_SECRET", "").strip(),
            "FEISHU_APP_TOKEN": os.getenv("FEISHU_APP_TOKEN", "").strip(),
            "FEISHU_TABLE_ID": os.getenv("FEISHU_TABLE_ID", "").strip(),
        }
        missing = [key for key, value in env.items() if not value]
        if missing:
            raise ValueError(
                "Missing Feishu environment variables: " + ", ".join(missing)
            )
        return cls(
            app_id=env["FEISHU_APP_ID"],
            app_secret=env["FEISHU_APP_SECRET"],
            app_token=env["FEISHU_APP_TOKEN"],
            table_id=env["FEISHU_TABLE_ID"],
        )

    @staticmethod
    def build_batch_payload(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"records": [{"fields": record} for record in records]}

    def batch_create_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not records:
            return {"records": []}
        if len(records) > 500:
            raise ValueError("Feishu batch_create accepts at most 500 records per batch")

        token = self._get_tenant_access_token()
        url = BATCH_CREATE_URL.format(
            app_token=self.app_token,
            table_id=self.table_id,
        )
        payload = self.build_batch_payload(records)
        response = self._post_json(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.get("data", {})

    def list_records(self, page_size: int = 500) -> List[Dict[str, Any]]:
        if page_size < 1 or page_size > 500:
            raise ValueError("Feishu list records page_size must be between 1 and 500")

        token = self._get_tenant_access_token()
        url = LIST_RECORDS_URL.format(
            app_token=self.app_token,
            table_id=self.table_id,
        )
        records: List[Dict[str, Any]] = []
        page_token = ""

        while True:
            params: Dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            response = self._request_json(
                "GET",
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            data = response.get("data", {})
            records.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")
            if not page_token:
                break

        return records

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        token = self._get_tenant_access_token()
        url = UPDATE_RECORD_URL.format(
            app_token=self.app_token,
            table_id=self.table_id,
            record_id=record_id,
        )
        response = self._request_json(
            "PUT",
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"fields": fields},
        )
        return response.get("data", {})

    def _get_tenant_access_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token

        response = self._post_json(
            TENANT_ACCESS_TOKEN_URL,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        token = response.get("tenant_access_token")
        if not token:
            raise FeishuAPIError("Feishu token response missing tenant_access_token")
        self._tenant_access_token = token
        return token

    def _post_json(self, url: str, **kwargs: Any) -> Dict[str, Any]:
        return self._request_json("POST", url, **kwargs)

    def _request_json(self, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                request_method = getattr(self.http_client, method.lower())
                response = request_method(url, **kwargs)
                payload = self._parse_response_json(response)
                status_code = getattr(response, "status_code", 0)

                if status_code >= 500:
                    raise FeishuAPIError(
                        f"Feishu HTTP {status_code}: {payload.get('msg') or getattr(response, 'text', '')}"
                    )
                if status_code >= 400:
                    raise FeishuAPIError(
                        f"Feishu HTTP {status_code}: {payload.get('msg') or getattr(response, 'text', '')}"
                    )

                code = payload.get("code", 0)
                if code != 0:
                    raise FeishuAPIError(
                        f"Feishu API error code={code}: {payload.get('msg', 'unknown error')}"
                    )
                return payload
            except httpx.RequestError as exc:
                last_error = FeishuAPIError(f"Feishu request failed: {exc}")
            except FeishuAPIError as exc:
                last_error = exc
                if not self._should_retry(exc):
                    break

            if attempt < self.max_retries:
                time.sleep(self.retry_interval)

        raise FeishuAPIError(str(last_error or "Feishu request failed"))

    @staticmethod
    def _parse_response_json(response: Any) -> Dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            status_code = getattr(response, "status_code", "unknown")
            raise FeishuAPIError(f"Feishu HTTP {status_code}: invalid JSON response") from exc
        if not isinstance(payload, dict):
            raise FeishuAPIError("Feishu response JSON must be an object")
        return payload

    @staticmethod
    def _should_retry(error: FeishuAPIError) -> bool:
        message = str(error)
        return "HTTP 5" in message or "request failed" in message.lower()
