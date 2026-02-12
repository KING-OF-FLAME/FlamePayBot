import os
import unittest

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
    'PROVIDER_SIGN_INCLUDE_SIGNTYPE': '1',
    'GLOBAL_FEE_PERCENT': '15.0',
    'DEFAULT_CURRENCY': 'usd',
    'NOTIFY_URL': 'https://example.com/notify',
    'RETURN_URL': 'https://t.me/test_bot',
}
for key, value in _REQUIRED_ENV.items():
    os.environ.setdefault(key, value)

from app.bot.handlers.admin import parse_package_amount_to_cents


class AdminPackageAmountTests(unittest.TestCase):
    def test_parse_decimal_dollars(self):
        self.assertEqual(parse_package_amount_to_cents('19.99'), 1999)

    def test_parse_cents_integer(self):
        self.assertEqual(parse_package_amount_to_cents('500'), 500)

    def test_reject_more_than_two_decimals(self):
        with self.assertRaises(ValueError):
            parse_package_amount_to_cents('19.999')


if __name__ == '__main__':
    unittest.main()
