from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

ImportColumnType = Literal["string", "number", "boolean", "date", "datetime"]
ImportConflictMode = Literal["ERROR", "REPLACE_DATASET", "REPLACE_GROUP"]


class GroupImportColumn(BaseModel):
    key: str
    label: str
    type: ImportColumnType = "string"
    source_header: Optional[str] = None


class GroupImportDatasetRead(BaseModel):
    id: int
    group_id: int
    source: str
    original_filename: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    columns: List[GroupImportColumn]
    symbol_mapping: Dict[str, Any] = {}

    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover

        class Config:
            orm_mode = True


class GroupImportDatasetValuesRead(BaseModel):
    symbol: str
    exchange: str
    values: Dict[str, Any]


class SkippedColumn(BaseModel):
    header: str
    reason: str


class SkippedSymbol(BaseModel):
    row_index: int
    raw_symbol: Optional[str] = None
    raw_exchange: Optional[str] = None
    normalized_symbol: Optional[str] = None
    normalized_exchange: Optional[str] = None
    reason: str


class GroupImportWatchlistRequest(BaseModel):
    group_name: str = Field(..., max_length=255)
    group_description: Optional[str] = None
    source: str = "TRADINGVIEW"
    original_filename: Optional[str] = None

    symbol_column: str
    exchange_column: Optional[str] = None
    default_exchange: str = "NSE"

    selected_columns: List[str] = []
    header_labels: Dict[str, str] = {}

    rows: List[Dict[str, Any]] = []

    strip_exchange_prefix: bool = True
    strip_special_chars: bool = True
    allow_kite_fallback: bool = True

    conflict_mode: ImportConflictMode = "ERROR"
    replace_members: bool = True


class GroupImportWatchlistResponse(BaseModel):
    group_id: int
    import_id: int
    imported_members: int
    imported_columns: int
    skipped_symbols: List[SkippedSymbol] = []
    skipped_columns: List[SkippedColumn] = []
    warnings: List[str] = []


__all__ = [
    "ImportColumnType",
    "ImportConflictMode",
    "GroupImportColumn",
    "GroupImportDatasetRead",
    "GroupImportDatasetValuesRead",
    "GroupImportWatchlistRequest",
    "GroupImportWatchlistResponse",
    "SkippedColumn",
    "SkippedSymbol",
]
