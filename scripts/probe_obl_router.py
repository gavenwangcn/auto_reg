"""Find router-state-tree patterns in OBL auth HTML."""
import json
import re
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
CB = "https://dashboard.openblocklabs.com/auth/callback"


def fetch(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"user-agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.geturl(), resp.read().decode("utf-8", errors="ignore")


def main():
    final_url, text = fetch(
        f"https://auth.openblocklabs.com/sign-up?redirect_uri={CB}"
    )
    print("final_url", final_url)

    # __PAGE__ with query in flight data
    for m in re.finditer(r"__PAGE__\?\\?\{[^\"]{20,200}", text):
        print("page_qs:", m.group(0)[:200])

    # search-params in JSON-ish chunks
    for m in re.finditer(r"searchParams[^\\]{0,120}", text):
        print("searchParams:", m.group(0)[:120])

    # try to find buildRouterState or similar
    for pat in [
        r"routerStateTree[^\n]{0,200}",
        r"\\u005b\\u0022\\u0022",  # encoded [
    ]:
        m = re.search(pat, text)
        if m:
            print("match", m.group(0)[:200])

    sid = re.search(r"authorization_session_id=([^&]+)", final_url)
    sid = sid.group(1) if sid else "TEST"
    page_qs = json.dumps(
        {"redirect_uri": CB, "authorization_session_id": sid}, separators=(",", ":")
    )
    tree = [
        "",
        {
            "children": [
                "(main)",
                {
                    "children": [
                        "(root)",
                        {
                            "children": [
                                "(sign-in)",
                                {"children": [f"__PAGE__?{page_qs}", {}]},
                            ]
                        },
                    ]
                },
            ]
        },
    ]
    encoded = urllib.parse.quote(json.dumps(tree, separators=(",", ":")))
    print("built sign-in router len", len(encoded))
    print("built preview", encoded[:180])


if __name__ == "__main__":
    main()
