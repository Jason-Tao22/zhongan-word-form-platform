"""Pydantic models — JSON Schema 格式定义"""
from __future__ import annotations
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Layout cell types
# ---------------------------------------------------------------------------

class CellStyle(BaseModel):
    widthPx: Optional[int] = None
    textAlign: Optional[Literal["left", "center", "right", "justify"]] = None
    verticalAlign: Optional[Literal["top", "middle", "bottom"]] = None
    backgroundColor: Optional[str] = None
    fontWeight: Optional[Literal["normal", "bold"]] = None

class LabelCell(BaseModel):
    kind: Literal["label"]
    text: str
    colspan: int = 1
    rowspan: int = 1
    style: Optional[CellStyle] = None


class InputCell(BaseModel):
    kind: Literal["input"]
    fieldId: str
    colspan: int = 1
    rowspan: int = 1
    style: Optional[CellStyle] = None


class StaticCell(BaseModel):
    kind: Literal["static"]
    text: str
    colspan: int = 1
    rowspan: int = 1
    style: Optional[CellStyle] = None


Cell = Union[LabelCell, InputCell, StaticCell]


# ---------------------------------------------------------------------------
# Layout types
# ---------------------------------------------------------------------------

class KeyValueLayout(BaseModel):
    type: Literal["key-value"]
    rows: list[list[Cell]]


class GridHeader(BaseModel):
    text: str
    rowspan: int = 1
    colspan: int = 1
    style: Optional[CellStyle] = None


class DataGridLayout(BaseModel):
    type: Literal["data-grid"]
    headers: list[list[GridHeader]]
    dataColumns: list[str]
    prefixFields: list[str] = Field(default_factory=list)
    defaultRowCount: int = 10


class ChecklistItem(BaseModel):
    seq: str = ""
    label: str
    fieldId: Optional[str] = None
    remarkFieldId: Optional[str] = None
    subItems: Optional[list[ChecklistItem]] = None


class ChecklistLayout(BaseModel):
    type: Literal["checklist"]
    columns: list[str]
    items: list[ChecklistItem]


class SectionItem(BaseModel):
    label: str
    fieldId: str
    colspan: int = 1
    labelColspan: int = 1
    labelStyle: Optional[CellStyle] = None
    inputStyle: Optional[CellStyle] = None


class Section(BaseModel):
    title: str
    titleStyle: Optional[CellStyle] = None
    rows: list[list[SectionItem]]


class SectionGroupLayout(BaseModel):
    type: Literal["section-group"]
    sections: list[Section]


Layout = Union[KeyValueLayout, DataGridLayout, ChecklistLayout, SectionGroupLayout]


# ---------------------------------------------------------------------------
# Field definition
# ---------------------------------------------------------------------------

FIELD_TYPE = Literal["text", "number", "textarea", "date", "radio", "select", "checkbox_group", "static"]
SQL_TYPE   = Literal["VARCHAR(20)", "VARCHAR(50)", "VARCHAR(100)", "VARCHAR(200)", "VARCHAR(500)",
                     "TEXT", "DATE", "INTEGER", "NUMERIC(10,2)", "NUMERIC(10,3)", "JSONB"]


class FieldDef(BaseModel):
    id: str
    label: str
    type: FIELD_TYPE
    placeholder: Optional[str] = None
    sqlColumn: Optional[str] = None   # None → static 字段，不建列
    storageColumn: Optional[str] = None
    sqlType: Optional[str] = None
    required: bool = False
    options: Optional[list[str]] = None   # radio / select 专用
    isPrefix: bool = False                # data-grid 中表头信息字段


# ---------------------------------------------------------------------------
# Sub-form (= 一张子表 = 一张 SQL 表)
# ---------------------------------------------------------------------------

class SubForm(BaseModel):
    id: str
    name: str
    sqlTableName: str
    storageTableName: Optional[str] = None
    recordType: Literal["single", "multi"]
    layout: Layout = Field(discriminator="type")
    fields: list[FieldDef]


# ---------------------------------------------------------------------------
# Top-level schema
# ---------------------------------------------------------------------------

class FormSchema(BaseModel):
    schemaVersion: str = "1.0"
    templateId: str
    templateName: str
    sourceFile: str
    createdAt: str
    sqlDatabase: Literal["postgresql"] = "postgresql"
    subForms: list[SubForm]
    documentBlocks: list[dict] = Field(default_factory=list)
