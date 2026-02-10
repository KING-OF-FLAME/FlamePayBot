import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.services.signing import make_sign

settings = get_settings()


class ProviderClient:
    def __init__(self) -> None:
        self.base = settings.provider_base_url.rstrip('/')
        self.timeout = settings.provider_timeout_seconds

    def _build_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        req = {
            'mchNo': settings.provider_mch_no,
            'mchUserName': settings.provider_username,
            'reqTime': int(time.time() * 1000),
            **payload,
        }
        req['signType'] = settings.provider_sign_type.upper()
        req['sign'] = make_sign(req, settings.provider_key, settings.provider_sign_type)
        return req

    @retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3), reraise=True)
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(f'{self.base}{path}', json=payload)
            r.raise_for_status()
            return r.json()

    def create(self, mch_order_no: str, amount_cents: int, way_code: str, remark: str = '') -> dict[str, Any]:
        payload = self._build_payload(
            {
                'mchOrderNo': mch_order_no,
                'amount': amount_cents,
                'currency': settings.default_currency,
                'wayCode': way_code,
                'notifyUrl': settings.notify_url,
                'returnUrl': settings.return_url,
                'subject': 'Balance Recharge',
                'body': remark or 'Recharge order',
            }
        )
        return self._post('/api/pay/create', payload)

    def query(self, mch_order_no: str | None = None, pay_order_no: str | None = None) -> dict[str, Any]:
        payload = {'mchOrderNo': mch_order_no, 'payOrderNo': pay_order_no}
        payload = {k: v for k, v in payload.items() if v}
        request_payload = self._build_payload(payload)
        return self._post('/api/pay/query', request_payload)

    def close(self, mch_order_no: str) -> dict[str, Any]:
        request_payload = self._build_payload({'mchOrderNo': mch_order_no})
        return self._post('/api/pay/close', request_payload)
