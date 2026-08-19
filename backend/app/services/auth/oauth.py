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

OAuthProvider = Literal["google", "github", "microsoft", "linkedin", "apple"]


class NormalisedOAuthProfile(TypedDict):
    email: str
    provider_id: str
    display_name: str


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


async def _google_profile_from_access_token(
    access_token: str,
    *,
    client: httpx.AsyncClient,
) -> NormalisedOAuthProfile:
    user_resp = await client.get(
        _GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if user_resp.status_code >= 400:
        raise OAuthError(f"Google userinfo failed: {user_resp.text}")
    return _normalise_google(user_resp.json())


async def verify_google_id_token(
    id_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    if not settings.GOOGLE_CLIENT_ID:
        raise OAuthError("Google OAuth is not configured")

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
        )
        if resp.status_code >= 400:
            raise OAuthError(f"Google id_token verification failed: {resp.text}")
        profile = resp.json()
        if profile.get("aud") != settings.GOOGLE_CLIENT_ID:
            raise OAuthError("Google id_token audience mismatch")
    finally:
        if owns_client:
            await client.aclose()

    return _normalise_google(profile)


async def fetch_google_profile_with_access_token(
    access_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        return await _google_profile_from_access_token(access_token, client=client)
    finally:
        if owns_client:
            await client.aclose()


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

        return await _google_profile_from_access_token(access_token, client=client)
    finally:
        if owns_client:
            await client.aclose()


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


async def _github_profile_from_access_token(
    access_token: str,
    *,
    client: httpx.AsyncClient,
) -> NormalisedOAuthProfile:
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
        emails_resp = await client.get(_GITHUB_EMAILS_URL, headers=headers)
        if emails_resp.status_code >= 400:
            raise OAuthError(
                "GitHub primary email is private and email scope was not granted"
            )
        for entry in emails_resp.json():
            if entry.get("primary") and entry.get("verified"):
                email = entry.get("email")
                break

    if not email:
        raise OAuthError("Could not resolve a verified GitHub email")

    return {
        "email": email.lower().strip(),
        "provider_id": str(user["id"]),
        "display_name": user.get("name") or user.get("login") or email.split("@", 1)[0],
    }


async def fetch_github_profile_with_access_token(
    access_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        return await _github_profile_from_access_token(access_token, client=client)
    finally:
        if owns_client:
            await client.aclose()


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

        return await _github_profile_from_access_token(access_token, client=client)
    finally:
        if owns_client:
            await client.aclose()


# ---------------------------------------------------------------------------
# Microsoft (Entra ID / Azure AD)
# ---------------------------------------------------------------------------

_MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_MICROSOFT_GRAPH_ME = "https://graph.microsoft.com/v1.0/me"
_MICROSOFT_JWKS_URL = (
    "https://login.microsoftonline.com/common/discovery/v2.0/keys"
)


async def _microsoft_profile_from_access_token(
    access_token: str,
    *,
    client: httpx.AsyncClient,
) -> NormalisedOAuthProfile:
    resp = await client.get(
        _MICROSOFT_GRAPH_ME,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if resp.status_code >= 400:
        raise OAuthError(f"Microsoft Graph /me failed: {resp.text}")
    profile = resp.json()
    email = (
        profile.get("mail")
        or profile.get("userPrincipalName")
        or ""
    ).lower().strip()
    sub = profile.get("id")
    if not email or not sub:
        raise OAuthError("Microsoft profile missing email or id")
    display = profile.get("displayName") or email.split("@", 1)[0]
    return {"email": email, "provider_id": str(sub), "display_name": display}


async def fetch_microsoft_profile_with_access_token(
    access_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        return await _microsoft_profile_from_access_token(access_token, client=client)
    finally:
        if owns_client:
            await client.aclose()


async def exchange_microsoft_code(
    code: str,
    redirect_uri: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    if not settings.AZURE_AD_CLIENT_ID or not settings.AZURE_AD_CLIENT_SECRET:
        raise OAuthError("Microsoft OAuth is not configured")
    payload = {
        "code": code,
        "client_id": settings.AZURE_AD_CLIENT_ID,
        "client_secret": settings.AZURE_AD_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        token_resp = await client.post(_MICROSOFT_TOKEN_URL, data=payload)
        if token_resp.status_code >= 400:
            raise OAuthError(f"Microsoft token exchange failed: {token_resp.text}")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise OAuthError("Microsoft token response missing access_token")
        return await _microsoft_profile_from_access_token(access_token, client=client)
    finally:
        if owns_client:
            await client.aclose()


async def verify_microsoft_id_token(
    id_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    if not settings.AZURE_AD_CLIENT_ID:
        raise OAuthError("Microsoft OAuth is not configured")
    from jose import jwt

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        jwks_resp = await client.get(_MICROSOFT_JWKS_URL)
        if jwks_resp.status_code >= 400:
            raise OAuthError("Microsoft JWKS fetch failed")
        claims = jwt.decode(
            id_token,
            jwks_resp.json(),
            algorithms=["RS256"],
            audience=settings.AZURE_AD_CLIENT_ID,
        )
    finally:
        if owns_client:
            await client.aclose()

    email = (claims.get("email") or claims.get("preferred_username") or "").lower().strip()
    sub = claims.get("oid") or claims.get("sub")
    if not email or not sub:
        raise OAuthError("Microsoft id_token missing email or subject")
    display = claims.get("name") or email.split("@", 1)[0]
    return {"email": email, "provider_id": str(sub), "display_name": display}


# ---------------------------------------------------------------------------
# LinkedIn (OpenID Connect)
# ---------------------------------------------------------------------------

_LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


async def _linkedin_profile_from_access_token(
    access_token: str,
    *,
    client: httpx.AsyncClient,
) -> NormalisedOAuthProfile:
    resp = await client.get(
        _LINKEDIN_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if resp.status_code >= 400:
        raise OAuthError(f"LinkedIn userinfo failed: {resp.text}")
    profile = resp.json()
    email = (profile.get("email") or "").lower().strip()
    sub = profile.get("sub")
    if not email or not sub:
        raise OAuthError("LinkedIn profile missing email or sub")
    display = profile.get("name") or email.split("@", 1)[0]
    return {"email": email, "provider_id": str(sub), "display_name": display}


async def fetch_linkedin_profile_with_access_token(
    access_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        return await _linkedin_profile_from_access_token(access_token, client=client)
    finally:
        if owns_client:
            await client.aclose()


async def exchange_linkedin_code(
    code: str,
    redirect_uri: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    if not settings.LINKEDIN_CLIENT_ID or not settings.LINKEDIN_CLIENT_SECRET:
        raise OAuthError("LinkedIn OAuth is not configured")
    payload = {
        "code": code,
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "client_secret": settings.LINKEDIN_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        token_resp = await client.post(_LINKEDIN_TOKEN_URL, data=payload)
        if token_resp.status_code >= 400:
            raise OAuthError(f"LinkedIn token exchange failed: {token_resp.text}")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise OAuthError("LinkedIn token response missing access_token")
        return await _linkedin_profile_from_access_token(access_token, client=client)
    finally:
        if owns_client:
            await client.aclose()


_LINKEDIN_JWKS_URL = "https://www.linkedin.com/oauth/openid/jwks"


async def verify_linkedin_id_token(
    id_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    if not settings.LINKEDIN_CLIENT_ID:
        raise OAuthError("LinkedIn OAuth is not configured")
    from jose import jwt

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        jwks_resp = await client.get(_LINKEDIN_JWKS_URL)
        if jwks_resp.status_code >= 400:
            raise OAuthError("LinkedIn JWKS fetch failed")
        claims = jwt.decode(
            id_token,
            jwks_resp.json(),
            algorithms=["RS256"],
            audience=settings.LINKEDIN_CLIENT_ID,
        )
    finally:
        if owns_client:
            await client.aclose()

    email = (claims.get("email") or "").lower().strip()
    sub = claims.get("sub")
    if not email or not sub:
        raise OAuthError("LinkedIn id_token missing email or subject")
    display = claims.get("name") or email.split("@", 1)[0]
    return {"email": email, "provider_id": str(sub), "display_name": display}


# ---------------------------------------------------------------------------
# Apple
# ---------------------------------------------------------------------------

_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"


async def verify_apple_id_token(
    id_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> NormalisedOAuthProfile:
    if not settings.APPLE_CLIENT_ID:
        raise OAuthError("Apple OAuth is not configured")
    from jose import jwt

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0)
    try:
        jwks_resp = await client.get(_APPLE_JWKS_URL)
        if jwks_resp.status_code >= 400:
            raise OAuthError("Apple JWKS fetch failed")
        claims = jwt.decode(
            id_token,
            jwks_resp.json(),
            algorithms=["RS256"],
            audience=settings.APPLE_CLIENT_ID,
        )
    finally:
        if owns_client:
            await client.aclose()

    email = (claims.get("email") or "").lower().strip()
    sub = claims.get("sub")
    if not sub:
        raise OAuthError("Apple id_token missing subject")
    if not email:
        raise OAuthError(
            "Apple did not share an email. Use a different sign-in method or "
            "revoke TalioCV in Apple ID settings and try again."
        )
    return {"email": email, "provider_id": str(sub), "display_name": email.split("@", 1)[0]}


__all__ = [
    "NormalisedOAuthProfile",
    "OAuthProvider",
    "exchange_github_code",
    "exchange_google_code",
    "exchange_linkedin_code",
    "exchange_microsoft_code",
    "fetch_github_profile_with_access_token",
    "fetch_google_profile_with_access_token",
    "fetch_linkedin_profile_with_access_token",
    "fetch_microsoft_profile_with_access_token",
    "verify_apple_id_token",
    "verify_google_id_token",
    "verify_linkedin_id_token",
    "verify_microsoft_id_token",
]
