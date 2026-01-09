from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Group, GroupImport, GroupImportValue, GroupMember
from app.schemas.group_imports import TargetWeightUnits
from app.services.market_data import resolve_listings_bulk


def _slugify_key(header: str) -> str:
    key = (header or "").strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "col"


def _parse_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    s = str(value).strip()
    if s == "":
        return None
    # Basic number parsing (no locale support).
    try:
        if re.fullmatch(r"-?\\d+", s):
            return int(s)
        if re.fullmatch(r"-?\\d+(\\.\\d+)?", s):
            return float(s)
    except Exception:
        return s
    return s


def _infer_column_type(values: Iterable[Any]) -> str:
    seen = [v for v in values if v is not None and str(v).strip() != ""]
    if not seen:
        return "string"
    numeric = 0
    for v in seen:
        parsed = _parse_scalar(v)
        if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
            numeric += 1
    return "number" if numeric / max(1, len(seen)) >= 0.8 else "string"


def normalize_symbol_exchange(
    symbol: str | None,
    exchange: str | None,
    *,
    default_exchange: str = "NSE",
    strip_exchange_prefix: bool = True,
    strip_special_chars: bool = True,
) -> tuple[str, str]:
    sym = (symbol or "").strip().upper()
    exch = (exchange or default_exchange or "NSE").strip().upper() or "NSE"
    if strip_exchange_prefix and ":" in sym:
        prefix, rest = sym.split(":", 1)
        if prefix.strip().upper() in {"NSE", "BSE"} and rest.strip():
            exch = prefix.strip().upper()
            sym = rest.strip().upper()
    if strip_special_chars:
        sym = re.sub(r"[^A-Z0-9]+", "", sym)
    return sym, exch


@dataclass
class ImportResult:
    group_id: int
    import_id: int
    imported_members: int
    imported_columns: int
    skipped_symbols: list[dict[str, Any]]
    skipped_columns: list[dict[str, Any]]
    warnings: list[str]


def import_watchlist_dataset(
    db: Session,
    settings: Settings,
    *,
    group: Group,
    source: str,
    original_filename: str | None,
    symbol_column: str,
    exchange_column: str | None,
    default_exchange: str,
    reference_qty_column: str | None,
    reference_price_column: str | None,
    target_weight_column: str | None,
    target_weight_units: TargetWeightUnits,
    selected_columns: list[str],
    header_labels: dict[str, str],
    rows: list[dict[str, Any]],
    strip_exchange_prefix: bool,
    strip_special_chars: bool,
    allow_kite_fallback: bool,
    replace_members: bool,
) -> ImportResult:
    skipped_columns: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not rows:
        raise ValueError("No rows provided.")

    if symbol_column not in rows[0]:
        raise ValueError("Symbol column not found in rows.")
    if exchange_column and exchange_column not in rows[0]:
        raise ValueError("Exchange column not found in rows.")
    if reference_qty_column and reference_qty_column not in rows[0]:
        raise ValueError("Ref qty column not found in rows.")
    if reference_price_column and reference_price_column not in rows[0]:
        raise ValueError("Ref price column not found in rows.")
    if target_weight_column and target_weight_column not in rows[0]:
        raise ValueError("Target weight column not found in rows.")

    reserved_headers = {
        symbol_column,
        exchange_column,
        reference_qty_column,
        reference_price_column,
        target_weight_column,
    }

    # Decide final imported columns (all user-selected, excluding reserved mappings).
    imported_headers: list[str] = []
    for header in selected_columns:
        if header in reserved_headers:
            continue
        label = header_labels.get(header) or header
        if header not in rows[0]:
            skipped_columns.append(
                {"header": str(label), "reason": "Header not found in rows."}
            )
            continue
        if not str(label or "").strip():
            skipped_columns.append({"header": str(label), "reason": "Empty header."})
            continue
        imported_headers.append(header)

    # Build stable keys for schema.
    used_keys: set[str] = set()
    schema: list[dict[str, Any]] = []
    for header in imported_headers:
        label = header_labels.get(header) or header
        base_key = _slugify_key(label)
        key = base_key
        i = 2
        while key in used_keys:
            key = f"{base_key}__{i}"
            i += 1
        used_keys.add(key)
        schema.append(
            {
                "key": key,
                "label": label,
                "type": "string",
                "source_header": label,
            }
        )

    # Normalize rows to symbol+exchange and collect unique pairs for broker resolution.
    skipped_symbols: list[dict[str, Any]] = []
    normalized_rows: list[tuple[int, str, str, dict[str, Any]]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for idx, row in enumerate(rows):
        raw_sym = row.get(symbol_column)
        raw_exch = row.get(exchange_column) if exchange_column else default_exchange
        sym, exch = normalize_symbol_exchange(
            str(raw_sym) if raw_sym is not None else None,
            str(raw_exch) if raw_exch is not None else None,
            default_exchange=default_exchange,
            strip_exchange_prefix=strip_exchange_prefix,
            strip_special_chars=strip_special_chars,
        )
        if not sym:
            skipped_symbols.append(
                {
                    "row_index": idx,
                    "raw_symbol": (
                        raw_sym
                        if raw_sym is None or isinstance(raw_sym, str)
                        else str(raw_sym)
                    ),
                    "raw_exchange": (
                        raw_exch
                        if raw_exch is None or isinstance(raw_exch, str)
                        else str(raw_exch)
                    ),
                    "normalized_symbol": sym or None,
                    "normalized_exchange": exch or None,
                    "reason": "Missing symbol.",
                }
            )
            continue
        if (sym, exch) in seen_pairs:
            skipped_symbols.append(
                {
                    "row_index": idx,
                    "raw_symbol": str(raw_sym) if raw_sym is not None else None,
                    "raw_exchange": str(raw_exch) if raw_exch is not None else None,
                    "normalized_symbol": sym,
                    "normalized_exchange": exch,
                    "reason": "Duplicate symbol in file.",
                }
            )
            continue
        seen_pairs.add((sym, exch))
        normalized_rows.append((idx, sym, exch, row))

    listings = resolve_listings_bulk(
        db,
        settings,
        pairs=[(sym, exch) for _, sym, exch, _ in normalized_rows],
        allow_kite_fallback=allow_kite_fallback,
    )

    resolved_rows: list[tuple[str, str, dict[str, Any]]] = []
    for idx, sym, exch, row in normalized_rows:
        if (sym, exch) not in listings:
            skipped_symbols.append(
                {
                    "row_index": idx,
                    "raw_symbol": row.get(symbol_column),
                    "raw_exchange": (
                        row.get(exchange_column)
                        if exchange_column
                        else default_exchange
                    ),
                    "normalized_symbol": sym,
                    "normalized_exchange": exch,
                    "reason": "Symbol does not resolve to a canonical listing.",
                }
            )
            continue
        resolved_rows.append((sym, exch, row))

    if not resolved_rows:
        raise ValueError(
            "No symbols resolved to broker instruments; nothing to import."
        )

    # Infer types from data.
    header_to_values: dict[str, list[Any]] = {h: [] for h in imported_headers}
    for _, _, row in resolved_rows:
        for h in imported_headers:
            header_to_values[h].append(row.get(h))
    for col in schema:
        source_header = next(
            (
                h
                for h in imported_headers
                if (header_labels.get(h) or h) == col["label"]
            ),
            None,
        )
        if source_header is None:
            continue
        col["type"] = _infer_column_type(header_to_values[source_header])

    # Replace group members if requested.
    if replace_members:
        db.query(GroupMember).filter(GroupMember.group_id == group.id).delete()

    def _parse_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            val = float(value)
            return val if val == val else None  # NaN check
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            cleaned = (
                s.replace(",", "")
                .replace("₹", "")
                .replace("Rs.", "")
                .replace("rs.", "")
            ).strip()
            cleaned = cleaned.replace("%", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                return None
        try:
            return float(str(value))
        except Exception:
            return None

    def _parse_int(value: Any) -> int | None:
        val = _parse_float(value)
        if val is None:
            return None
        if val < 0:
            return None
        if float(int(val)) != val:
            return None
        return int(val)

    def _parse_weight_fraction(value: Any) -> float | None:
        val = _parse_float(value)
        if val is None:
            return None
        if target_weight_units == "PCT":
            val = val / 100.0
        elif target_weight_units == "AUTO" and val > 1.0:
            val = val / 100.0

        if val < 0.0 or val > 1.0:
            return None
        return val

    members: list[GroupMember] = []
    for sym, exch, row in resolved_rows:
        reference_qty = (
            _parse_int(row.get(reference_qty_column)) if reference_qty_column else None
        )
        reference_price = (
            _parse_float(row.get(reference_price_column))
            if reference_price_column
            else None
        )
        if reference_price is not None and reference_price <= 0.0:
            reference_price = None
        target_weight = (
            _parse_weight_fraction(row.get(target_weight_column))
            if target_weight_column
            else None
        )
        members.append(
            GroupMember(
                group_id=group.id,
                symbol=sym,
                exchange=exch,
                target_weight=target_weight,
                reference_qty=reference_qty,
                reference_price=reference_price,
            )
        )
    db.add_all(members)

    # Upsert dataset: ensure a single record per group.
    existing: GroupImport | None = (
        db.query(GroupImport).filter(GroupImport.group_id == group.id).one_or_none()
    )
    if existing is None:
        existing = GroupImport(
            group_id=group.id,
            source=source,
            original_filename=original_filename,
            schema_json="[]",
            symbol_mapping_json="{}",
        )
        db.add(existing)
        db.flush()
    else:
        # Clear existing values.
        db.query(GroupImportValue).filter(
            GroupImportValue.import_id == existing.id
        ).delete()
        existing.source = source
        existing.original_filename = original_filename

    symbol_mapping = {
        "symbol_column": symbol_column,
        "exchange_column": exchange_column,
        "default_exchange": default_exchange,
        "strip_exchange_prefix": strip_exchange_prefix,
        "strip_special_chars": strip_special_chars,
        "selected_headers": [header_labels.get(h) or h for h in imported_headers],
        "member_field_mapping": {
            "reference_qty_column": reference_qty_column,
            "reference_price_column": reference_price_column,
            "target_weight_column": target_weight_column,
            "target_weight_units": target_weight_units,
        },
    }
    existing.schema_json = json.dumps(schema, ensure_ascii=False)
    existing.symbol_mapping_json = json.dumps(symbol_mapping, ensure_ascii=False)

    # Persist values per resolved symbol.
    key_by_header: dict[str, str] = {}
    for header, col in zip(imported_headers, schema, strict=False):
        key_by_header[header] = col["key"]

    values_rows: list[GroupImportValue] = []
    for sym, exch, row in resolved_rows:
        values: dict[str, Any] = {}
        for header in imported_headers:
            key = key_by_header.get(header)
            if not key:
                continue
            values[key] = _parse_scalar(row.get(header))
        values_rows.append(
            GroupImportValue(
                import_id=existing.id,
                symbol=sym,
                exchange=exch,
                values_json=json.dumps(values, ensure_ascii=False),
            )
        )
    db.add_all(values_rows)

    db.add(group)
    db.commit()

    return ImportResult(
        group_id=group.id,
        import_id=existing.id,
        imported_members=len(resolved_rows),
        imported_columns=len(schema),
        skipped_symbols=skipped_symbols,
        skipped_columns=skipped_columns,
        warnings=warnings,
    )
