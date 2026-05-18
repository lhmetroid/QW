"""
Gmail and Outlook OAuth2 authorization flows.
Ported from other/KnowledgeBase/BackEnd/app/services/gmail_oauth.py
            and other/KnowledgeBase/BackEnd/app/services/outlook_oauth.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Any
from urllib.parse import urlencode

import httpx


# ── Gmail OAuth ──────────────────────────────────────────────────────────────

_GMAIL_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GMAIL_DEFAULT_SCOPE = "openid email profile https://www.googleapis.com/auth/gmail.readonly"


def build_gmail_authorize_url(account: dict[str, Any], *, state: str | None = None) -> dict[str, str]:
    client_id = account.get("oauth_client_id", "").strip()
    redirect_uri = account.get("oauth_redirect_uri", "").strip()
    scope = account.get("oauth_scope", "").strip() or _GMAIL_DEFAULT_SCOPE
    if not client_id or not redirect_uri:
        raise ValueError("Gmail OAuth2 缺少 client_id 或 redirect_uri")
    state = state or token_urlsafe(24)
    qs = urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": scope,
        "access_type": "offline", "prompt": "consent", "state": state,
    })
    return {"authorize_url": f"{_GMAIL_AUTH_URL}?{qs}", "state": state}


async def exchange_gmail_code(account: dict[str, Any], code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(_GMAIL_TOKEN_URL, data={
            "client_id": account["oauth_client_id"].strip(),
            "client_secret": account["oauth_client_secret"].strip(),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": account["oauth_redirect_uri"].strip(),
        })
        r.raise_for_status()
        return _parse_token_response(r.json(), account.get("oauth_refresh_token", ""))


async def refresh_gmail_token(account: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(_GMAIL_TOKEN_URL, data={
            "client_id": account["oauth_client_id"].strip(),
            "client_secret": account["oauth_client_secret"].strip(),
            "refresh_token": account["oauth_refresh_token"].strip(),
            "grant_type": "refresh_token",
        })
        r.raise_for_status()
        return _parse_token_response(r.json(), account.get("oauth_refresh_token", ""))


# ── Outlook OAuth ─────────────────────────────────────────────────────────────

_OUTLOOK_AUTH_BASE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
_OUTLOOK_TOKEN_BASE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


def build_outlook_authorize_url(account: dict[str, Any], *, state: str | None = None) -> dict[str, str]:
    client_id = account.get("oauth_client_id", "").strip()
    redirect_uri = account.get("oauth_redirect_uri", "").strip()
    tenant = account.get("oauth_tenant_id", "common").strip() or "common"
    scope = account.get("oauth_scope", "").strip()
    if not client_id or not redirect_uri:
        raise ValueError("Outlook OAuth2 缺少 client_id 或 redirect_uri")
    state = state or token_urlsafe(24)
    qs = urlencode({
        "client_id": client_id, "response_type": "code",
        "redirect_uri": redirect_uri, "response_mode": "query",
        "scope": scope, "state": state,
    })
    return {"authorize_url": f"{_OUTLOOK_AUTH_BASE.format(tenant=tenant)}?{qs}", "state": state}


async def exchange_outlook_code(account: dict[str, Any], code: str) -> dict[str, Any]:
    tenant = account.get("oauth_tenant_id", "common").strip() or "common"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(_OUTLOOK_TOKEN_BASE.format(tenant=tenant), data={
            "client_id": account["oauth_client_id"].strip(),
            "client_secret": account["oauth_client_secret"].strip(),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": account["oauth_redirect_uri"].strip(),
            "scope": account.get("oauth_scope", "").strip(),
        })
        r.raise_for_status()
        return _parse_token_response(r.json(), account.get("oauth_refresh_token", ""))


async def refresh_outlook_token(account: dict[str, Any]) -> dict[str, Any]:
    tenant = account.get("oauth_tenant_id", "common").strip() or "common"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(_OUTLOOK_TOKEN_BASE.format(tenant=tenant), data={
            "client_id": account["oauth_client_id"].strip(),
            "client_secret": account["oauth_client_secret"].strip(),
            "grant_type": "refresh_token",
            "refresh_token": account["oauth_refresh_token"].strip(),
            "redirect_uri": account["oauth_redirect_uri"].strip(),
            "scope": account.get("oauth_scope", "").strip(),
        })
        r.raise_for_status()
        return _parse_token_response(r.json(), account.get("oauth_refresh_token", ""))


# ── Shared helpers ────────────────────────────────────────────────────────────

def _parse_token_response(payload: dict, fallback_refresh: str) -> dict[str, Any]:
    expires_in = int(payload.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return {
        "access_token": payload.get("access_token", ""),
        "refresh_token": payload.get("refresh_token") or fallback_refresh,
        "expires_at": expires_at.isoformat(),
    }
