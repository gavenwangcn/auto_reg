"""Probe OpenBlockLabs sign-up page for next-action ID extraction."""
import re
import sys
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

URL = "https://auth.openblocklabs.com/sign-up"
AUTH_ROOT = "https://auth.openblocklabs.com/"
CLIENT_ID = "client_01K8YDZSSKDMK8GYTEHBAW4N4S"
REDIRECT_URI = "https://dashboard.openblocklabs.com/auth/callback"
PARAMS = {"redirect_uri": REDIRECT_URI}
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)

PATTERNS = [
    (r'\\?"id\\?":\\?"([a-f0-9]{40})\\?"', "current_code_regex"),
    (r'\\"id\\":\\"([a-f0-9]{40})\\"', "escaped_json_id"),
    (r'"id":"([a-f0-9]{40})"', "plain_json_id"),
]


def extract_action_id(text: str) -> tuple[str | None, str | None]:
    for pat, name in PATTERNS:
        match = re.search(pat, text)
        if match:
            return match.group(1), name
    return None, None


def normalize_auth_landing_url(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if not parsed.path.rstrip("/").endswith("/sign-up") or not qs.get("client_id"):
        return url
    query = urlencode(
        {
            "client_id": qs["client_id"][0],
            "redirect_uri": qs.get("redirect_uri", [REDIRECT_URI])[0],
            "authorization_session_id": qs.get("authorization_session_id", [""])[0],
        }
    )
    return f"{AUTH_ROOT}?{query}"


def follow_auth_redirects(session, start_url: str, params: dict | None = None):
    url = start_url
    query_params = params
    history = []
    for _ in range(15):
        resp = session.get(url, params=query_params, allow_redirects=False, timeout=30)
        query_params = None
        history.append((resp.status_code, str(resp.url), resp.headers.get("location", "")))
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("location", "")
            if not loc:
                return resp, history
            url = normalize_auth_landing_url(urljoin(str(resp.url), loc))
            continue
        return resp, history
    return resp, history


def fetch_root_no_redirect(session, session_id: str):
    root_url = f"{AUTH_ROOT}?{urlencode({'client_id': CLIENT_ID, 'redirect_uri': REDIRECT_URI, 'authorization_session_id': session_id})}"
    return root_url, session.get(root_url, allow_redirects=False, timeout=30)


def fetch_with_stdlib():
    import urllib.request

    req = urllib.request.Request(
        f"{URL}?redirect_uri={REDIRECT_URI}",
        headers={"user-agent": UA},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return str(resp.geturl()), resp.read().decode("utf-8", errors="ignore")


def fetch_with_curl_cffi():
    from curl_cffi import requests

    s = requests.Session()
    s.impersonate = "chrome131"
    s.headers.update({"user-agent": UA})
    resp, history = follow_auth_redirects(s, URL, PARAMS)
    return s, resp, history


def main() -> int:
    backend = "curl_cffi"
    strategy = "manual_redirect"
    history = []
    try:
        session, resp, history = fetch_with_curl_cffi()
        final_url = str(resp.url)
        text = resp.text
        status = resp.status_code
    except ImportError:
        backend = "urllib"
        final_url, text = fetch_with_stdlib()
        status = 200
        session = None
        strategy = "stdlib"

    action_id, pattern = extract_action_id(text)
    session_match = re.search(r"authorization_session_id=([^&]+)", final_url)

    if not action_id and session_match and session is not None:
        norm = normalize_auth_landing_url(final_url)
        if norm != final_url:
            strategy = "normalize_landing"
            resp = session.get(norm, allow_redirects=False, timeout=30)
            final_url = str(resp.url)
            text = resp.text
            action_id, pattern = extract_action_id(text)
            if action_id:
                pattern = f"normalize:{pattern}"

    if not action_id and session_match and session is not None:
        strategy = "root_no_redirect"
        root_url, root_resp = fetch_root_no_redirect(session, session_match.group(1))
        action_id, pattern = extract_action_id(root_resp.text)
        print(f"root_url: {root_url}")
        print(f"root_status: {root_resp.status_code}")
        print(f"root_location: {root_resp.headers.get('location', '')[:120]}")
        if action_id:
            pattern = f"root:{pattern}"
            text = root_resp.text
            final_url = root_url

    if not action_id and backend == "curl_cffi":
        strategy = "stdlib_fallback"
        final_url, text = fetch_with_stdlib()
        action_id, pattern = extract_action_id(text)
        if action_id:
            pattern = f"stdlib:{pattern}"

    print(f"backend: {backend}")
    print(f"strategy: {strategy}")
    if history:
        for i, (code, url, loc) in enumerate(history):
            print(f"redirect[{i}]: {code} {url[:80]} -> {loc[:80]}")
    print(f"status: {status}")
    print(f"final_url: {final_url}")
    print(f"html_len: {len(text)}")
    print(f"session_id: {session_match.group(1) if session_match else None}")
    print(f"action_id: {action_id}")
    print(f"matched_pattern: {pattern}")

    if not action_id:
        print("body_tail:", text[-500:])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
