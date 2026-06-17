"""Cloud Mail / SkyMail 公共 API Token 获取与刷新。"""
from __future__ import annotations

from typing import Any, Optional

import requests

from core.proxy_utils import build_requests_proxy_config


class SkyMailAuthError(RuntimeError):
    pass


def fetch_skymail_token(
    api_base: str,
    email: str,
    password: str,
    *,
    proxy: Optional[str] = None,
    timeout: int = 15,
) -> str:
    """POST /api/public/genToken 获取 Authorization Token。"""
    api = (api_base or "").rstrip("/")
    admin_email = (email or "").strip()
    admin_password = password or ""
    if not api:
        raise SkyMailAuthError("SkyMail API Base 未配置")
    if not admin_email or not admin_password:
        raise SkyMailAuthError("SkyMail 管理员邮箱或密码未配置")

    response = requests.post(
        f"{api}/api/public/genToken",
        json={"email": admin_email, "password": admin_password},
        headers={
            "accept": "application/json",
            "content-type": "application/json",
        },
        proxies=build_requests_proxy_config(proxy),
        timeout=timeout,
    )
    if response.status_code != 200:
        raise SkyMailAuthError(
            f"genToken 失败: HTTP {response.status_code} {response.text[:200]}"
        )

    data: dict[str, Any] = {}
    try:
        data = response.json()
    except Exception as exc:
        raise SkyMailAuthError(f"genToken 响应不是 JSON: {response.text[:200]}") from exc

    if data.get("code") != 200:
        message = data.get("message") or data
        raise SkyMailAuthError(f"genToken 失败: {message}")

    token = str((data.get("data") or {}).get("token") or "").strip()
    if not token:
        raise SkyMailAuthError(f"genToken 未返回 token: {data}")
    return token


def resolve_skymail_token(
    api_base: str,
    *,
    auth_token: str = "",
    email: str = "",
    password: str = "",
    force_refresh: bool = False,
    proxy: Optional[str] = None,
) -> str:
    """优先用账号密码刷新；否则回退到已保存 token。"""
    token = (auth_token or "").strip()
    if force_refresh or (email and password):
        return fetch_skymail_token(api_base, email, password, proxy=proxy)
    if token:
        return token
    raise SkyMailAuthError(
        "SkyMail 未配置 Token：请填写 skymail_email + skymail_password，或手动填写 skymail_token"
    )


def persist_skymail_token(token: str) -> None:
    from core.config_store import config_store

    config_store.set("skymail_token", token)
