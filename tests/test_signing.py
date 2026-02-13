import unittest

from app.services.signing import flatten_sign_data, make_sign, verify_sign


class SigningTests(unittest.TestCase):
    def test_provider_reference_vector_matches(self):
        payload = {
            'currency': 'usd',
            'mchNo': '2023112614',
            'mchOrderNo': '2023112614-000001',
            'sign': '348A24E96B8F32FBB3C4DF805A309458',
            'signType': 'MD5',
            'timestamp': 1700532558623,
            'extParam': {'b': 2, 'a': 1, 'c': ''},
            'expiredTime': 1200,
            'clientIp': '1.1.1.1',
            'returnUrl': 'https://www.google.com',
            'notifyUrl': 'https://localhost/notify?abc=123&efg=456',
            'amount': 1000,
        }
        expected_base = (
            'amount=1000&clientIp=1.1.1.1&currency=usd&expiredTime=1200&'
            'extParam={"a":1,"b":2}&mchNo=2023112614&mchOrderNo=2023112614-000001&'
            'notifyUrl=https://localhost/notify?abc=123&efg=456&returnUrl=https://www.google.com&'
            'signType=MD5&timestamp=1700532558623'
        )

        self.assertEqual(flatten_sign_data(payload), expected_base)
        self.assertEqual(make_sign(payload, '123456789', 'MD5'), '348A24E96B8F32FBB3C4DF805A309458')

    def test_empty_values_and_sign_field_are_excluded(self):
        payload = {
            'b': '',
            'a': 1,
            'sign': 'SHOULD_NOT_BE_INCLUDED',
            'z': None,
            'obj': {'x': '', 'y': 2},
            'emptyObj': {'x': ''},
        }

        self.assertEqual(flatten_sign_data(payload), 'a=1&obj={"y":2}')

    def test_verify_sign_uses_uppercase_and_ignores_sign_in_source(self):
        payload = {'a': 1, 'b': 'x', 'signType': 'MD5'}
        payload['sign'] = make_sign(payload, 'secret', 'MD5').lower()

        self.assertTrue(verify_sign(payload, 'secret', 'MD5'))


if __name__ == '__main__':
    unittest.main()
