import os
import unittest
from unittest.mock import patch

_REQUIRED_ENV = {
    'APP_ENV': 'development',
    'LOG_LEVEL': 'INFO',
    'BOT_TOKEN': 'test-token',
    'BOT_USERNAME': 'test_bot',
    'ADMIN_IDS': '1',
    'MYSQL_HOST': '127.0.0.1',
    'MYSQL_PORT': '3306',
    'MYSQL_USER': 'root',
    'MYSQL_PASSWORD': '',
    'MYSQL_DB': 'flamepaybot',
    'PROVIDER_BASE_URL': 'https://www.ggusonepay.com',
    'PROVIDER_MCH_NO': '123',
    'PROVIDER_USERNAME': 'tester',
    'PROVIDER_KEY': 'secret',
    'PROVIDER_SIGN_TYPE': 'MD5',
    'PROVIDER_TIMEOUT_SECONDS': '15',
    'GLOBAL_FEE_PERCENT': '15.0',
    'DEFAULT_CURRENCY': 'usd',
    'NOTIFY_URL': 'https://example.com/notify',
    'RETURN_URL': 'https://t.me/test_bot',
}
for key, value in _REQUIRED_ENV.items():
    os.environ.setdefault(key, value)

from app.services.provider_client import ProviderClient


class DummyProviderClient(ProviderClient):
    def __init__(self):
        super().__init__()
        self.calls: list[dict] = []

    def _post(self, path: str, payload: dict):
        self.calls.append({'path': path, 'payload': payload})
        if len(self.calls) == 1:
            return {'code': 1005, 'msg': 'SIGNATURE ERROR'}
        return {'code': 0, 'msg': 'success', 'data': {'cashierUrl': 'https://example.com/cashier'}}


class DuplicateProviderClient(ProviderClient):
    def __init__(self):
        super().__init__()
        self.calls: list[dict] = []

    def _post(self, path: str, payload: dict):
        self.calls.append({'path': path, 'payload': payload})
        if path == '/api/pay/create':
            return {'code': 2008, 'msg': 'DUPLICATE SUBMISSION[/api/pay/create]'}
        return {'code': 0, 'msg': 'success', 'data': {'cashierUrl': 'https://example.com/recovered', 'payOrderNo': 'PO123', 'state': '1'}}


class DuplicateEventuallyConsistentClient(ProviderClient):
    def __init__(self):
        super().__init__()
        self.calls: list[dict] = []
        self.query_count = 0

    def _post(self, path: str, payload: dict):
        self.calls.append({'path': path, 'payload': payload})
        if path == '/api/pay/create':
            return {'code': 2008, 'msg': 'DUPLICATE SUBMISSION[/api/pay/create]'}
        self.query_count += 1
        if self.query_count == 1:
            return {'code': 0, 'msg': 'processing', 'data': {'state': '1'}}
        return {'code': 0, 'msg': 'success', 'data': {'payData': {'cashierUrl': 'https://example.com/later'}}}


class ProviderClientTests(unittest.TestCase):
    def test_create_retries_on_signature_error_with_alt_signature(self):
        client = DummyProviderClient()
        response = client.create('ORD-1', 500, 'card')
        self.assertEqual(response['code'], 0)
        self.assertEqual(len(client.calls), 2)
        first_payload = client.calls[0]['payload']
        second_payload = client.calls[1]['payload']
        self.assertEqual(first_payload['currency'], 'usd')
        self.assertEqual(second_payload['currency'], 'usd')
        self.assertNotEqual(first_payload['sign'], second_payload['sign'])

    def test_create_recovers_duplicate_by_query(self):
        client = DuplicateProviderClient()
        response = client.create('ORD-2', 500, 'card')
        self.assertEqual(response.get('code'), 0)
        self.assertEqual(response.get('data', {}).get('cashierUrl'), 'https://example.com/recovered')
        self.assertEqual([c['path'] for c in client.calls], ['/api/pay/create', '/api/pay/query'])

    def test_create_duplicate_retries_query_until_cashier_available(self):
        client = DuplicateEventuallyConsistentClient()
        with patch('app.services.provider_client.time.sleep', return_value=None):
            response = client.create('ORD-3', 500, 'card')
        self.assertEqual(response.get('data', {}).get('payData', {}).get('cashierUrl'), 'https://example.com/later')
        self.assertEqual([c['path'] for c in client.calls], ['/api/pay/create', '/api/pay/query', '/api/pay/query'])


if __name__ == '__main__':
    unittest.main()
