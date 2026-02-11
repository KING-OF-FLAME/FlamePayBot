import os
import unittest
from fastapi.testclient import TestClient


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
    'DEFAULT_CURRENCY': 'USD',
    'NOTIFY_URL': 'https://example.com/notify',
    'RETURN_URL': 'https://t.me/test_bot',
}

for key, value in _REQUIRED_ENV.items():
    os.environ.setdefault(key, value)

from app.api.webhook import app


class WebhookSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_get_notify_probe(self) -> None:
        response = self.client.get('/notify')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['code'], 0)
        self.assertIn('POST', body['msg'])

    def test_post_notify_empty_body(self) -> None:
        response = self.client.post('/notify')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'code': -1, 'msg': 'invalid payload'})

    def test_post_notify_json_invalid_sign(self) -> None:
        response = self.client.post('/notify', json={'mchOrderNo': 'X'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'code': -1, 'msg': 'invalid sign'})

    def test_post_notify_form_invalid_sign(self) -> None:
        response = self.client.post('/notify', data={'mchOrderNo': 'X'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'code': -1, 'msg': 'invalid sign'})


if __name__ == '__main__':
    unittest.main()
