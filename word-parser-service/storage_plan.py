from __future__ import annotations

import hashlib
import re
from typing import Any


def _slugify(value: str | None, fallback: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"{fallback}_{text}"
    return text


def _ensure_unique(base: str, seen: set[str]) -> str:
    candidate = base
    index = 2
    while candidate in seen:
        candidate = f"{base}_{index}"
        index += 1
    seen.add(candidate)
    return candidate


def apply_storage_plan(template_name: str, sub_forms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach physical storage metadata without changing render-oriented subForms."""
    single_forms = [
        sub_form for sub_form in sub_forms
        if sub_form.get("recordType") != "multi" and _has_persisted_fields(sub_form)
    ]

    main_table_name = None
    if len(single_forms) > 1:
        table_slug = _slugify(template_name, "")
        if not table_slug:
            table_slug = f"tpl_{hashlib.sha1(template_name.encode('utf-8')).hexdigest()[:8]}"
        main_table_name = f"t_insp_{table_slug}_main"

    for sub_form in sub_forms:
        if sub_form.get("recordType") == "multi":
            sub_form["storageTableName"] = sub_form.get("sqlTableName", "t_unknown")
        elif _has_persisted_fields(sub_form):
            sub_form["storageTableName"] = main_table_name or sub_form.get("sqlTableName", "t_unknown")
        else:
            sub_form["storageTableName"] = None

    for sub_form in sub_forms:
        seen_columns: set[str] = set()
        for field in sub_form.get("fields", []):
            if field.get("type") == "static":
                field["storageColumn"] = None
                continue
            base = field.get("sqlColumn") or field.get("id") or "field"
            field["storageColumn"] = _ensure_unique(_slugify(str(base), "field"), seen_columns)

    for table_name in {
        sub_form.get("storageTableName")
        for sub_form in sub_forms
        if sub_form.get("storageTableName")
    }:
        seen_columns: set[str] = set()
        grouped_fields = [
            field
            for sub_form in sub_forms
            if sub_form.get("storageTableName") == table_name
            for field in sub_form.get("fields", [])
            if field.get("type") != "static"
        ]
        for field in grouped_fields:
            preferred = field.get("storageColumn") or field.get("sqlColumn") or field.get("id") or "field"
            field["storageColumn"] = _ensure_unique(_slugify(str(preferred), "field"), seen_columns)

    return sub_forms


def count_storage_tables(sub_forms: list[dict[str, Any]]) -> int:
    return len({
        sub_form.get("storageTableName") or sub_form.get("sqlTableName")
        for sub_form in sub_forms
        if _has_persisted_fields(sub_form)
    })


def _has_persisted_fields(sub_form: dict[str, Any]) -> bool:
    return any(field.get("type") != "static" for field in sub_form.get("fields", []))
