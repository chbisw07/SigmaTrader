from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.ai_trading_manager import AiTmPlaybook, AiTmPlaybookRun, AiTmTradePlan
from app.schemas.ai_trading_manager import (
    PlaybookCreateRequest,
    PlaybookRead,
    PlaybookRunRead,
    TradePlan,
)


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(raw: str) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        return {}


def create_trade_plan(db: Session, *, plan: TradePlan, user_id: int | None, account_id: str) -> AiTmTradePlan:
    row = AiTmTradePlan(
        plan_id=plan.plan_id,
        user_id=user_id,
        account_id=account_id,
        plan_json=_json_dumps(plan.model_dump(mode="json")),
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def upsert_trade_plan(db: Session, *, plan: TradePlan, user_id: int | None, account_id: str) -> AiTmTradePlan:
    existing = db.execute(select(AiTmTradePlan).where(AiTmTradePlan.plan_id == plan.plan_id)).scalar_one_or_none()
    payload = _json_dumps(plan.model_dump(mode="json"))
    if existing is None:
        return create_trade_plan(db, plan=plan, user_id=user_id, account_id=account_id)
    existing.plan_json = payload
    db.commit()
    db.refresh(existing)
    return existing


def get_trade_plan(db: Session, *, plan_id: str) -> TradePlan | None:
    row = db.execute(select(AiTmTradePlan).where(AiTmTradePlan.plan_id == plan_id)).scalar_one_or_none()
    if row is None:
        return None
    return TradePlan.model_validate(_json_loads(row.plan_json))


def create_playbook(db: Session, *, payload: PlaybookCreateRequest, user_id: int | None) -> PlaybookRead:
    pb_id = uuid4().hex
    now = datetime.now(UTC)
    plan_row = upsert_trade_plan(db, plan=payload.plan, user_id=user_id, account_id=payload.account_id)

    next_run_at = None
    if payload.cadence_sec is not None:
        next_run_at = now + timedelta(seconds=int(payload.cadence_sec))

    row = AiTmPlaybook(
        playbook_id=pb_id,
        user_id=user_id,
        account_id=payload.account_id,
        name=payload.name,
        description=payload.description,
        plan_id=plan_row.plan_id,
        enabled=True,
        armed=False,
        armed_at=None,
        armed_by_message_id=None,
        cadence_sec=payload.cadence_sec,
        next_run_at=next_run_at,
        last_run_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_schema(row)


def list_playbooks(db: Session, *, account_id: str) -> List[PlaybookRead]:
    rows = (
        db.execute(
            select(AiTmPlaybook)
            .where(AiTmPlaybook.account_id == account_id)
            .order_by(desc(AiTmPlaybook.created_at))
        )
        .scalars()
        .all()
    )
    return [_to_schema(r) for r in rows]


def get_playbook(db: Session, *, playbook_id: str) -> PlaybookRead | None:
    row = db.execute(select(AiTmPlaybook).where(AiTmPlaybook.playbook_id == playbook_id)).scalar_one_or_none()
    if row is None:
        return None
    return _to_schema(row)


def set_playbook_armed(
    db: Session,
    *,
    playbook_id: str,
    armed: bool,
    armed_by_message_id: str | None = None,
) -> PlaybookRead | None:
    row = db.execute(select(AiTmPlaybook).where(AiTmPlaybook.playbook_id == playbook_id)).scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(UTC)
    row.armed = bool(armed)
    row.armed_at = now if armed else None
    if not armed:
        row.armed_by_message_id = None
    elif armed_by_message_id:
        row.armed_by_message_id = str(armed_by_message_id)
    if armed and row.cadence_sec:
        row.next_run_at = now + timedelta(seconds=int(row.cadence_sec))
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return _to_schema(row)


def create_playbook_run(
    db: Session,
    *,
    playbook_id: str,
    dedupe_key: str,
    decision_id: str | None,
    authorization_message_id: str | None,
    status: str,
    outcome: Dict[str, Any],
) -> AiTmPlaybookRun:
    now = datetime.now(UTC)
    row = AiTmPlaybookRun(
        run_id=uuid4().hex,
        playbook_id=playbook_id,
        dedupe_key=dedupe_key,
        decision_id=decision_id,
        authorization_message_id=authorization_message_id,
        status=status,
        outcome_json=_json_dumps(outcome),
        started_at=now,
        completed_at=now,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        existing = (
            db.execute(
                select(AiTmPlaybookRun).where(
                    AiTmPlaybookRun.playbook_id == playbook_id,
                    AiTmPlaybookRun.dedupe_key == dedupe_key,
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return existing
        raise


def touch_playbook_after_run(
    db: Session,
    *,
    playbook_id: str,
    ran_at: datetime | None = None,
) -> None:
    row = db.execute(select(AiTmPlaybook).where(AiTmPlaybook.playbook_id == playbook_id)).scalar_one_or_none()
    if row is None:
        return
    now = ran_at or datetime.now(UTC)
    row.last_run_at = now
    if row.cadence_sec:
        row.next_run_at = now + timedelta(seconds=int(row.cadence_sec))
    row.updated_at = now
    db.commit()


def _to_schema(row: AiTmPlaybook) -> PlaybookRead:
    return PlaybookRead(
        playbook_id=row.playbook_id,
        account_id=row.account_id,
        name=row.name,
        description=row.description,
        plan_id=row.plan_id,
        enabled=bool(row.enabled),
        armed=bool(row.armed),
        armed_at=row.armed_at,
        armed_by_message_id=row.armed_by_message_id,
        cadence_sec=row.cadence_sec,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_playbook_runs(
    db: Session,
    *,
    playbook_id: str,
    limit: int = 50,
) -> List[PlaybookRunRead]:
    rows = (
        db.execute(
            select(AiTmPlaybookRun)
            .where(AiTmPlaybookRun.playbook_id == playbook_id)
            .order_by(desc(AiTmPlaybookRun.started_at))
            .limit(min(int(limit), 200))
        )
        .scalars()
        .all()
    )
    out: List[PlaybookRunRead] = []
    for r in rows:
        out.append(
            PlaybookRunRead(
                run_id=r.run_id,
                playbook_id=r.playbook_id,
                dedupe_key=r.dedupe_key,
                decision_id=r.decision_id,
                authorization_message_id=r.authorization_message_id,
                status=r.status,
                outcome=_json_loads(r.outcome_json),
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
        )
    return out
