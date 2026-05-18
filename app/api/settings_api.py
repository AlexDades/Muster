from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.dependencies import RuntimeSettings, get_runtime_settings
from app.config import settings as app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsPatch(BaseModel):
    human_review_mode: Optional[bool] = None
    n_results: Optional[int] = None


def _masked_email(addr: str) -> str:
    if not addr:
        return ""
    parts = addr.split("@")
    if len(parts) == 2:
        return parts[0][:3] + "***@" + parts[1]
    return addr[:3] + "***"


@router.get("")
def get_settings(rs: RuntimeSettings = Depends(get_runtime_settings)) -> dict:
    gmail_connected = bool(
        app_settings.gmail_use_inbox
        and app_settings.gmail_address
        and app_settings.gmail_app_password
    )
    return {
        "human_review_mode": rs.human_review_mode,
        "n_results": rs.n_results,
        "gmail_connected": gmail_connected,
        "gmail_address": _masked_email(app_settings.gmail_address),
        "allowed_senders": app_settings.allowed_senders,
        "poll_interval_seconds": app_settings.poll_interval_seconds,
    }


@router.patch("")
def update_settings(
    patch: SettingsPatch,
    rs: RuntimeSettings = Depends(get_runtime_settings),
) -> dict:
    if patch.human_review_mode is not None:
        rs.human_review_mode = patch.human_review_mode
    if patch.n_results is not None:
        rs.n_results = max(1, min(patch.n_results, 20))
    return {
        "human_review_mode": rs.human_review_mode,
        "n_results": rs.n_results,
    }
