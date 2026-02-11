import json
import logging
import time
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.services.signing import make_sign

settings = get_settings()
logger = logging.getLogger(__name__)


class ProviderClient:
    def __init__(self) -> None:
        self.base = settings.provider_base_url.rstrip('/')
        self.timeout = settings.provider_timeout_seconds

    def _build_payload(self, payload: dict[str, Any], *, include_sign_type_in_sign: bool = True) -> dict[str, Any]:
        req = {
            'mchNo': settings.provider_mch_no,
            'timestamp': int(time.time() * 1000),
            **payload,
        }
        if settings.provider_username:
            req['username'] = settings.provider_username
        req['signType'] = settings.provider_sign_type.upper()
        ignore_keys = None if include_sign_type_in_sign else {'signType'}
        req['sign'] = make_sign(req, settings.provider_key, settings.provider_sign_type, ignore_keys=ignore_keys)
        return req

    @staticmethod
    def _is_signature_error(resp: dict[str, Any]) -> bool:
        if not isinstance(resp, dict):
            return False
        msg = str(resp.get('msg') or resp.get('message') or '').upper()
        code = str(resp.get('code', ''))
        return ('SIGN' in msg and 'ERROR' in msg) or code in {'1005'}


    @staticmethod
    def _is_duplicate_submission(resp: dict[str, Any]) -> bool:
        if not isinstance(resp, dict):
            return False
        msg = str(resp.get('msg') or resp.get('message') or '').upper()
        code = str(resp.get('code', ''))
        return ('DUPLICATE' in msg and 'SUBMISSION' in msg) or code == '14'

    @classmethod
    def _extract_cashier(cls, resp: dict[str, Any]) -> str | None:
        def _walk(node: Any) -> str | None:
            if isinstance(node, dict):
                for key in ('cashierUrl', 'cashierURL', 'payUrl', 'payURL', 'redirectUrl', 'redirectURL', 'url'):
                    value = node.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                for value in node.values():
                    nested = _walk(value)
                    if nested:
                        return nested
            elif isinstance(node, list):
                for item in node:
                    nested = _walk(item)
                    if nested:
                        return nested
            return None

        data = resp.get('data') if isinstance(resp, dict) else None
        return _walk(data)

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
            'currency': settings.default_currency.strip().lower(),
            'wayCode': way_code,
            'notifyUrl': settings.notify_url,
            'returnUrl': settings.return_url,
            'subject': 'Balance Recharge',
            'body': remark or 'Recharge order',
            'extParam': f'user:{mch_order_no}',
        }
        currency = str(payload['currency'])
        if len(currency) != 3 or currency.lower() != currency:
            raise ValueError('DEFAULT_CURRENCY must be a 3-letter lowercase code for provider create API (e.g. usd)')

        if client_ip:
            payload['clientIp'] = client_ip
        request_payload = self._build_payload(payload, include_sign_type_in_sign=True)
        logger.info('Provider create request mchOrderNo=%s wayCode=%s amount=%s ts=%s signType=%s sign=%s', mch_order_no, way_code, payload['amount'], request_payload['timestamp'], request_payload['signType'], str(request_payload.get('sign', ''))[:8] + '...')
        response = self._post('/api/pay/create', request_payload)
        logger.info('Provider create response mchOrderNo=%s code=%s msg=%s has_cashier=%s', mch_order_no, response.get('code') if isinstance(response, dict) else None, (response.get('msg') if isinstance(response, dict) else None), bool(self._extract_cashier(response) if isinstance(response, dict) else False))
        logger.debug('Provider create raw mchOrderNo=%s body=%s', mch_order_no, json.dumps(response, ensure_ascii=False) if isinstance(response, dict) else str(response))

        if self._is_signature_error(response) and settings.provider_retry_alt_sign:
            alt_payload = self._build_payload(payload, include_sign_type_in_sign=False)
            logger.warning('Retrying provider create with alternate sign composition mchOrderNo=%s', mch_order_no)
            response = self._post('/api/pay/create', alt_payload)
            logger.info('Provider create alt response mchOrderNo=%s code=%s msg=%s has_cashier=%s', mch_order_no, response.get('code') if isinstance(response, dict) else None, (response.get('msg') if isinstance(response, dict) else None), bool(self._extract_cashier(response) if isinstance(response, dict) else False))
            logger.debug('Provider create alt raw mchOrderNo=%s body=%s', mch_order_no, json.dumps(response, ensure_ascii=False) if isinstance(response, dict) else str(response))

        if self._is_duplicate_submission(response):
            duplicate_response = response
            for _ in range(3):
                query_response = self.query(mch_order_no=mch_order_no)
                logger.info('Provider duplicate recovery query mchOrderNo=%s code=%s msg=%s has_cashier=%s', mch_order_no, query_response.get('code') if isinstance(query_response, dict) else None, (query_response.get('msg') if isinstance(query_response, dict) else None), bool(self._extract_cashier(query_response) if isinstance(query_response, dict) else False))
                if self._extract_cashier(query_response):
                    return query_response
                time.sleep(0.8)
            return duplicate_response

        return response

    def query(self, mch_order_no: str | None = None, pay_order_no: str | None = None) -> dict[str, Any]:
        payload = {'mchOrderNo': mch_order_no, 'payOrderNo': pay_order_no}
        payload = {k: v for k, v in payload.items() if v}
        if not payload:
            raise ValueError('Either mchOrderNo or payOrderNo is required for query')
        request_payload = self._build_payload(payload)
        logger.info('Provider query request mchOrderNo=%s payOrderNo=%s ts=%s', mch_order_no, pay_order_no, request_payload['timestamp'])
        response = self._post('/api/pay/query', request_payload)
        logger.info('Provider query response mchOrderNo=%s payOrderNo=%s code=%s msg=%s has_cashier=%s', mch_order_no, pay_order_no, response.get('code') if isinstance(response, dict) else None, (response.get('msg') if isinstance(response, dict) else None), bool(self._extract_cashier(response) if isinstance(response, dict) else False))
        logger.debug('Provider query raw mchOrderNo=%s payOrderNo=%s body=%s', mch_order_no, pay_order_no, json.dumps(response, ensure_ascii=False) if isinstance(response, dict) else str(response))
        return response

    def close(self, mch_order_no: str, pay_order_no: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {'mchOrderNo': mch_order_no}
        if pay_order_no:
            payload['payOrderNo'] = pay_order_no
        request_payload = self._build_payload(payload)
        return self._post('/api/pay/close', request_payload)
