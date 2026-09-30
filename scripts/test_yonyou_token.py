"""Offline authentication helper tests. All credentials/tokens are synthetic."""
from contextlib import nullcontext
import base64
import hashlib
import hmac
import json
import os
import unittest
from urllib import error, parse

import yonyou_token as auth


CREDS = {'appKey': 'demo-key', 'appSecret': 'demo-secret', 'credential_id': 'demo-generation'}
NOW = 1700000000


def token(ttl=7200):
    return {'access_token': 'synthetic-token', 'credential_id': CREDS['credential_id'],
            'obtained_at_epoch': NOW - 1, 'expires_at_epoch': NOW + ttl,
            'provider_expire_seconds': ttl}


class MemoryStore:
    def __init__(self, cached=None):
        self.values = {'credentials': dict(CREDS), 'token': cached}
        self.writes = []

    def lock(self):
        return nullcontext()

    def read(self, key):
        value = self.values.get(key)
        if isinstance(value, Exception):
            raise value
        return value

    def write(self, key, value):
        self.writes.append(key)
        self.values[key] = value


class Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.body[:size]


class Opener:
    def __init__(self, payload=None, raw=None, exception=None):
        self.body = json.dumps(payload).encode() if raw is None else raw
        self.exception = exception
        self.request = None

    def open(self, req, timeout):
        self.request = req
        if self.exception:
            raise self.exception
        return Response(self.body)


class TestProtocol(unittest.TestCase):
    def test_signing_and_single_url_encoding(self):
        url = auth.make_auth_url('demo-key', 'demo-secret', 1700000000000)
        parts = parse.urlsplit(url)
        self.assertEqual(parts.scheme, 'https')
        self.assertEqual(parts.netloc, 'c4.yonyoucloud.com')
        self.assertEqual(parts.path, '/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken')
        values = parse.parse_qs(parts.query)
        expected = base64.b64encode(hmac.new(b'demo-secret', b'appKeydemo-keytimestamp1700000000000', hashlib.sha256).digest()).decode()
        self.assertEqual(values['signature'], [expected])
        self.assertEqual(values['timestamp'], ['1700000000000'])
        self.assertNotIn('demo-secret', url)

    def test_actual_server_lifetime_not_fixed_two_hours(self):
        opener = Opener({'code': '00000', 'data': {'access_token': 'synthetic-token', 'expire': 7122}})
        result = auth.fetch_token(CREDS, opener=opener, now=NOW)
        self.assertEqual(result['expires_at_epoch'], NOW + 7122)
        self.assertEqual(opener.request.get_header('Content-type'), 'application/json')

    def test_missing_or_invalid_lifetime_is_not_guessed(self):
        for expiry in (None, 0, -1, True, 'invalid', 1.5):
            with self.subTest(expiry=expiry), self.assertRaises(auth.TokenError):
                auth.fetch_token(CREDS, opener=Opener({'code': '00000', 'data': {'access_token': 'synthetic-token', 'expire': expiry}}), now=NOW)

    def test_response_requires_success_and_nonempty_token(self):
        for payload in ({'code': '00000', 'data': {}}, {'code': '00000', 'data': []},
                        {'code': '00000', 'data': {'access_token': ' ', 'expire': 7200}}, []):
            with self.subTest(payload=payload), self.assertRaises(auth.TokenError):
                auth.fetch_token(CREDS, opener=Opener(payload), now=NOW)

    def test_provider_error_does_not_echo_credentials(self):
        with self.assertRaises(auth.TokenError) as raised:
            auth.fetch_token(CREDS, opener=Opener({'code': '10001', 'message': 'demo-secret demo-key'}), now=NOW)
        self.assertNotIn('demo-secret', str(raised.exception))
        self.assertNotIn('demo-key', str(raised.exception))

    def test_http_failure_does_not_echo_signed_url(self):
        failure = error.HTTPError('https://example.invalid/?signature=secret', 403, 'private-message', {}, None)
        with self.assertRaises(auth.TokenError) as raised:
            auth.fetch_token(CREDS, opener=Opener(exception=failure), now=NOW)
        self.assertIn('403', str(raised.exception))
        self.assertNotIn('signature', str(raised.exception))
        self.assertNotIn('private-message', str(raised.exception))

    def test_network_failure_safe(self):
        with self.assertRaises(auth.TokenError) as raised:
            auth.fetch_token(CREDS, opener=Opener(exception=error.URLError('private URL signature')), now=NOW)
        self.assertNotIn('signature', str(raised.exception))

    def test_invalid_json_safe(self):
        with self.assertRaises(auth.TokenError):
            auth.fetch_token(CREDS, opener=Opener(raw=b'not-json'), now=NOW)

    def test_oversized_response_refused(self):
        with self.assertRaises(auth.TokenError):
            auth.fetch_token(CREDS, opener=Opener(raw=b'x' * 1_000_001), now=NOW)

    def test_redirects_refused(self):
        self.assertIsNone(auth.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.invalid'))


class TestCaching(unittest.TestCase):
    def run_get(self, store, force=False, fail=False):
        self.calls = 0

        def fetcher(credentials):
            self.calls += 1
            if fail:
                raise auth.TokenError('Synthetic failure')
            result = token()
            result['credential_id'] = credentials['credential_id']
            return result

        return auth.get_token(store, force=force, fetcher=fetcher, clock=lambda: NOW)

    def test_valid_cache_avoids_network(self):
        store = MemoryStore(token())
        self.assertEqual(self.run_get(store)[1], 'cache')
        self.assertEqual(self.calls, 0)
        self.assertFalse(store.writes)

    def test_expired_and_near_expiry_refresh(self):
        for ttl in (-1, 0, 299, 300):
            with self.subTest(ttl=ttl):
                store = MemoryStore(token(ttl))
                self.assertEqual(self.run_get(store)[1], 'c4_authentication')
                self.assertEqual(self.calls, 1)

    def test_force_refresh_bypasses_valid_cache(self):
        self.assertEqual(self.run_get(MemoryStore(token()), force=True)[1], 'c4_authentication')
        self.assertEqual(self.calls, 1)

    def test_new_credentials_invalidate_old_cache(self):
        store = MemoryStore(token())
        store.values['credentials']['credential_id'] = 'new-generation'
        result, source = self.run_get(store)
        self.assertEqual(source, 'c4_authentication')
        self.assertEqual(result['credential_id'], 'new-generation')

    def test_failure_preserves_previous_cache_but_does_not_return_it(self):
        original = token(1)
        store = MemoryStore(original)
        with self.assertRaises(auth.TokenError):
            self.run_get(store, fail=True)
        self.assertEqual(store.values['token'], original)
        self.assertFalse(store.writes)

    def test_corrupt_token_cache_can_be_replaced(self):
        self.assertEqual(self.run_get(MemoryStore(auth.TokenError('Unreadable cache')))[1], 'c4_authentication')

    def test_missing_credentials_fail_before_network(self):
        store = MemoryStore()
        store.values['credentials'] = None
        with self.assertRaises(auth.TokenError):
            self.run_get(store)
        self.assertEqual(self.calls, 0)

    def test_clock_rollback_invalidates_cache(self):
        cache = token()
        cache['obtained_at_epoch'] = NOW + 30
        self.assertFalse(auth.cache_is_valid(cache, CREDS, NOW))

    def test_malformed_cache_invalid(self):
        for cached in (None, [], {}, {'access_token': 'x'}):
            self.assertFalse(auth.cache_is_valid(cached, CREDS, NOW))

    def test_returned_expired_token_not_written(self):
        store = MemoryStore()
        with self.assertRaises(auth.TokenError):
            auth.get_token(store, fetcher=lambda _: token(-1), clock=lambda: NOW)
        self.assertFalse(store.writes)

    def test_metadata_does_not_include_token(self):
        self.assertNotIn('synthetic-token', json.dumps(auth.token_metadata(token(), 'cache')))

    @unittest.skipUnless(os.name == 'nt', 'Windows encryption')
    def test_windows_encryption_round_trip(self):
        plaintext = b'{"appSecret":"synthetic-secret"}'
        encrypted = auth.dpapi(plaintext)
        self.assertNotIn(b'synthetic-secret', encrypted)
        self.assertEqual(auth.dpapi(encrypted, decrypt=True), plaintext)


if __name__ == '__main__':
    unittest.main()
