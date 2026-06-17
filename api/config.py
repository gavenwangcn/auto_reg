from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.config_store import config_store
from core.skymail_auth import SkyMailAuthError, fetch_skymail_token, persist_skymail_token

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_KEYS = [
    "laoudo_auth",
    "laoudo_email",
    "laoudo_account_id",
    "yescaptcha_key",
    "twocaptcha_key",
    "default_executor",
    "default_captcha_solver",
    "duckmail_api_url",
    "duckmail_provider_url",
    "duckmail_bearer",
    "duckmail_domain",
    "duckmail_api_key",
    "freemail_api_url",
    "freemail_admin_token",
    "freemail_username",
    "freemail_password",
    "moemail_api_url",
    "moemail_api_key",
    "skymail_api_base",
    "skymail_email",
    "skymail_password",
    "skymail_token",
    "skymail_domain",
    "mail_provider",
    "maliapi_base_url",
    "maliapi_api_key",
    "maliapi_domain",
    "maliapi_auto_domain_strategy",
    "gptmail_base_url",
    "gptmail_api_key",
    "gptmail_domain",
    "opentrashmail_api_url",
    "opentrashmail_domain",
    "opentrashmail_password",
    "cfworker_api_url",
    "cfworker_admin_token",
    "cfworker_custom_auth",
    "cfworker_domain",
    "cfworker_domains",
    "cfworker_enabled_domains",
    "cfworker_subdomain",
    "cfworker_random_subdomain",
    "cfworker_fingerprint",
    "smstome_cookie",
    "smstome_country_slugs",
    "smstome_phone_attempts",
    "smstome_otp_timeout_seconds",
    "smstome_poll_interval_seconds",
    "smstome_sync_max_pages_per_country",
    "luckmail_base_url",
    "luckmail_api_key",
    "luckmail_email_type",
    "luckmail_domain",
    "cpa_api_url",
    "cpa_api_key",
    "cpa_cleanup_enabled",
    "cpa_cleanup_interval_minutes",
    "cpa_cleanup_threshold",
    "cpa_cleanup_concurrency",
    "cpa_cleanup_register_delay_seconds",
    "sub2api_api_url",
    "sub2api_api_key",
    "sub2api_group_ids",
    "team_manager_url",
    "team_manager_key",
    "codex_proxy_url",
    "codex_proxy_key",
    "codex_proxy_upload_type",
    "cliproxyapi_base_url",
    "cliproxyapi_management_key",
    "grok2api_url",
    "grok2api_app_key",
    "grok2api_pool",
    "grok2api_quota",
    "kiro_manager_path",
    "kiro_manager_exe",
]


class ConfigUpdate(BaseModel):
    data: dict


class SkyMailRefreshRequest(BaseModel):
    skymail_api_base: str = ""
    skymail_email: str = ""
    skymail_password: str = ""


@router.get("")
def get_config():
    all_cfg = config_store.get_all()
    if not all_cfg.get("mail_provider"):
        all_cfg["mail_provider"] = "luckmail"
    if not all_cfg.get("gptmail_base_url"):
        all_cfg["gptmail_base_url"] = "https://mail.chatgpt.org.uk"
    if not all_cfg.get("luckmail_base_url"):
        all_cfg["luckmail_base_url"] = "https://mails.luckyous.com/"
    # 只返回已知 key，未设置的返回空字符串
    return {k: all_cfg.get(k, "") for k in CONFIG_KEYS}


@router.put("")
def update_config(body: ConfigUpdate):
    # 只允许更新已知 key
    safe = {k: v for k, v in body.data.items() if k in CONFIG_KEYS}
    config_store.set_many(safe)
    return {"ok": True, "updated": list(safe.keys())}


@router.post("/skymail/refresh-token")
def refresh_skymail_token(body: SkyMailRefreshRequest | None = None):
    payload = body or SkyMailRefreshRequest()
    api_base = (payload.skymail_api_base or config_store.get("skymail_api_base", "")).strip()
    email = (payload.skymail_email or config_store.get("skymail_email", "")).strip()
    password = payload.skymail_password or config_store.get("skymail_password", "")
    if not api_base or not email or not password:
        raise HTTPException(400, "请先配置 SkyMail API Base、管理员邮箱和密码")
    try:
        token = fetch_skymail_token(api_base, email, password)
    except SkyMailAuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    persist_skymail_token(token)
    return {"ok": True, "skymail_token": token}
