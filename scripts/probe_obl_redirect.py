"""Debug OBL redirect chain and action extraction."""
import re
import urllib.request
from urllib.parse import urlencode

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
AUTH = "https://auth.openblocklabs.com"
CLIENT = "client_01K8YDZSSKDMK8GYTEHBAW4N4S"
CB = "https://dashboard.openblocklabs.com/auth/callback"
PAT = r'\\?"id\\?":\\?"([a-f0-9]{40})\\?"'


def extract(text: str):
    m = re.search(PAT, text)
    return m.group(1) if m else None


def curl_probe():
    from curl_cffi import requests

    s = requests.Session()
    s.impersonate = "chrome131"
    s.headers.update({"user-agent": UA})
    r = s.get(f"{AUTH}/sign-up", params={"redirect_uri": CB}, allow_redirects=True, timeout=30)
    print("=== curl_cffi sign-up ===")
    print("redirects", len(r.history))
    for i, h in enumerate(r.history):
        print(f"  {i} {h.status_code} {h.headers.get('location', '')[:140]}")
    print("final", r.url)
    print("len", len(r.text))
    print("action", extract(r.text))
    print("has Sign in", "Sign in" in r.text)
    sid = re.search(r"authorization_session_id=([^&]+)", str(r.url))
    if sid:
        root = f"{AUTH}/?{urlencode({'client_id': CLIENT, 'redirect_uri': CB, 'authorization_session_id': sid.group(1)})}"
        r2 = s.get(root, allow_redirects=True, timeout=30)
        print("=== curl_cffi root ===")
        print("redirects", len(r2.history))
        for i, h in enumerate(r2.history):
            print(f"  {i} {h.status_code} {h.headers.get('location', '')[:140]}")
        print("final", r2.url)
        print("len", len(r2.text))
        print("action", extract(r2.text))
    r3 = s.get(f"{AUTH}/sign-up", params={"redirect_uri": CB}, allow_redirects=False, timeout=30)
    print("=== curl_cffi no redirect ===", r3.status_code, (r3.headers.get("location") or "")[:160])


def urllib_probe():
    url = f"{AUTH}/sign-up?redirect_uri={CB}"
    req = urllib.request.Request(url, headers={"user-agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="ignore")
        print("=== urllib sign-up ===")
        print("final", resp.geturl())
        print("len", len(text))
        print("action", extract(text))
        print("has Sign in", "Sign in" in text)


if __name__ == "__main__":
    try:
        curl_probe()
    except ImportError as e:
        print("curl_cffi missing", e)
    urllib_probe()
