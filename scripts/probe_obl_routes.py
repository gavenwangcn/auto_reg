"""Extract router state and route hints from OBL auth HTML."""
import re
import urllib.request
from urllib.parse import urlencode

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
CB = "https://dashboard.openblocklabs.com/auth/callback"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"user-agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def main():
    text = fetch(f"https://auth.openblocklabs.com/sign-up?redirect_uri={CB}")
    print("len", len(text))
    for label, pat in [
        ("sign-up route", r"sign-up"),
        ("sign-in route", r"\(sign-in\)"),
        ("router tree chunk", r"children.*?__PAGE__"),
    ]:
        print(label, len(re.findall(pat, text)))

    # Next.js flight chunks mentioning routes
    for m in re.finditer(r'"(sign-up|sign-in|password|__PAGE__[^"]*)"', text):
        s = m.group(1)
        if "PAGE" in s or s in ("sign-up", "sign-in", "password"):
            pass
    routes = re.findall(r'\\"(sign-up|sign-in|password)\\"', text)
    from collections import Counter

    print("route tokens", Counter(routes).most_common(10))

    # look for encoded router state in page
    for pat in [
        r"next-router-state-tree",
        r"routerStateTree",
        r"__next_router",
    ]:
        if pat in text:
            print("found marker", pat)

    # extract all 40-char action ids with nearby context
    for m in re.finditer(r'.{0,40}([a-f0-9]{40}).{0,40}', text):
        ctx = m.group(0).replace("\n", " ")
        if "id" in ctx.lower():
            print("action ctx:", ctx[:120])


if __name__ == "__main__":
    main()
