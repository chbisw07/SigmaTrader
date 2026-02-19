from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, List
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.ai_trading_manager import AiTmManagePlaybook
from app.schemas.ai_trading_manager import ManagePlaybookRead, ManagePlaybookUpsertRequest


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _to_schema(row: AiTmManagePlaybook) -> ManagePlaybookRead:
    return ManagePlaybookRead(
        playbook_id=row.playbook_id,
        scope_type=row.scope_type,
        scope_key=row.scope_key,
        enabled=bool(row.enabled),
        mode=row.mode,
        horizon=row.horizon,
        review_cadence_min=int(row.review_cadence_min),
        exit_policy=_json_loads(row.exit_policy_json or "{}", {}),
        scale_policy=_json_loads(row.scale_policy_json or "{}", {}),
        execution_style=row.execution_style,
        allow_strategy_exits=bool(row.allow_strategy_exits),
        behavior_on_strategy_exit=row.behavior_on_strategy_exit,
        notes=row.notes,
        version=int(row.version or 1),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_manage_playbooks(
    db: Session,
    *,
    scope_type: str | None = None,
    scope_key: str | None = None,
    enabled_only: bool | None = None,
    limit: int = 200,
) -> List[ManagePlaybookRead]:
    stmt = select(AiTmManagePlaybook)
    if scope_type:
        stmt = stmt.where(AiTmManagePlaybook.scope_type == scope_type)
    if scope_key is not None:
        stmt = stmt.where(AiTmManagePlaybook.scope_key == scope_key)
    if enabled_only is True:
        stmt = stmt.where(AiTmManagePlaybook.enabled.is_(True))
    stmt = stmt.order_by(desc(AiTmManagePlaybook.updated_at)).limit(min(int(limit), 1000))
    rows = db.execute(stmt).scalars().all()
    return [_to_schema(r) for r in rows]


def get_manage_playbook(db: Session, *, playbook_id: str) -> ManagePlaybookRead | None:
    row = (
        db.execute(select(AiTmManagePlaybook).where(AiTmManagePlaybook.playbook_id == playbook_id))
        .scalars()
        .first()
    )
    return _to_schema(row) if row is not None else None


def upsert_manage_playbook(
    db: Session,
    *,
    playbook_id: str | None,
    payload: ManagePlaybookUpsertRequest,
) -> ManagePlaybookRead:
    now = datetime.now(UTC)
    if playbook_id:
        row = (
            db.execute(select(AiTmManagePlaybook).where(AiTmManagePlaybook.playbook_id == playbook_id))
            .scalars()
            .first()
        )
    else:
        row = None

    if row is None:
        row = AiTmManagePlaybook(
            playbook_id=playbook_id or uuid4().hex,
            scope_type=str(payload.scope_type or "POSITION").upper(),
            scope_key=str(payload.scope_key) if payload.scope_key is not None else None,
            enabled=bool(payload.enabled) if payload.enabled is not None else False,
            mode=str(payload.mode or "OBSERVE").upper(),
            horizon=str(payload.horizon or "SWING").upper(),
            review_cadence_min=int(payload.review_cadence_min or 60),
            exit_policy_json=_json_dumps(payload.exit_policy or {}),
            scale_policy_json=_json_dumps(payload.scale_policy or {}),
            execution_style=str(payload.execution_style or "LIMIT_BBO").upper(),
            allow_strategy_exits=(
                bool(payload.allow_strategy_exits) if payload.allow_strategy_exits is not None else True
            ),
            behavior_on_strategy_exit=str(payload.behavior_on_strategy_exit or "ALLOW_AS_IS").upper(),
            notes=payload.notes,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _to_schema(row)

    # Update.
    if payload.enabled is not None:
        row.enabled = bool(payload.enabled)
    if payload.mode is not None:
        row.mode = str(payload.mode).upper()
    if payload.horizon is not None:
        row.horizon = str(payload.horizon).upper()
    if payload.review_cadence_min is not None:
        row.review_cadence_min = int(payload.review_cadence_min)
    if payload.exit_policy is not None:
        row.exit_policy_json = _json_dumps(payload.exit_policy)
    if payload.scale_policy is not None:
        row.scale_policy_json = _json_dumps(payload.scale_policy)
    if payload.execution_style is not None:
        row.execution_style = str(payload.execution_style).upper()
    if payload.allow_strategy_exits is not None:
        row.allow_strategy_exits = bool(payload.allow_strategy_exits)
    if payload.behavior_on_strategy_exit is not None:
        row.behavior_on_strategy_exit = str(payload.behavior_on_strategy_exit).upper()
    if payload.notes is not None:
        row.notes = payload.notes

    row.version = int(row.version or 1) + 1
    row.updated_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_schema(row)


def delete_manage_playbook(db: Session, *, playbook_id: str) -> bool:
    row = (
        db.execute(select(AiTmManagePlaybook).where(AiTmManagePlaybook.playbook_id == playbook_id))
        .scalars()
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


__all__ = [
    "delete_manage_playbook",
    "get_manage_playbook",
    "list_manage_playbooks",
    "upsert_manage_playbook",
]
