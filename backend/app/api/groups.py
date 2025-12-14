from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.db.session import get_db
from app.models import Group, GroupMember, User
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

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


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
    if payload.target_weight is not None:
        member.target_weight = payload.target_weight
        updated = True
    if payload.notes is not None:
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
