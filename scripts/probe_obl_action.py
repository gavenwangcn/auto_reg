import re
import urllib.request

url = (
    "https://auth.openblocklabs.com/sign-up?"
    "redirect_uri=https://dashboard.openblocklabs.com/auth/callback"
)
req = urllib.request.Request(
    url,
    headers={
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        )
    },
)
with urllib.request.urlopen(req, timeout=30) as resp:
    text = resp.read().decode("utf-8", errors="ignore")
    final_url = resp.geturl()

print("final_url", final_url)
print("len", len(text))

patterns = [
    (r'\\?"id\\?":\\?"([a-f0-9]{40})\\?"', "current_code_regex"),
    (r'"id":"([a-f0-9]{40})"', "plain_json_id"),
    (r'\\"id\\":\\"([a-f0-9]{40})\\"', "escaped_json_id"),
]
for pat, name in patterns:
    found = re.findall(pat, text)
    print(name, found[:5])

m = re.search(r"authorization_session_id=([^&]+)", final_url)
print("session_from_url", m.group(1) if m else None)
