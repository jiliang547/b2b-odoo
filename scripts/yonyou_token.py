"""Local Windows C4 token helper; no Odoo or third-party Python dependency.

Credentials and cached tokens use Windows DPAPI (current user). Only the
explicit --print-token / --json-token options disclose a token on stdout.
"""
import argparse
import base64
from contextlib import contextmanager
import csv
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import getpass
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib import error, parse, request
import uuid


AUTH_URL = 'https://c4.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken'
GATEWAY_URL = 'https://c4.yonyoucloud.com/iuap-api-gateway'
REFRESH_MARGIN = 300


class TokenError(Exception):
    """Safe, deliberately credential-free user-facing error."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def make_auth_url(app_key, app_secret, timestamp):
    parameters = {'appKey': app_key, 'timestamp': str(timestamp)}
    signing_text = ''.join(key + parameters[key] for key in sorted(parameters))
    signature = hmac.new(app_secret.encode('utf-8'), signing_text.encode('utf-8'), hashlib.sha256).digest()
    parameters['signature'] = base64.b64encode(signature).decode('ascii')
    # Encode exactly once; do not pre-encode the base64 signature.
    return AUTH_URL + '?' + parse.urlencode(parameters)


def fetch_token(credentials, *, opener=None, now=None):
    started = time.time() if now is None else now
    url = make_auth_url(credentials['appKey'], credentials['appSecret'], int(started * 1000))
    req = request.Request(url, headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with (opener or request.build_opener(NoRedirect())).open(req, timeout=30) as response:
            if response.status != 200:
                raise TokenError('C4 authentication returned a non-success HTTP status.')
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise TokenError('C4 authentication response was unexpectedly large.')
        payload = json.loads(raw)
    except error.HTTPError as exc:
        raise TokenError(f'C4 authentication HTTP {exc.code}; redirects are not followed.') from None
    except (error.URLError, TimeoutError, OSError):
        raise TokenError('C4 authentication connection failed. Check the network and retry.') from None
    except (ValueError, UnicodeError):
        raise TokenError('C4 authentication returned invalid JSON.') from None
    if not isinstance(payload, dict):
        raise TokenError('C4 authentication returned an invalid response.')
    if str(payload.get('code')) != '00000':
        code = str(payload.get('code', 'unknown'))
        code = code if re.fullmatch(r'[0-9]{1,12}', code) else 'unknown'
        # Provider error text may echo request credentials; never log it verbatim.
        raise TokenError(f'C4 authentication rejected (code {code}). Check credentials, authorization and system time.')
    data = payload.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('access_token'), str) or not data['access_token'].strip():
        raise TokenError('C4 did not return an access_token.')
    expiry = data.get('expire')
    if isinstance(expiry, bool) or not re.fullmatch(r'[0-9]+', str(expiry)) or int(expiry) <= 0:
        raise TokenError('C4 did not return a valid positive expire value; no lifetime is guessed.')
    return {
        'access_token': data['access_token'],
        'credential_id': credentials['credential_id'],
        'obtained_at_epoch': started,
        'expires_at_epoch': started + int(expiry),
        'provider_expire_seconds': int(expiry),
    }


def dpapi(data, *, decrypt=False):
    if os.name != 'nt':
        raise TokenError('Encrypted local storage requires Windows. This is not an Odoo.sh service.')

    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        method = crypt.CryptUnprotectData
        method.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        second_arg = None
    else:
        method = crypt.CryptProtectData
        method.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        second_arg = 'Partner Hub C4 authentication'
    method.restype = wintypes.BOOL
    if not method(ctypes.byref(source), second_arg, None, None, None, 1, ctypes.byref(result)):
        raise TokenError('Windows could not protect/unprotect the local authentication data for this user.')
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree(result.pbData)


class WindowsStore:
    def __init__(self):
        if os.name != 'nt':
            raise TokenError('Use this local credential helper on Windows, not Odoo.sh.')
        local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
        self.root = local / 'PartnerHub' / 'YonyouC4Auth'
        if self.root.is_symlink() or (hasattr(self.root, 'is_junction') and self.root.is_junction()):
            raise TokenError('Refusing a linked credential directory.')
        self.root.mkdir(parents=True, exist_ok=True)
        sid_text = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True)
        sid = next(csv.reader(io.StringIO(sid_text.strip())))[1]
        subprocess.run(['icacls', str(self.root), '/inheritance:r', '/grant:r',
                        f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def read(self, name):
        path = self.root / (name + '.dpapi')
        if not path.exists():
            return None
        try:
            return json.loads(dpapi(path.read_bytes(), decrypt=True))
        except (OSError, ValueError):
            raise TokenError(f'The encrypted {name} file cannot be read.') from None

    def write(self, name, value):
        encrypted = dpapi(json.dumps(value).encode('utf-8'))
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, prefix='.writing-', delete=False) as output:
                temporary = Path(output.name)
                output.write(encrypted)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.root / (name + '.dpapi'))
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @contextmanager
    def lock(self):
        import msvcrt
        # OS-held lock is released even if the process crashes; no stale lock file cleanup.
        with (self.root / 'refresh.lock').open('a+b') as lock_file:
            lock_file.seek(0, 2)
            if lock_file.tell() == 0:
                lock_file.write(b'0')
                lock_file.flush()
            deadline = time.monotonic() + 40
            while True:
                lock_file.seek(0)
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TokenError('Another token refresh is busy. Retry shortly.') from None
                    time.sleep(0.1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


def cache_is_valid(cache, credentials, now):
    try:
        return (isinstance(cache, dict)
                and cache['credential_id'] == credentials['credential_id']
                and isinstance(cache['access_token'], str) and bool(cache['access_token'])
                and float(cache['obtained_at_epoch']) <= now
                and float(cache['expires_at_epoch']) - now > REFRESH_MARGIN)
    except (KeyError, ValueError, TypeError):
        return False


def get_token(store, *, force=False, fetcher=fetch_token, clock=time.time):
    with store.lock():
        credentials = store.read('credentials')
        if not isinstance(credentials, dict) or not all(credentials.get(key) for key in ('appKey', 'appSecret', 'credential_id')):
            raise TokenError('Run --configure once before requesting a token.')
        try:
            cached = store.read('token')
        except TokenError:
            cached = None
        if not force and cache_is_valid(cached, credentials, clock()):
            return cached, 'cache'
        refreshed = fetcher(credentials)
        if float(refreshed['expires_at_epoch']) <= clock():
            raise TokenError('The returned token is already expired; local cache was not changed.')
        store.write('token', refreshed)
        return refreshed, 'c4_authentication'


def token_metadata(token, source):
    return {
        'success': True,
        'source': source,
        'remaining_seconds': max(0, int(token['expires_at_epoch'] - time.time())),
        'expires_at': datetime.fromtimestamp(token['expires_at_epoch'], timezone.utc).astimezone().isoformat(timespec='seconds'),
        'gateway_url': GATEWAY_URL,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--configure', action='store_true', help='Store AppKey/AppSecret with Windows current-user encryption.')
    actions.add_argument('--force-refresh', action='store_true', help='Request C4 even when a cached token is usable.')
    actions.add_argument('--status', action='store_true', help='Inspect cache only; never contact C4.')
    parser.add_argument('--credentials-stdin', action='store_true', help='With --configure, read a credentials JSON object from stdin.')
    outputs = parser.add_mutually_exclusive_group()
    outputs.add_argument('--print-token', action='store_true', help='Explicitly output the plaintext token for a caller to capture.')
    outputs.add_argument('--json-token', action='store_true', help='Explicitly include the plaintext token in JSON output.')
    args = parser.parse_args()
    if args.credentials_stdin and not args.configure:
        parser.error('--credentials-stdin requires --configure')
    if (args.status or args.configure) and (args.print_token or args.json_token):
        parser.error('Token output is only available when getting/refreshing a token.')
    store = WindowsStore()
    if args.configure:
        credentials = (json.load(sys.stdin) if args.credentials_stdin else {
            'appKey': input('AppKey: ').strip(), 'appSecret': getpass.getpass('AppSecret (hidden): ').strip(),
        })
        if not isinstance(credentials, dict) or not all(isinstance(credentials.get(key), str) and credentials[key].strip() for key in ('appKey', 'appSecret')):
            raise TokenError('AppKey and AppSecret must be non-empty strings.')
        with store.lock():
            store.write('credentials', {'appKey': credentials['appKey'].strip(),
                                        'appSecret': credentials['appSecret'].strip(),
                                        'credential_id': uuid.uuid4().hex})
        print(json.dumps({'success': True, 'configured': True, 'encrypted_storage': str(store.root)}))
        return
    if args.status:
        with store.lock():
            credentials = store.read('credentials') or {}
            cached = store.read('token')
        valid = cache_is_valid(cached, credentials, time.time())
        result = {'success': True, 'configured': bool(credentials), 'usable_cached_token': bool(valid),
                  'encrypted_storage': str(store.root)}
        if isinstance(cached, dict) and cached.get('credential_id') == credentials.get('credential_id'):
            result.update(token_metadata(cached, 'cache_status'))
        print(json.dumps(result))
        return
    token, source = get_token(store, force=args.force_refresh)
    if args.print_token:
        print(token['access_token'])
    else:
        result = token_metadata(token, source)
        if args.json_token:
            result['access_token'] = token['access_token']
        print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except TokenError as exc:
        print(json.dumps({'success': False, 'error': str(exc)}), file=sys.stderr)
        sys.exit(1)
    except (Exception, KeyboardInterrupt) as exc:
        # No traceback, HTTP request URL, provider response, or credentials in errors.
        print(json.dumps({'success': False, 'error': f'Local authentication helper failed ({type(exc).__name__}).'}), file=sys.stderr)
        sys.exit(1)
