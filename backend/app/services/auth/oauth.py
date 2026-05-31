"""Google + GitHub OAuth code exchanges.

Returns a normalised profile shape so the registration code path does
not need to know which provider it is talking to:

    {"email": str, "provider_id": str, "display_name": str}

Both implementations use the standard `Authorization Code` flow with
the back-channel ``client_id`` / ``client_secret`` from the platform
admin console.  The frontend redirects the user to the provider's authz
URL, the provider redirects back to a frontend route with ``?code=...``,
and the frontend POSTs that code to ``/api/auth/callback`` which calls
the matching ``exchange_*`` helper.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

import httpx

from app.config import settings
from app.services.auth.exceptions import OAuthError

OAuthProvider = Literal["google", "github"]


class NormalisedOAuthProfile(TypedDict):
    email: str
    provider_id: str
    display_name: str


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


async def exchange_google_code(
    code: str,
    redirect_uri: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise OAuthError("Google OAuth is not configured")

    payload = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        token_resp = await client.post(_GOOGLE_TOKEN_URL, data=payload)
        if token_resp.status_code >= 400:
            raise OAuthError(f"Google token exchange failed: {token_resp.text}")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise OAuthError("Google token response missing access_token")

        user_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code >= 400:
            raise OAuthError(f"Google userinfo failed: {user_resp.text}")
        profile = user_resp.json()
    finally:
        if owns_client:
            await client.aclose()

    return _normalise_google(profile)


def _normalise_google(profile: dict[str, Any]) -> NormalisedOAuthProfile:
    email = (profile.get("email") or "").lower().strip()
    sub = profile.get("sub")
    if not email or not sub:
        raise OAuthError("Google profile missing email or sub")
    if not profile.get("email_verified", False):
        raise OAuthError("Google account email is not verified")
    display = (
        profile.get("name")
        or profile.get("given_name")
        or email.split("@", 1)[0]
    )
    return {"email": email, "provider_id": str(sub), "display_name": display}


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


async def exchange_github_code(
    code: str,
    redirect_uri: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise OAuthError("GitHub OAuth is not configured")

    payload = {
        "code": code,
        "client_id": settings.GITHUB_CLIENT_ID,
        "client_secret": settings.GITHUB_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
    }
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        token_resp = await client.post(
            _GITHUB_TOKEN_URL,
            data=payload,
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code >= 400:
            raise OAuthError(f"GitHub token exchange failed: {token_resp.text}")
        token_body = token_resp.json()
        access_token = token_body.get("access_token")
        if not access_token:
            raise OAuthError(
                f"GitHub token response missing access_token: {token_body}"
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        user_resp = await client.get(_GITHUB_USER_URL, headers=headers)
        if user_resp.status_code >= 400:
            raise OAuthError(f"GitHub user fetch failed: {user_resp.text}")
        user = user_resp.json()

        email = user.get("email")
        if not email:
            # GitHub returns null when the user keeps email private — fall
            # back to the emails endpoint and pick the primary+verified row.
            emails_resp = await client.get(_GITHUB_EMAILS_URL, headers=headers)
            if emails_resp.status_code >= 400:
                raise OAuthError(
                    "GitHub primary email is private and email scope was not granted"
                )
            for entry in emails_resp.json():
                if entry.get("primary") and entry.get("verified"):
                    email = entry.get("email")
                    break
    finally:
        if owns_client:
            await client.aclose()

    if not email:
        raise OAuthError("Could not resolve a verified GitHub email")

    return {
        "email": email.lower().strip(),
        "provider_id": str(user["id"]),
        "display_name": user.get("name") or user.get("login") or email.split("@", 1)[0],
    }


__all__ = [
    "NormalisedOAuthProfile",
    "OAuthProvider",
    "exchange_github_code",
    "exchange_google_code",
]
