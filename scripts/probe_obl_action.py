"""Probe OpenBlockLabs sign-up page for next-action ID extraction."""
import re
import sys

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


def fetch_auth_root_page(session, session_id: str):
    from urllib.parse import urlencode

    root_url = f"{AUTH_ROOT}?{urlencode({'client_id': CLIENT_ID, 'redirect_uri': REDIRECT_URI, 'authorization_session_id': session_id})}"
    return session.get(root_url, allow_redirects=True, timeout=30)


def fetch_with_curl_cffi():
    from curl_cffi import requests

    s = requests.Session()
    s.impersonate = "chrome131"
    s.headers.update({"user-agent": UA})
    resp = s.get(URL, params=PARAMS, allow_redirects=True, timeout=30)
    return s, resp


def fetch_with_urllib():
    import urllib.request

    query = "&".join(f"{k}={v}" for k, v in PARAMS.items())
    req = urllib.request.Request(
        f"{URL}?{query}",
        headers={"user-agent": UA},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="ignore")
        return resp.geturl(), text


def main() -> int:
    backend = "curl_cffi"
    try:
        session, resp = fetch_with_curl_cffi()
        final_url = str(resp.url)
        text = resp.text
        status = resp.status_code
    except ImportError:
        backend = "urllib"
        final_url, text = fetch_with_urllib()
        status = 200
        session = None

    action_id, pattern = extract_action_id(text)
    session_match = re.search(r"authorization_session_id=([^&]+)", final_url)

    if not action_id and session_match and session is not None:
        root_resp = fetch_auth_root_page(session, session_match.group(1))
        action_id, pattern = extract_action_id(root_resp.text)
        if action_id:
            pattern = f"root_page:{pattern}"
            text = root_resp.text
            final_url = str(root_resp.url)

    print(f"backend: {backend}")
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
