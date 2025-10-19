from __future__ import annotations

from typing import List, Optional, Dict
from pydantic import BaseModel, RootModel, Field, field_validator


class Column(BaseModel):
    column_name: str = Field(..., description="Column/field name as in the DB")
    data_type: str = Field(
        ...,
        description="DB-native data type (kept as string, e.g., 'int', 'nvarchar', 'decimal')",
    )
    is_nullable: bool = Field(..., description="True if column accepts NULL")

    @field_validator("data_type")
    @classmethod
    def _normalize_data_type(cls, v: str) -> str:
        # preserve details but normalize base type for consistency
        return (v or "").strip().lower()

    @field_validator("is_nullable", mode="before")
    @classmethod
    def _coerce_nullable(cls, v):
        # Accepts "YES"/"NO", booleans, or truthy strings
        if isinstance(v, bool):
            return v
        if v is None:
            return True  # be permissive if unspecified
        s = str(v).strip().lower()
        if s in {"yes", "y", "true", "1"}:
            return True
        if s in {"no", "n", "false", "0"}:
            return False
        # fallback: truthy
        return bool(v)


class ForeignKeyRef(BaseModel):
    foreign_key: str = Field(..., description="FK column in this table")
    primary_key_table: Optional[str] = Field(
        None, description="Referenced PK table name (may be missing in source)"
    )
    primary_key_column: Optional[str] = Field(
        None,
        description="Referenced PK column name (optional; your JSON may not include it)",
    )


class TableMetadata(BaseModel):
    description: Optional[str] = None
    primary_key: Optional[str] = None
    primary_key_description: Optional[str] = None
    row_count_estimate: Optional[int] = None
    key_columns: Optional[List[str]] = None


class TableSchema(BaseModel):
    table_name: str
    columns: List[Column]
    metadata: Optional[TableMetadata] = None
    foreign_keys: Optional[List[ForeignKeyRef]] = None

    @field_validator("table_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()

    def column_index(self) -> Dict[str, Column]:
        """Convenience: map of column_name -> Column (case-sensitive as provided)."""
        return {c.column_name: c for c in self.columns}


class DatabaseSchema(RootModel[List[TableSchema]]):
    """Root model for the entire JSON array of tables."""

    def by_table(self) -> Dict[str, TableSchema]:
        """Convenience: map of table_name -> TableSchema."""
        return {t.table_name: t for t in self.root}

    def find_table(self, name: str) -> Optional[TableSchema]:
        """Case-insensitive lookup."""
        name_l = name.strip().lower()
        for t in self.root:
            if t.table_name.lower() == name_l:
                return t
        return None
