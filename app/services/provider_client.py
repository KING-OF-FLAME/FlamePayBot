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
            'timestamp': int(time.time() * 1000),
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
            data = r.json()
            if not isinstance(data, dict):
                raise httpx.HTTPError(f'Provider returned non-JSON object for {path}')
            return data

    def create(self, mch_order_no: str, amount_cents: int, way_code: str, remark: str = '', client_ip: str | None = None) -> dict[str, Any]:
        payload = {
            'mchOrderNo': mch_order_no,
            'amount': int(amount_cents),
            'currency': settings.default_currency.lower(),
            'wayCode': way_code,
            'notifyUrl': settings.notify_url,
            'returnUrl': settings.return_url,
            'subject': 'Balance Recharge',
            'body': remark or 'Recharge order',
            'extParam': f'user:{mch_order_no}',
        }
        if client_ip:
            payload['clientIp'] = client_ip
        request_payload = self._build_payload(payload)
        return self._post('/api/pay/create', request_payload)

    def query(self, mch_order_no: str | None = None, pay_order_no: str | None = None) -> dict[str, Any]:
        payload = {'mchOrderNo': mch_order_no, 'payOrderNo': pay_order_no}
        payload = {k: v for k, v in payload.items() if v}
        if not payload:
            raise ValueError('Either mchOrderNo or payOrderNo is required for query')
        request_payload = self._build_payload(payload)
        return self._post('/api/pay/query', request_payload)

    def close(self, mch_order_no: str, pay_order_no: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {'mchOrderNo': mch_order_no}
        if pay_order_no:
            payload['payOrderNo'] = pay_order_no
        request_payload = self._build_payload(payload)
        return self._post('/api/pay/close', request_payload)
