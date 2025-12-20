from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import Group, GroupImport, GroupImportValue, GroupMember, User
from app.schemas.group_imports import (
    GroupImportDatasetRead,
    GroupImportDatasetValuesRead,
    GroupImportWatchlistRequest,
    GroupImportWatchlistResponse,
)
from app.schemas.groups import (
    GroupCreate,
    GroupDetailRead,
    GroupMemberCreate,
    GroupMemberRead,
    GroupMembershipsRead,
    GroupMemberUpdate,
    GroupRead,
    GroupUpdate,
)
from app.services.group_imports import import_watchlist_dataset

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _field_is_set(payload, field: str) -> bool:
    if hasattr(payload, "model_fields_set"):
        return field in payload.model_fields_set  # type: ignore[attr-defined]
    return field in getattr(payload, "__fields_set__", set())


def _model_validate(schema_cls, obj):
    """Compat helper for Pydantic v1/v2."""

    if hasattr(schema_cls, "model_validate"):
        return schema_cls.model_validate(obj)  # type: ignore[attr-defined]
    return schema_cls.from_orm(obj)  # type: ignore[call-arg]


def _get_group_or_404(db: Session, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return group


def _get_group_by_name(
    db: Session,
    *,
    name: str,
    user: User | None,
) -> Group | None:
    owner_id = user.id if user is not None else None
    return (
        db.query(Group)
        .filter(Group.owner_id == owner_id, func.lower(Group.name) == name.lower())
        .one_or_none()
    )


@router.get("/", response_model=List[GroupRead])
def list_groups(
    kind: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> List[GroupRead]:
    query = (
        db.query(
            Group,
            func.count(GroupMember.id).label("member_count"),
        )
        .outerjoin(GroupMember, GroupMember.group_id == Group.id)
        .group_by(Group.id)
    )
    if user is not None:
        query = query.filter((Group.owner_id == user.id) | (Group.owner_id.is_(None)))
    if kind is not None:
        query = query.filter(Group.kind == kind)

    rows = query.order_by(Group.updated_at.desc()).all()
    results: List[GroupRead] = []
    for group, member_count in rows:
        payload = _model_validate(GroupRead, group)
        payload.member_count = int(member_count or 0)
        results.append(payload)
    return results


@router.post("/import/watchlist", response_model=GroupImportWatchlistResponse)
def import_watchlist(
    payload: GroupImportWatchlistRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> GroupImportWatchlistResponse:
    group_name = payload.group_name.strip()
    if not group_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group name is required.",
        )

    existing = _get_group_by_name(db, name=group_name, user=user)
    group: Group
    if existing is not None:
        if payload.conflict_mode == "ERROR":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A group with this name already exists.",
            )
        if payload.conflict_mode == "REPLACE_GROUP":
            db.delete(existing)
            db.commit()
            existing = None
        elif payload.conflict_mode == "REPLACE_DATASET":
            group = existing
    if existing is None:
        group = Group(
            owner_id=user.id if user is not None else None,
            name=group_name,
            kind="WATCHLIST",
            description=(payload.group_description or None),
        )
        db.add(group)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A group with this name already exists.",
            ) from exc
        db.refresh(group)

    try:
        result = import_watchlist_dataset(
            db,
            settings,
            group=group,
            source=payload.source,
            original_filename=payload.original_filename,
            symbol_column=payload.symbol_column,
            exchange_column=payload.exchange_column,
            default_exchange=payload.default_exchange,
            selected_columns=payload.selected_columns,
            header_labels=payload.header_labels,
            rows=payload.rows,
            strip_exchange_prefix=payload.strip_exchange_prefix,
            strip_special_chars=payload.strip_special_chars,
            allow_kite_fallback=payload.allow_kite_fallback,
            replace_members=payload.replace_members,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return GroupImportWatchlistResponse(
        group_id=result.group_id,
        import_id=result.import_id,
        imported_members=result.imported_members,
        imported_columns=result.imported_columns,
        skipped_symbols=result.skipped_symbols,
        skipped_columns=result.skipped_columns,
        warnings=result.warnings,
    )


@router.get("/{group_id}/dataset", response_model=GroupImportDatasetRead)
def get_group_dataset(
    group_id: int,
    db: Session = Depends(get_db),
) -> GroupImportDatasetRead:
    _get_group_or_404(db, group_id)
    record: GroupImport | None = (
        db.query(GroupImport).filter(GroupImport.group_id == group_id).one_or_none()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No dataset for this group.",
        )

    import json

    try:
        schema = json.loads(record.schema_json or "[]")
    except Exception:
        schema = []
    try:
        mapping = json.loads(record.symbol_mapping_json or "{}")
    except Exception:
        mapping = {}

    columns = []
    for col in schema:
        if not isinstance(col, dict):
            continue
        key = str(col.get("key") or "").strip()
        label = str(col.get("label") or key).strip()
        if not key:
            continue
        columns.append(
            {
                "key": key,
                "label": label,
                "type": col.get("type") or "string",
                "source_header": col.get("source_header"),
            }
        )

    return GroupImportDatasetRead(
        id=record.id,
        group_id=record.group_id,
        source=record.source,
        original_filename=record.original_filename,
        created_at=record.created_at,
        updated_at=record.updated_at,
        columns=columns,
        symbol_mapping=mapping,
    )


class _GroupDatasetValuesResponse(BaseModel):
    items: list[GroupImportDatasetValuesRead]


@router.get("/{group_id}/dataset/values", response_model=_GroupDatasetValuesResponse)
def get_group_dataset_values(
    group_id: int,
    db: Session = Depends(get_db),
) -> _GroupDatasetValuesResponse:
    _get_group_or_404(db, group_id)
    record: GroupImport | None = (
        db.query(GroupImport).filter(GroupImport.group_id == group_id).one_or_none()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No dataset for this group.",
        )

    import json

    values: list[GroupImportDatasetValuesRead] = []
    rows = (
        db.query(GroupImportValue)
        .filter(GroupImportValue.import_id == record.id)
        .order_by(GroupImportValue.id)
        .all()
    )
    for row in rows:
        try:
            payload = json.loads(row.values_json or "{}")
        except Exception:
            payload = {}
        values.append(
            GroupImportDatasetValuesRead(
                symbol=row.symbol,
                exchange=row.exchange,
                values=payload if isinstance(payload, dict) else {},
            )
        )
    return _GroupDatasetValuesResponse(items=values)


@router.post("/", response_model=GroupRead)
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> GroupRead:
    group = Group(
        owner_id=user.id if user is not None else None,
        name=payload.name,
        kind=payload.kind,
        description=payload.description,
    )
    db.add(group)
    try:
        db.commit()
    except IntegrityError as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A group with this name already exists.",
        ) from exc
    db.refresh(group)
    result = _model_validate(GroupRead, group)
    result.member_count = 0
    return result


@router.get("/{group_id}", response_model=GroupDetailRead)
def get_group(group_id: int, db: Session = Depends(get_db)) -> GroupDetailRead:
    group = _get_group_or_404(db, group_id)
    # Force members load.
    members = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id)
        .order_by(GroupMember.created_at)
        .all()
    )
    result = _model_validate(GroupDetailRead, group)
    result.member_count = len(members)
    result.members = [_model_validate(GroupMemberRead, m) for m in members]
    return result


@router.patch("/{group_id}", response_model=GroupRead)
def update_group(
    group_id: int,
    payload: GroupUpdate,
    db: Session = Depends(get_db),
) -> GroupRead:
    group = _get_group_or_404(db, group_id)
    updated = False
    if payload.name is not None:
        group.name = payload.name
        updated = True
    if payload.kind is not None:
        group.kind = payload.kind
        updated = True
    if payload.description is not None:
        group.description = payload.description
        updated = True

    if updated:
        db.add(group)
        try:
            db.commit()
        except IntegrityError as exc:  # pragma: no cover
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A group with this name already exists.",
            ) from exc
        db.refresh(group)

    member_count = (
        db.query(func.count(GroupMember.id))
        .filter(GroupMember.group_id == group_id)
        .scalar()
        or 0
    )
    result = _model_validate(GroupRead, group)
    result.member_count = int(member_count)
    return result


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_group(group_id: int, db: Session = Depends(get_db)) -> Response:
    group = _get_group_or_404(db, group_id)
    db.delete(group)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{group_id}/members", response_model=List[GroupMemberRead])
def list_group_members(
    group_id: int, db: Session = Depends(get_db)
) -> List[GroupMember]:
    _get_group_or_404(db, group_id)
    return (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id)
        .order_by(GroupMember.created_at)
        .all()
    )


@router.post("/{group_id}/members", response_model=GroupMemberRead)
def add_group_member(
    group_id: int,
    payload: GroupMemberCreate,
    db: Session = Depends(get_db),
) -> GroupMember:
    _get_group_or_404(db, group_id)
    member = GroupMember(
        group_id=group_id,
        symbol=payload.symbol,
        exchange=payload.exchange,
        target_weight=payload.target_weight,
        reference_qty=payload.reference_qty,
        reference_price=payload.reference_price,
        notes=payload.notes,
    )
    db.add(member)
    try:
        db.commit()
    except Exception as exc:  # pragma: no cover - SQLite uniqueness surface
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Member already exists in this group.",
        ) from exc
    db.refresh(member)
    return member


@router.post("/{group_id}/members/bulk", response_model=List[GroupMemberRead])
def bulk_add_group_members(
    group_id: int,
    payload: List[GroupMemberCreate],
    db: Session = Depends(get_db),
) -> List[GroupMember]:
    _get_group_or_404(db, group_id)
    created: List[GroupMember] = []
    for item in payload:
        created.append(
            GroupMember(
                group_id=group_id,
                symbol=item.symbol,
                exchange=item.exchange,
                target_weight=item.target_weight,
                reference_qty=item.reference_qty,
                reference_price=item.reference_price,
                notes=item.notes,
            )
        )
    db.add_all(created)
    try:
        db.commit()
    except Exception as exc:  # pragma: no cover
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more members already exist in this group.",
        ) from exc
    for member in created:
        db.refresh(member)
    return created


@router.patch("/{group_id}/members/{member_id}", response_model=GroupMemberRead)
def update_group_member(
    group_id: int,
    member_id: int,
    payload: GroupMemberUpdate,
    db: Session = Depends(get_db),
) -> GroupMember:
    _get_group_or_404(db, group_id)
    member = db.get(GroupMember, member_id)
    if member is None or member.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    updated = False
    if _field_is_set(payload, "target_weight"):
        member.target_weight = payload.target_weight
        updated = True
    if _field_is_set(payload, "reference_qty"):
        member.reference_qty = payload.reference_qty
        updated = True
    if _field_is_set(payload, "reference_price"):
        member.reference_price = payload.reference_price
        updated = True
    if _field_is_set(payload, "notes"):
        member.notes = payload.notes
        updated = True
    if updated:
        db.add(member)
        db.commit()
        db.refresh(member)
    return member


@router.delete(
    "/{group_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_group_member(
    group_id: int,
    member_id: int,
    db: Session = Depends(get_db),
) -> Response:
    _get_group_or_404(db, group_id)
    member = db.get(GroupMember, member_id)
    if member is None or member.group_id != group_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    db.delete(member)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/memberships", response_model=GroupMembershipsRead)
def get_memberships(
    symbols: List[str] = Query([]),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> GroupMembershipsRead:
    if not symbols:
        return GroupMembershipsRead(memberships={})

    group_query = db.query(Group.id, Group.name)
    if user is not None:
        group_query = group_query.filter(
            (Group.owner_id == user.id) | (Group.owner_id.is_(None))
        )
    groups = {gid: name for gid, name in group_query.all()}
    if not groups:
        return GroupMembershipsRead(memberships={})

    members = (
        db.query(GroupMember.group_id, GroupMember.symbol)
        .filter(
            GroupMember.symbol.in_(symbols),
            GroupMember.group_id.in_(list(groups.keys())),
        )
        .all()
    )
    memberships: dict[str, List[str]] = {symbol: [] for symbol in symbols}
    for group_id, symbol in members:
        memberships.setdefault(symbol, []).append(groups.get(group_id, ""))
    for symbol, names in list(memberships.items()):
        memberships[symbol] = [n for n in names if n]
    return GroupMembershipsRead(memberships=memberships)


__all__ = ["router"]
