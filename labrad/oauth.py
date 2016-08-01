"""Implements the OAuth 2.0 flow for Mobile and Desktop Apps.

The flow is described in detail in the google developer docs:
https://developers.google.com/identity/protocols/OAuth2InstalledApp

We use OAuth to fetch a token which identifies the user by google account.
This token is then passed to the manager, and the manager in turn calls google
APIs to validate the token and extract the user's email address. It then checks
to see that this email address has been registered as a labrad user.
"""

from __future__ import absolute_import
from __future__ import print_function

import BaseHTTPServer
import json
import os
import threading
import time
import urllib
import urlparse
import webbrowser

from concurrent import futures
import requests


# Page to display after we complete the OAuth flow
_OAUTH_PAGE = """
<html>
<head>
  <title>Labrad authorized!</title>
</head>
<body>
  <h1>Labrad authorized!</h1>
  <p>You may now close this window.</p>
</body>
</html>
"""


OAUTH_URI = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URI = 'https://www.googleapis.com/oauth2/v4/token'
NO_REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'


TOKEN_PATH = os.path.join(os.path.expanduser('~'), '.labrad', 'client')
TOKEN_FILE = os.path.join(TOKEN_PATH, 'oauth_tokens.json')


# In-memory cache of OAuth tokens. Lasts until the python session is closed.
_token_cache = {}
_token_cache_lock = threading.RLock()


class OAuthToken(object):
    def __init__(self, resp):
        self.access_token = resp['access_token']
        self.expires_at = resp['expires_at']
        self.id_token = resp['id_token']
        self.refresh_token = resp['refresh_token']
        self.token_type = resp['token_type']


def get_token(client_id, client_secret, headless=False, timeout=60):
    """Get id token by asking the user to complete OAuth login flow.

    If we have a cached id_token for this client_id that is not expired, we use
    that. Similarly, if we have a cached refresh_token we will attempt to use
    it to get a new id_token. If refreshing fails, we go through the OAuth flow
    as usual.

    After successfully completing the login flow, we cache the OAuth tokens to
    be used on subsequent login attempts.

    Args:
        client_id (str): The client_id for the app we want to authorize.
        client_secret (str): The client_secret for the app we want to authorize.
        headless (bool): If False, the default, we open a web browser to perform
            the OAuth login and spin up a local http server to receive the
            authorization code. If True, or if we fail to open a webbrowser,
            we print a url for the user to visit to get the authorization code,
            which they must then paste into the terminal. The headless is useful
            in some scenarios such as when tunneling through ssh.
        timeout (int): Amount of time to wait for OAuth login flow to complete,
            in seconds.

    Returns:
        (str) id_token to be passed to the manager to identify the user.
    """
    cached = _get_cached_token(client_id)
    if cached is None:
        print('No cached token. Logging in...')
    else:
        if cached.expires_at > time.time() + 600:
            print('Using cached id_token...')
            return cached
        print('Trying cached refresh_token...')
        try:
            token = _refresh_token(client_id, client_secret,
                                   cached.refresh_token)
            _cache_token(client_id, token)
            return token
        except Exception:
            print('Failed to refresh token. Logging in...')

    def do_headless_login():
        redirect_uri = NO_REDIRECT_URI
        login_uri = _create_login_uri(client_id, redirect_uri)
        print('To obtain an OAuth authorization code, please navigate to the '
              'following URL in a browser:\n\n{}\n'.format(login_uri))
        code = raw_input('When you have completed the login flow, enter the '
                         'code here: ')
        return redirect_uri, code

    if headless:
        redirect_uri, code = do_headless_login()
    else:
        code_future = futures.Future()

        class OAuthHandler(BaseHTTPServer.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed_path = urlparse.urlparse(self.path)
                params = urlparse.parse_qs(parsed_path.query)
                code = params['code'][0]
                code_future.set_result(code)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(_OAUTH_PAGE)

            def log_request(self, *args, **kw):
                pass

        # Start local http server to receive redirect on random port
        httpd = BaseHTTPServer.HTTPServer(('localhost', 0), OAuthHandler)
        _, local_port = httpd.server_address

        redirect_uri = 'http://localhost:{}'.format(local_port)
        login_uri = _create_login_uri(client_id, redirect_uri)
        ok = webbrowser.open(login_uri)
        if ok:
            print('Launched web browser to log in with OAuth. Will timeout in '
                  '{} seconds'.format(timeout))
            # Wait to receive code via redirect to local http server
            httpd.timeout = timeout
            httpd.handle_request()
            code = code_future.result(timeout=timeout)
        else:
            redirect_uri, code = do_headless_login()

    data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    response = _send_request(TOKEN_URI, data)
    response['expires_at'] = int(time.time() + response['expires_in'])
    token = OAuthToken(response)
    _cache_token(client_id, token)
    return token


# HTTP helpers.

def _create_login_uri(client_id, redirect_uri):
    """Create URI to start the OAuth flow.

    Args:
        client_id (str): The OAuth client_id of the app to authorize.
        redirect_uri (str): The uri where the user should be redirected to
            receive the authorization code after authorizing the app. This can
            be a localhost url or the special value stored in NO_REDIRECT_URI
            for the "headless" flow.

    Returns:
        (str) URL the user should visit to start the OAuth flow.
    """
    params = {
        'scope': 'openid email profile',
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'client_id': client_id
    }
    return '{}?{}'.format(OAUTH_URI, urllib.urlencode(params))


def _refresh_token(client_id, client_secret, refresh_token):
    """Attempt to use the given refresh_token to obtain a new id_token.

    Args:
        client_id (str): The OAuth client_id of the app to authorize.
        client_secret (str): The client_secret of the app to authorize.
        refresh_token (str): Token to use to try to fetch a refreshed id_token.

    Returns:
        (OAuthToken) Token containing information from JSON response.
    """
    data = {
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'refresh_token'
    }
    response = _send_request(TOKEN_URI, data)
    response['expires_at'] = int(time.time() + response['expires_in'])
    response['refresh_token'] = refresh_token
    return OAuthToken(response)


def _send_request(url, params):
    """Helper to send a POST request with the given parameters."""
    r = requests.post(url, data=params)
    if r.status_code != 200:
        raise Exception('request failed: status_code={}'.format(r.status_code))
    return r.json()


# Token cache helpers.

def clear_token_cache():
    """Discard all cached OAuth tokens."""
    with _token_cache_lock:
        _token_cache = {}
        _save_tokens({})


def _get_cached_token(client_id):
    """Get cached token information for the given OAuth client_id.

    Args:
        client_id (str): The OAuth client_id for the app to be authorized.

    Returns:
        (OAuthToken or None): Token for the given client_id or None if we do
        not have a cached token.
    """
    with _token_cache_lock:
        if client_id in _token_cache:
            return _token_cache[client_id]
        tokens = _load_tokens()
        if client_id in tokens:
            return OAuthToken(tokens[client_id])
        return None


def _cache_token(client_id, token, persistent=True):
    """Cache token response for the given client_id.

    Args:
        client_id (str): The OAuth client_id for the app to be authorized.
        resp (OAuthToken): Dict of JSON response parameters from a successful OAuth
            API call. Should contain 'access_token', 'id_token', 'expires_in',
            'refresh_token', and 'token_type' entries. We convert 'expires_in'
            from a relative time to an absolute epoch time and store it as
            'expires_at'.
    """
    with _token_cache_lock:
        _token_cache[client_id] = token
        if persistent:
            tokens = _load_tokens()
            tokens[client_id] = {
                'access_token': token.access_token,
                'expires_at': token.expires_at,
                'id_token': token.id_token,
                'refresh_token': token.refresh_token,
                'token_type': token.token_type
            }
            _save_tokens(tokens)


def _load_tokens():
    """Load dict containing cached tokens, indexed by client_id."""
    _ensure_token_file()
    with open(TOKEN_FILE) as f:
        contents = f.read()
    if not contents:
        return {}
    return json.loads(contents)


def _save_tokens(tokens):
    """Save a dict of cached tokens, indexed by client_id."""
    _ensure_token_file()
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f, sort_keys=True, indent=4)


def _ensure_token_file():
    """Ensure that the token cache file exists and has appropriate perms."""
    if not os.path.exists(TOKEN_PATH):
        os.makedirs(TOKEN_PATH)
    if not os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'w') as f:
            pass
    os.chmod(TOKEN_FILE, 0o600)

