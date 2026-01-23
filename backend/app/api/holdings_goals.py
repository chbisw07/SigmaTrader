from __future__ import annotations

from typing import Annotated, List

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models import User
from app.pydantic_compat import PYDANTIC_V2
from app.schemas.holdings import (
    HoldingGoalImportMapping,
    HoldingGoalImportPresetCreate,
    HoldingGoalImportPresetRead,
    HoldingGoalImportRequest,
    HoldingGoalImportResult,
    HoldingGoalRead,
    HoldingGoalReviewActionRequest,
    HoldingGoalReviewActionResponse,
    HoldingGoalReviewRead,
    HoldingGoalUpsert,
)
from app.services.holdings_goals import (
    apply_review_action,
    create_preset,
    delete_goal,
    delete_preset,
    import_goals,
    list_goals,
    list_reviews,
    list_presets,
    upsert_goal,
)

router = APIRouter()


@router.get("/", response_model=List[HoldingGoalRead])
def list_holding_goals(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    broker_name: str | None = Query(None, min_length=1),
) -> List[HoldingGoalRead]:
    broker = broker_name.strip().lower() if broker_name else None
    return list_goals(db, user_id=user.id, broker_name=broker)


@router.put("/", response_model=HoldingGoalRead)
def upsert_holding_goal(
    payload: HoldingGoalUpsert,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> HoldingGoalRead:
    try:
        goal = upsert_goal(db, user_id=user.id, payload=payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return goal


@router.delete("/", response_model=dict)
def delete_holding_goal(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    symbol: str = Query(..., min_length=1),
    exchange: str | None = Query(None),
    broker_name: str | None = Query(None),
) -> dict:
    try:
        removed = delete_goal(
            db,
            user_id=user.id,
            symbol=symbol,
            exchange=exchange,
            broker_name=broker_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holding goal not found.",
        )
    return {"deleted": True}


@router.post("/import", response_model=HoldingGoalImportResult)
def import_holding_goals(
    payload: HoldingGoalImportRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> HoldingGoalImportResult:
    return import_goals(db, user_id=user.id, payload=payload)


@router.post("/review-actions", response_model=HoldingGoalReviewActionResponse)
def apply_holding_goal_review_action(
    payload: HoldingGoalReviewActionRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> HoldingGoalReviewActionResponse:
    try:
        goal, review = apply_review_action(db, user_id=user.id, payload=payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return HoldingGoalReviewActionResponse(goal=goal, review=review)


@router.get("/reviews", response_model=List[HoldingGoalReviewRead])
def list_holding_goal_reviews(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    symbol: str = Query(..., min_length=1),
    exchange: str | None = Query(None),
    broker_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> List[HoldingGoalReviewRead]:
    try:
        return list_reviews(
            db,
            user_id=user.id,
            broker_name=broker_name,
            symbol=symbol,
            exchange=exchange,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/presets", response_model=List[HoldingGoalImportPresetRead])
def list_goal_import_presets(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> List[HoldingGoalImportPresetRead]:
    presets = list_presets(db, user_id=user.id)
    out: list[HoldingGoalImportPresetRead] = []
    for preset in presets:
        raw_mapping = json.loads(preset.mapping_json or "{}")
        if PYDANTIC_V2:
            mapping = HoldingGoalImportMapping.model_validate(raw_mapping)
        else:  # pragma: no cover - Pydantic v1
            mapping = HoldingGoalImportMapping.parse_obj(raw_mapping)
        out.append(
            HoldingGoalImportPresetRead(
                id=preset.id,
                name=preset.name,
                mapping=mapping,
                created_at=preset.created_at,
                updated_at=preset.updated_at,
            )
        )
    return out


@router.post("/presets", response_model=HoldingGoalImportPresetRead)
def create_goal_import_preset(
    payload: HoldingGoalImportPresetCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> HoldingGoalImportPresetRead:
    try:
        preset = create_preset(db, user_id=user.id, payload=payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return HoldingGoalImportPresetRead(
        id=preset.id,
        name=preset.name,
        mapping=payload.mapping,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


@router.delete("/presets/{preset_id}", response_model=dict)
def delete_goal_import_preset(
    preset_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    removed = delete_preset(db, user_id=user.id, preset_id=preset_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset not found.",
        )
    return {"deleted": True}
