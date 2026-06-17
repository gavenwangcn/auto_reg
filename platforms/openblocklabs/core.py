"""
OpenBlockLabs 自动注册 (WorkOS AuthKit)

流程:
  1. GET auth-relay/.../initiate_signup → authorization_session_id
  2. GET auth.openblocklabs.com/sign-up?... → 提取 next-action ID
  3. POST /sign-up (first_name/last_name/email/intent=sign-up) → __Host-state cookie
  4. GET /sign-up/password → 提取 next-action ID
  5. POST /sign-up/password (password/signals/...) → pendingAuthenticationToken from RSC body
  6. GET /email-verification → 提取 next-action ID
  7. POST /email-verification (code + pending_authentication_token) → 303 → callback
  8. GET dashboard.openblocklabs.com/auth/callback?code=... → wos-session cookie
  9. GET /api/create-personal-org → 完成

pip install curl_cffi requests
"""

import re, json, time, base64, random, string
from urllib.parse import urlencode, urlparse, parse_qs, urljoin, quote
from curl_cffi import requests as curl_requests
import requests as std_requests
from core.proxy_utils import build_requests_proxy_config

# ─── 配置 ───────────────────────────────────────────────────────────────────

AUTH_BASE = "https://auth.openblocklabs.com"
DASHBOARD_BASE = "https://dashboard.openblocklabs.com"
DASHBOARD_CALLBACK = f"{DASHBOARD_BASE}/auth/callback"
CLIENT_ID = "client_01K8YDZSSKDMK8GYTEHBAW4N4S"
WORKOS_AUTH_URL = "https://api.workos.com/user_management/authenticate"
# ────────────────────────────────────────────────────────────────────────────

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)


def _rand_password(n=14):
    chars = string.ascii_letters + string.digits + "!@#"
    pw = (
        random.choice(string.ascii_uppercase)
        + random.choice(string.ascii_lowercase)
        + random.choice(string.digits)
        + random.choice("!@#")
        + "".join(random.choices(chars, k=n - 4))
    )
    lst = list(pw)
    random.shuffle(lst)
    return "".join(lst)


def _build_multipart(
    fields: list, boundary: str = "----WebKitFormBoundaryPyAPI"
) -> tuple:
    body = ""
    for name, value in fields:
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
    body += f"--{boundary}--\r\n"
    return body.encode("utf-8"), f"multipart/form-data; boundary={boundary}"


def _make_signals() -> str:
    """生成伪造的 browser signals (base64 JSON)"""
    data = {
        "createdAtMs": int(time.time() * 1000),
        "timezone": "Asia/Shanghai",
        "language": "zh-CN",
        "hardwareConcurrency": 8,
        "webdriver": False,
        "userAgent": UA,
        "appVersion": UA.split("Mozilla/5.0 ")[1] if "Mozilla" in UA else UA,
        "platform": "MacIntel",
        "screen": {
            "width": 1470,
            "height": 956,
            "availWidth": 1470,
            "availHeight": 956,
            "windowOuterWidth": 1470,
            "windowOuterHeight": 956,
            "colorDepth": 24,
            "pixelDepth": 24,
        },
        "maxTouchPoints": 0,
        "deviceMemory": 8,
        "devicePixelRatio": 2,
        "pluginsLength": 5,
        "mimeTypesCount": 2,
        "webdriver": False,
        "playwrightDetected": False,
        "phantomDetected": False,
        "nightmareDetected": False,
        "seleniumDetected": False,
        "puppeteerDetected": False,
        "submittedAtMs": int(time.time() * 1000) + 5000,
    }
    return base64.b64encode(json.dumps(data).encode()).decode()


# ─── Register ────────────────────────────────────────────────────────────────
class OpenBlockLabsRegister:
    def __init__(self, proxy: str = None):
        self.s = curl_requests.Session()
        self.s.impersonate = "chrome131"
        if proxy:
            self.s.proxies = build_requests_proxy_config(proxy)
        self.s.headers.update(
            {
                "user-agent": UA,
                "accept-language": "zh-CN,zh;q=0.9",
            }
        )
        self.authorization_session_id = None
        self._action_id = None
        self._landing_url = None

    def log(self, msg):
        print(f"[REG] {msg}")

    def _get_headers(self, referer: str = None, accept: str = None) -> dict:
        h = {
            "accept": accept
            or "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }
        if referer:
            h["referer"] = referer
        return h

    def _extract_action_id(self, text: str) -> str:
        patterns = (
            r'\\?"id\\?":\\?"([a-f0-9]{40})\\?"',
            r'\\"id\\":\\"([a-f0-9]{40})\\"',
            r'"id":"([a-f0-9]{40})"',
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _normalize_auth_landing_url(self, url: str) -> str:
        """curl_cffi 常落在 /sign-up?client_id=...，需改成 /?client_id=... 才有 action ID。"""
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if not parsed.path.rstrip("/").endswith("/sign-up") or not qs.get("client_id"):
            return url
        query = urlencode(
            {
                "client_id": qs["client_id"][0],
                "redirect_uri": qs.get("redirect_uri", [DASHBOARD_CALLBACK])[0],
                "authorization_session_id": qs.get("authorization_session_id", [""])[0],
            }
        )
        return f"{AUTH_BASE}/?{query}"

    def _sync_session_from_url(self, url: str) -> None:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        session_id = qs.get("authorization_session_id", [None])[0]
        if session_id:
            self.authorization_session_id = session_id

    def _follow_auth_redirects(self, start_url: str, params: dict = None):
        """手动跟随重定向，把 /sign-up?client_id=... 规范到 /?client_id=...。"""
        url = start_url
        query_params = params
        for _ in range(15):
            r = self.s.get(
                url,
                params=query_params,
                headers=self._get_headers(),
                allow_redirects=False,
            )
            query_params = None
            if r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("location", "")
                if not loc:
                    return r
                url = self._normalize_auth_landing_url(urljoin(str(r.url), loc))
                continue
            return r
        return r

    def _copy_cookies_from_session(self, other) -> None:
        for cookie in other.cookies:
            self.s.cookies.set(
                cookie.name,
                cookie.value,
                domain=cookie.domain,
                path=cookie.path,
            )

    def _fetch_signup_via_stdlib(self) -> bool:
        """curl_cffi 拿不到 action 时，用标准 requests 拉注册页并同步 cookie。"""
        self.log("  回退 std requests GET /sign-up")
        std_s = std_requests.Session()
        if self.s.proxies:
            std_s.proxies.update(self.s.proxies)
        std_s.headers.update(
            {
                "user-agent": UA,
                "accept-language": "zh-CN,zh;q=0.9",
            }
        )
        r = std_s.get(
            f"{AUTH_BASE}/sign-up",
            params={"redirect_uri": DASHBOARD_CALLBACK},
            allow_redirects=True,
            timeout=30,
        )
        final_url = str(r.url)
        self._sync_session_from_url(final_url)
        self._copy_cookies_from_session(std_s)
        self._action_id = self._extract_action_id(r.text)
        self._landing_url = final_url
        self.log(f"  std final_url={final_url[:120]}...")
        if self._action_id:
            self.log(f"  std action={self._action_id[:16]}...")
        else:
            self.log(f"  std 仍未解析到 action, html_len={len(r.text)}")
        return bool(self._action_id)

    def _auth_params(self) -> dict:
        return {
            "client_id": CLIENT_ID,
            "redirect_uri": DASHBOARD_CALLBACK,
            "authorization_session_id": self.authorization_session_id,
        }

    def _auth_url(self, path: str = "/") -> str:
        if path == "/":
            return f"{AUTH_BASE}/?{urlencode(self._auth_params())}"
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{AUTH_BASE}{path}?{urlencode(self._auth_params())}"

    def _page_search_params(self) -> str:
        return json.dumps(
            {
                "redirect_uri": DASHBOARD_CALLBACK,
                "authorization_session_id": self.authorization_session_id,
            },
            separators=(",", ":"),
        )

    def _encode_router_state(self, tree) -> str:
        return quote(json.dumps(tree, separators=(",", ":")), safe="")

    def _router_state_sign_in_page(self) -> str:
        qs = self._page_search_params()
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
                                    {
                                        "children": [
                                            f"__PAGE__?{qs}",
                                            {},
                                            None,
                                            None,
                                        ]
                                    },
                                    None,
                                    None,
                                ]
                            },
                            None,
                            None,
                        ]
                    },
                    None,
                    None,
                ]
            },
            None,
            None,
            True,
        ]
        return self._encode_router_state(tree)

    def _router_state_sign_up_password(self) -> str:
        qs = self._page_search_params()
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
                                    "sign-up",
                                    {
                                        "children": [
                                            "password",
                                            {
                                                "children": [
                                                    f"__PAGE__?{qs}",
                                                    {},
                                                    None,
                                                    None,
                                                ]
                                            },
                                            None,
                                            None,
                                        ]
                                    },
                                    None,
                                    None,
                                ]
                            },
                            None,
                            None,
                        ]
                    },
                    None,
                    None,
                ]
            },
            None,
            None,
            True,
        ]
        return self._encode_router_state(tree)

    def _router_state_email_verification(self) -> str:
        qs = self._page_search_params()
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
                                    "(fixed-layout)",
                                    {
                                        "children": [
                                            "email-verification",
                                            {
                                                "children": [
                                                    f"__PAGE__?{qs}",
                                                    {},
                                                    None,
                                                    None,
                                                ]
                                            },
                                            None,
                                            None,
                                        ]
                                    },
                                    None,
                                    None,
                                ]
                            },
                            None,
                            None,
                        ]
                    },
                    None,
                    None,
                ]
            },
            None,
            None,
            True,
        ]
        return self._encode_router_state(tree)

    def _is_signup_password_redirect(self, resp) -> bool:
        redirect = resp.headers.get("x-action-redirect", "") or ""
        body = resp.text or ""
        return "sign-up/password" in redirect or "sign-up/password" in body

    def _post_action(self, url: str, fields: list, router_state: str):
        all_fields = fields + [("0", '["$K1"]')]
        body, ct = _build_multipart(all_fields)
        return self.s.post(
            url,
            data=body,
            headers={
                "accept": "text/x-component",
                "content-type": ct,
                "origin": AUTH_BASE,
                "referer": url,
                "next-action": self._action_id,
                "next-router-state-tree": router_state,
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            },
            allow_redirects=False,
        )

    def _sync_session_from_response(self, r) -> str:
        final_url = str(r.url)
        self._sync_session_from_url(final_url)
        if not self.authorization_session_id:
            for rr in r.history:
                loc = rr.headers.get("location", "")
                m = re.search(r"authorization_session_id=([^&]+)", loc)
                if m:
                    self.authorization_session_id = m.group(1)
                    break
        return final_url

    def _fetch_auth_root_page(self) -> bool:
        """补拉 /?client_id=... 页面；禁止自动重定向，避免再次跳回 /sign-up。"""
        if not self.authorization_session_id:
            return False
        root_query = urlencode(
            {
                "client_id": CLIENT_ID,
                "redirect_uri": DASHBOARD_CALLBACK,
                "authorization_session_id": self.authorization_session_id,
            }
        )
        root_url = f"{AUTH_BASE}/?{root_query}"
        self.log("  补拉 GET /?client_id=... (no redirect)")
        r = self.s.get(
            root_url,
            headers=self._get_headers(),
            allow_redirects=False,
        )
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("location", "")
            self.log(f"  根路径返回 {r.status_code} -> {loc[:120]}")
            norm = self._normalize_auth_landing_url(urljoin(root_url, loc))
            if norm != urljoin(root_url, loc):
                r = self.s.get(
                    norm,
                    headers=self._get_headers(),
                    allow_redirects=False,
                )
        if r.status_code == 200:
            self._sync_session_from_response(r)
            self._action_id = self._extract_action_id(r.text)
            self._landing_url = root_url
            if self._action_id:
                self.log(f"  根路径页面 action={self._action_id[:16]}...")
            else:
                self.log(f"  根路径仍未解析到 action, html_len={len(r.text)}")
            return bool(self._action_id)
        self.log(f"  根路径 HTTP {r.status_code}")
        return False

    def step1_initiate_signup(self) -> bool:
        """GET auth.openblocklabs.com/sign-up → authorization_session_id + action ID"""
        self.log("Step1: GET /sign-up")
        r = None
        for attempt in range(5):
            r = self._follow_auth_redirects(
                f"{AUTH_BASE}/sign-up",
                params={"redirect_uri": DASHBOARD_CALLBACK},
            )
            if r.status_code == 200:
                break
            self.log(f"  CF拦截 (status={r.status_code}), 重试 {attempt + 1}/5...")
            time.sleep(2)
        final_url = self._sync_session_from_response(r)
        if "/sign-up" in urlparse(final_url).path and "client_id" in final_url:
            norm = self._normalize_auth_landing_url(final_url)
            self.log(f"  规范化 landing URL -> {norm[:120]}...")
            r = self.s.get(
                norm,
                headers=self._get_headers(),
                allow_redirects=False,
            )
            if r.status_code == 200:
                final_url = str(r.url)
                self._sync_session_from_response(r)
        self._action_id = self._extract_action_id(r.text)
        self.log(f"  final_url={final_url[:120]}...")
        self.log(
            f"  session_id={self.authorization_session_id}, action={self._action_id and self._action_id[:16]}..."
        )
        if not self._action_id:
            self.log(f"  首次页面未解析到 next-action ID, html_len={len(r.text)}")
            if not self._fetch_auth_root_page():
                self._fetch_signup_via_stdlib()
        self._landing_url = self._landing_url or final_url
        if self._landing_url and urlparse(self._landing_url).path.rstrip("/").endswith(
            "/sign-up"
        ):
            self._landing_url = self._normalize_auth_landing_url(self._landing_url)
        return bool(self.authorization_session_id and self._action_id)

    def step2_get_signup_page(self) -> bool:
        """已在 step1 完成，直接返回 True"""
        return bool(self.authorization_session_id)

    def step3_submit_signup(self, email: str, first_name: str, last_name: str) -> bool:
        """POST auth landing page (sign-in route + intent=sign-up) → sign-up/password"""
        self.log(f"Step3: POST signup email={email}")
        url = self._landing_url or self._auth_url("/")
        resp = self._post_action(
            url,
            [
                ("1_browser_supports_passkeys", "true"),
                ("1_signals", ""),
                ("1_first_name", first_name),
                ("1_last_name", last_name),
                ("1_email", email),
                ("1_intent", "sign-up"),
                ("1_redirect_uri", DASHBOARD_CALLBACK),
                ("1_authorization_session_id", self.authorization_session_id),
                ("1_client_id", CLIENT_ID),
            ],
            self._router_state_sign_in_page(),
        )
        redirect = resp.headers.get("x-action-redirect", "")
        self.log(f"  -> {resp.status_code}")
        if redirect:
            self.log(f"  x-action-redirect: {redirect[:120]}")
        if resp.status_code != 303 and not self._is_signup_password_redirect(resp):
            self.log(f"  body[:300]: {(resp.text or '')[:300]}")
        return resp.status_code == 303 or self._is_signup_password_redirect(resp)

    def step4_get_password_page(self) -> bool:
        """GET /sign-up/password → 提取 next-action ID"""
        self.log("Step4: GET /sign-up/password")
        url = self._auth_url("/sign-up/password")
        r = self.s.get(
            url,
            headers=self._get_headers(referer=self._landing_url or self._auth_url("/")),
            allow_redirects=True,
        )
        self.log(f"  -> {r.status_code}")
        action = self._extract_action_id(r.text)
        if action:
            self._action_id = action
            self.log(f"  action={action[:16]}...")
        return r.status_code == 200

    def step5_submit_password(
        self, email: str, password: str, first_name: str, last_name: str
    ) -> str:
        """POST /sign-up/password → RSC body 包含 pendingAuthenticationToken"""
        self.log("Step5: POST /sign-up/password")
        url = self._auth_url("/sign-up/password")
        resp = self._post_action(
            url,
            [
                ("1_browser_supports_passkeys", "true"),
                ("1_signals", _make_signals()),
                ("1_first_name", first_name),
                ("1_last_name", last_name),
                ("1_email", email),
                ("1_password", password),
                ("1_intent", "sign-up"),
                ("1_redirect_uri", DASHBOARD_CALLBACK),
                ("1_authorization_session_id", self.authorization_session_id),
                ("1_client_id", CLIENT_ID),
            ],
            self._router_state_sign_up_password(),
        )
        self.log(f"  -> {resp.status_code}")
        body = resp.text
        m = re.search(r'"pendingAuthenticationToken"\s*:\s*"([^"]+)"', body)
        token = m.group(1) if m else None
        self.log(f"  pendingAuthenticationToken={token}")
        if not token:
            self.log(f"  body[:600]: {body[:600]}")
        return token

    def step6_get_email_verification_page(self) -> bool:
        """GET /email-verification → 提取 next-action ID"""
        self.log("Step6: GET /email-verification")
        url = self._auth_url("/email-verification")
        r = self.s.get(
            url,
            headers=self._get_headers(referer=self._auth_url("/sign-up/password")),
            allow_redirects=True,
        )
        self.log(f"  -> {r.status_code}")
        action = self._extract_action_id(r.text)
        if action:
            self._action_id = action
            self.log(f"  action={action[:16]}...")
        return r.status_code == 200

    def step7_submit_otp(self, email: str, code: str, pending_auth_token: str) -> str:
        """POST /email-verification → 303 → dashboard/auth/callback?code=..."""
        self.log(f"Step7: POST /email-verification code={code}")
        url = self._auth_url("/email-verification")
        fields = [
            ("1_code", code),
            ("1_redirect_uri", DASHBOARD_CALLBACK),
            ("1_authorization_session_id", self.authorization_session_id),
            ("1_email", email),
            ("1_client_id", CLIENT_ID),
        ]
        if pending_auth_token:
            fields.append(("1_pending_authentication_token", pending_auth_token))
        fields.append(("0", '["$K1"]'))
        body, ct = _build_multipart(fields)
        resp = self.s.post(
            url,
            data=body,
            headers={
                "accept": "text/x-component",
                "content-type": ct,
                "origin": AUTH_BASE,
                "referer": url,
                "next-action": self._action_id,
                "next-router-state-tree": self._router_state_email_verification(),
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            },
            allow_redirects=False,
        )
        self.log(f"  -> {resp.status_code}")
        redirect = resp.headers.get("x-action-redirect", "")
        self.log(f"  x-action-redirect: {redirect[:120]}")
        if not redirect:
            self.log(f"  body[:400]: {resp.text[:400]}")
        m = re.search(r"code=([^&]+)", redirect)
        auth_code = m.group(1) if m else None
        self.log(f"  auth_code={auth_code}")
        return auth_code

    def step7b_exchange_workos_tokens(self, auth_code: str) -> dict:
        """POST WorkOS authenticate → access_token / refresh_token / authkit_authorization_code"""
        self.log("Step7b: POST WorkOS /user_management/authenticate")
        payload = {
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": auth_code,
        }
        r = self.s.post(
            WORKOS_AUTH_URL,
            json=payload,
            headers={"Content-Type": "application/json", "accept": "application/json"},
        )
        self.log(f"  -> {r.status_code}")
        if r.status_code != 200:
            self.log(f"  body[:400]: {r.text[:400]}")
            return {}
        try:
            data = r.json()
        except json.JSONDecodeError:
            self.log(f"  invalid JSON: {r.text[:200]}")
            return {}
        user = data.get("user") or {}
        tokens = {
            "access_token": data.get("access_token") or "",
            "refresh_token": data.get("refresh_token") or "",
            "authkit_authorization_code": data.get("authkit_authorization_code") or "",
            "user_id": user.get("id") or "",
            "organization_id": data.get("organization_id") or "",
        }
        self.log(
            f"  access_token={'Y' if tokens['access_token'] else 'N'} "
            f"refresh_token={'Y' if tokens['refresh_token'] else 'N'} "
            f"authkit_code={'Y' if tokens['authkit_authorization_code'] else 'N'}"
        )
        return tokens

    def step8_exchange_callback(self, auth_code: str) -> str:
        """GET dashboard/auth/callback?code=... → wos-session cookie"""
        self.log("Step8: GET /auth/callback")
        url = f"{DASHBOARD_CALLBACK}?code={auth_code}"
        r = self.s.get(
            url, headers=self._get_headers(referer=AUTH_BASE), allow_redirects=True
        )
        self.log(f"  -> {r.status_code} final={str(r.url)[:80]}")
        for c in self.s.cookies.jar:
            if "wos-session" in c.name:
                return c.value
        return None

    def step9_create_personal_org(self, access_token: str = None) -> bool:
        """GET /api/create-personal-org → 完成组织创建"""
        self.log("Step9: GET /api/create-personal-org")
        headers = self._get_headers(referer=f"{DASHBOARD_BASE}/")
        if access_token:
            headers["authorization"] = f"Bearer {access_token}"
        r = self.s.get(
            f"{DASHBOARD_BASE}/api/create-personal-org",
            headers=headers,
            allow_redirects=True,
        )
        self.log(f"  -> {r.status_code} final={str(r.url)[:80]}")
        return r.status_code == 200

    def register(
        self,
        email: str = None,
        password: str = None,
        first_name: str = None,
        last_name: str = None,
        account_id: str = None,
        otp_callback=None,
    ) -> dict:
        if not password:
            password = _rand_password()
        if not first_name:
            first_name = "".join(
                random.choices(string.ascii_lowercase, k=5)
            ).capitalize()
        if not last_name:
            last_name = random.choice(string.ascii_uppercase)

        if not self.step1_initiate_signup():
            return {"success": False, "error": "initiate_signup failed"}
        if not self.step2_get_signup_page():
            return {"success": False, "error": "get_signup_page failed"}
        if not self.step3_submit_signup(email, first_name, last_name):
            return {"success": False, "error": "submit_signup failed"}
        if not self.step4_get_password_page():
            return {"success": False, "error": "get_password_page failed"}

        pending_token = self.step5_submit_password(
            email, password, first_name, last_name
        )
        if pending_token is None:
            return {
                "success": False,
                "error": "submit_password failed (email may already be registered)",
            }

        if not self.step6_get_email_verification_page():
            return {"success": False, "error": "get_email_verification_page failed"}

        if not otp_callback:
            raise RuntimeError("otp_callback is required")
        otp = otp_callback()
        if not otp:
            return {"success": False, "error": "OTP timeout"}

        auth_code = self.step7_submit_otp(email, otp, pending_token)
        if not auth_code:
            return {"success": False, "error": "submit_otp failed / no auth_code"}

        tokens = self.step7b_exchange_workos_tokens(auth_code)
        access_token = tokens.get("access_token") or ""
        refresh_token = tokens.get("refresh_token") or ""
        if not access_token and not refresh_token:
            return {
                "success": False,
                "error": "workos token exchange failed / no access or refresh token",
            }

        callback_code = tokens.get("authkit_authorization_code") or auth_code
        session_token = self.step8_exchange_callback(callback_code)
        if not session_token:
            self.log("  wos-session 未获取，继续使用 Bearer access_token 完成后续步骤")

        self.step9_create_personal_org(access_token=access_token or None)

        result = {
            "success": True,
            "email": email,
            "password": password,
            "wos_session": session_token or "",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": tokens.get("user_id") or "",
            "organization_id": tokens.get("organization_id") or "",
        }
        self.log(f"注册成功: {email}")
        return result
