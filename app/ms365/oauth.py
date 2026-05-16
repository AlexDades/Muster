"""OAuth 2.0 authorization-code flow for connecting a Microsoft 365 mailbox.

Phase 7 stub — the /authorize endpoint initiates the flow and /callback
receives the code. Full token exchange and storage will be completed when
the Azure AD app registration is finalized.
"""
from __future__ import annotations
import urllib.parse
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import RedirectResponse, JSONResponse
from app.config import settings

router = APIRouter(prefix="/ms365", tags=["ms365"])

_AUTHORIZE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
_SCOPES = (
    "https://graph.microsoft.com/Mail.ReadWrite "
    "https://graph.microsoft.com/Mail.Send "
    "offline_access"
)


@router.get("/authorize", include_in_schema=True)
def authorize():
    """Redirect the admin to Microsoft's OAuth consent page."""
    if not settings.ms365_client_id or not settings.ms365_tenant_id:
        return JSONResponse(
            {"error": "MS365_CLIENT_ID and MS365_TENANT_ID must be set before authorizing."},
            status_code=503,
        )
    params = {
        "client_id": settings.ms365_client_id,
        "response_type": "code",
        "redirect_uri": settings.ms365_redirect_uri,
        "scope": _SCOPES,
        "response_mode": "query",
    }
    url = _AUTHORIZE_URL.format(tenant=settings.ms365_tenant_id)
    return RedirectResponse(f"{url}?{urllib.parse.urlencode(params)}")


@router.get("/callback", include_in_schema=True)
def callback(code: Optional[str] = None, error: Optional[str] = None, error_description: Optional[str] = None):
    """Receive the authorization code from Microsoft."""
    if error:
        return JSONResponse({"error": error, "description": error_description}, status_code=400)
    if not code:
        return JSONResponse({"error": "No authorization code received."}, status_code=400)
    return JSONResponse({
        "message": "Authorization code received. Token exchange will be completed in a future update.",
        "next_step": "Exchange this code for an access token via POST to the token endpoint.",
    })


@router.get("/status", include_in_schema=True)
def ms365_status():
    """Returns the current M365 integration configuration status."""
    return {
        "configured": bool(settings.ms365_client_id and settings.ms365_tenant_id and settings.ms365_mailbox),
        "use_real_inbox": settings.ms365_use_real_inbox,
        "mailbox": settings.ms365_mailbox or None,
        "tenant_id": settings.ms365_tenant_id[:8] + "…" if settings.ms365_tenant_id else None,
    }
