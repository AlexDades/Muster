from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.dependencies import RuntimeSettings, get_runtime_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsPatch(BaseModel):
    human_review_mode: Optional[bool] = None
    n_results: Optional[int] = None


@router.get("")
def get_settings(rs: RuntimeSettings = Depends(get_runtime_settings)) -> dict:
    return {
        "human_review_mode": rs.human_review_mode,
        "n_results": rs.n_results,
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
