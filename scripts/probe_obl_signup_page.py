"""Test sign-up page fetch after auth session established."""
import re
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
CB = "https://dashboard.openblocklabs.com/auth/callback"
PAT = r'\\?"id\\?":\\?"([a-f0-9]{40})\\?"'


def fetch(opener, url: str, referer: str = None) -> tuple[str, str, int]:
    headers = {"user-agent": UA}
    if referer:
        headers["referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with opener.open(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="ignore")
        return resp.geturl(), text, resp.status


def main():
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    final1, text1, _ = fetch(
        opener, f"https://auth.openblocklabs.com/sign-up?redirect_uri={CB}"
    )
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(final1).query)
    print("step1 final", final1)
    print("step1 action", re.search(PAT, text1).group(1) if re.search(PAT, text1) else None)
    print("step1 sign-in count", text1.count("(sign-in)"), "sign-up count", text1.count('"sign-up"'))

    params = {
        "redirect_uri": qs["redirect_uri"][0],
        "client_id": qs["client_id"][0],
        "authorization_session_id": qs["authorization_session_id"][0],
    }
    sign_up_url = f"https://auth.openblocklabs.com/sign-up?{urllib.parse.urlencode(params)}"
    final2, text2, status2 = fetch(opener, sign_up_url, referer=final1)
    print("step2 status", status2, "final", final2)
    print("step2 len", len(text2))
    print("step2 action", re.search(PAT, text2).group(1) if re.search(PAT, text2) else None)
    print("step2 sign-in count", text2.count("(sign-in)"), "sign-up count", text2.count('"sign-up"'))


if __name__ == "__main__":
    main()
