from __future__ import annotations

import hashlib
import re

from word_parser import ParsedCell, ParsedTable


def analyze_tables_heuristically(tables: list[ParsedTable], filename: str) -> list[dict]:
    return [_build_sub_form(table, index, filename) for index, table in enumerate(tables, start=1)]


def _build_sub_form(table: ParsedTable, index: int, filename: str) -> dict:
    layout_type = _infer_layout_type(table)
    name = _infer_table_name(table, index, filename)
    form_id = _safe_name_to_id(name, fallback=f"table_{index}")
    record_type = "multi" if layout_type == "data-grid" else "single"

    if layout_type == "data-grid":
        fields = _build_data_grid_fields(table, form_id)
    elif layout_type == "checklist":
        fields = _build_checklist_fields(table, form_id)
    else:
        fields = _build_form_fields(table, form_id, section_group=(layout_type == "section-group"))

    return {
        "id": form_id,
        "name": name,
        "sqlTableName": f"t_insp_{form_id}",
        "recordType": record_type,
        "layout": {"type": layout_type},
        "fields": fields,
    }


def _infer_layout_type(table: ParsedTable) -> str:
    visible_rows = _visible_rows(table)
    if not visible_rows:
        return "key-value"

    title_row_count = sum(1 for row in visible_rows if _is_title_row(row, table.col_count))
    seq_like_rows = sum(1 for row in visible_rows if _is_seq_row(row))
    header_candidate = _header_candidate_rows(visible_rows)
    max_visible_cols = max((len(row) for row in visible_rows), default=0)

    if max_visible_cols >= 4 and len(visible_rows) >= 4 and header_candidate >= 1 and _looks_like_grid(table):
        return "data-grid"

    if seq_like_rows >= max(3, len(visible_rows) // 3):
        return "checklist"

    if title_row_count >= 1:
        return "section-group"

    return "key-value"


def _looks_like_grid(table: ParsedTable) -> bool:
    visible_rows = _visible_rows(table)
    if len(visible_rows) < 3:
        return False

    dense_rows = sum(1 for row in visible_rows[:4] if len(row) >= max(4, table.col_count // 2))
    repeated_width = sum(1 for row in visible_rows if len(row) >= max(4, table.col_count // 2))
    return dense_rows >= 2 and repeated_width >= 3


def _header_candidate_rows(rows: list[list[ParsedCell]]) -> int:
    count = 0
    for row in rows[:4]:
        texts = [_normalize_text(cell.text) for cell in row]
        if not any(texts):
            break
        count += 1
    return count


def _is_seq_row(row: list[ParsedCell]) -> bool:
    first = _normalize_text(row[0].text) if row else ""
    return bool(re.fullmatch(r"[0-9一二三四五六七八九十]+[.)、]?", first))


def _is_title_row(row: list[ParsedCell], col_count: int) -> bool:
    return len(row) == 1 and row[0].colspan >= max(2, col_count // 2)


def _infer_table_name(table: ParsedTable, index: int, filename: str) -> str:
    visible_rows = _visible_rows(table)
    for row in visible_rows[:5]:
        for cell in row:
            text = _normalize_text(cell.text)
            if len(text) >= 4 and not _is_generic_header(text):
                return text[:60]
    return f"{filename.removesuffix('.docx').removesuffix('.doc')}_table_{index}"


def _is_generic_header(text: str) -> bool:
    generic = {"序号", "项目", "内容", "备注", "检查结果", "检查项目"}
    return text in generic


def _build_form_fields(table: ParsedTable, form_id: str, section_group: bool) -> list[dict]:
    fields: list[dict] = []
    used_ids: set[str] = set()

    for row in _visible_rows(table):
        if _is_title_row(row, table.col_count):
            continue
        if _contains_signature(row):
            continue

        pairs = _iter_label_input_pairs(row, section_group)
        for label, input_cell in pairs:
            field = _make_field(label, form_id, used_ids, input_cell)
            if field:
                fields.append(field)

    if fields:
        return fields

    # 极端兜底：至少给每张表一个 textarea，避免 schema 为空导致后续没法录入。
    fallback_id = _unique_id(f"{form_id}_content", used_ids)
    return [{
        "id": fallback_id,
        "label": "内容",
        "type": "textarea",
    }]


def _build_checklist_fields(table: ParsedTable, form_id: str) -> list[dict]:
    fields: list[dict] = []
    used_ids: set[str] = set()

    for row in _visible_rows(table):
        if _contains_signature(row):
            continue
        label = _row_label_for_checklist(row)
        if not label:
            continue
        result_field = _make_field(label + "_结果", form_id, used_ids, None, preferred_type="text")
        remark_field = _make_field(label + "_备注", form_id, used_ids, None, preferred_type="textarea")
        if result_field:
            fields.append(result_field)
        if remark_field:
            fields.append(remark_field)

    return fields or _build_form_fields(table, form_id, section_group=False)


def _build_data_grid_fields(table: ParsedTable, form_id: str) -> list[dict]:
    visible_rows = _visible_rows(table)
    header_rows = visible_rows[: min(3, len(visible_rows))]
    header_cells = header_rows[-1] if header_rows else []
    fields: list[dict] = []
    used_ids: set[str] = set()

    for index, cell in enumerate(header_cells):
        label = _normalize_text(cell.text) or f"列{index + 1}"
        if _should_skip_grid_column(label):
            continue
        fields.append(_make_grid_field(label, form_id, used_ids))

    if fields:
        return fields

    return [{
        "id": _unique_id(f"{form_id}_value", used_ids),
        "label": "数值",
        "type": "text",
    }]


def _should_skip_grid_column(label: str) -> bool:
    normalized = label.replace(" ", "")
    if normalized in {"", "序号", "备注", "项目", "检查项目"}:
        return True
    return bool(re.fullmatch(r"[0-9一二三四五六七八九十]+", normalized))


def _make_grid_field(label: str, form_id: str, used_ids: set[str]) -> dict:
    field_id = _unique_id(f"{form_id}_{_safe_name_to_id(label, 'col')}", used_ids)
    field_type = _infer_field_type(label, None)
    return {
        "id": field_id,
        "label": label,
        "type": field_type,
    }


def _iter_label_input_pairs(row: list[ParsedCell], section_group: bool) -> list[tuple[str, ParsedCell | None]]:
    pairs: list[tuple[str, ParsedCell | None]] = []
    if len(row) == 1:
        text = _normalize_text(row[0].text)
        if text and not _contains_option_mark(text):
            pairs.append((text, None))
        return pairs

    step = 2 if section_group or len(row) % 2 == 0 else 1
    if step == 1:
        for index, cell in enumerate(row[:-1]):
            label = _normalize_text(cell.text)
            if label and not _contains_option_mark(label):
                pairs.append((label, row[index + 1]))
        return pairs

    for index in range(0, len(row), 2):
        label = _normalize_text(row[index].text)
        input_cell = row[index + 1] if index + 1 < len(row) else None
        if label:
            pairs.append((label, input_cell))
    return pairs


def _contains_signature(row: list[ParsedCell]) -> bool:
    text = " ".join(_normalize_text(cell.text) for cell in row)
    return any(keyword in text for keyword in ["检查：", "审核：", "批准：", "检验人员", "检验机构"])


def _row_label_for_checklist(row: list[ParsedCell]) -> str:
    texts = [_normalize_text(cell.text) for cell in row]
    meaningful = [text for text in texts if text]
    if len(meaningful) >= 2:
        return meaningful[1]
    return meaningful[0] if meaningful else ""


def _make_field(
    label: str,
    form_id: str,
    used_ids: set[str],
    input_cell: ParsedCell | None,
    preferred_type: str | None = None,
) -> dict | None:
    label = _cleanup_label(label)
    if not label:
        return None
    field_id = _unique_id(f"{form_id}_{_safe_name_to_id(label, 'field')}", used_ids)
    field_type = preferred_type or _infer_field_type(label, input_cell)
    field: dict = {
        "id": field_id,
        "label": label,
        "type": field_type,
    }
    options = _extract_options(label, input_cell)
    if options:
        field["options"] = options
    return field


def _infer_field_type(label: str, input_cell: ParsedCell | None) -> str:
    source = f"{label} {_normalize_text(input_cell.text) if input_cell else ''}"
    if _contains_option_mark(source):
        return "radio"
    if "年月日" in source or "日期" in source or "时间" in source:
        return "date"
    if any(keyword in source for keyword in ["备注", "说明", "意见", "结论", "情况", "记录"]):
        return "textarea"
    if any(keyword in source for keyword in ["温度", "压力", "厚度", "长度", "直径", "高度", "宽度", "数值", "浓度"]):
        return "number"
    return "text"


def _extract_options(label: str, input_cell: ParsedCell | None) -> list[str] | None:
    source = f"{label} {_normalize_text(input_cell.text) if input_cell else ''}"
    if "□" not in source:
        return None
    options = [part.strip() for part in re.findall(r"□\s*([^□]+)", source)]
    return options or None


def _cleanup_label(label: str) -> str:
    label = _normalize_text(label)
    label = re.sub(r"^[0-9一二三四五六七八九十]+[.)、]\s*", "", label)
    label = label.strip(":： ")
    return label[:80]


def _safe_name_to_id(text: str, fallback: str) -> str:
    text = text.lower()
    original = text
    if re.search(r"[a-z0-9]", text):
        slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
        return _limit_identifier(slug or fallback, original)

    tokens = re.findall(r"[\u4e00-\u9fff]+", text)
    if tokens:
        return _limit_identifier(fallback, original)

    return _limit_identifier(fallback, original)


def _unique_id(base: str, used_ids: set[str]) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9_]+", "_", base).strip("_") or "field"
    if candidate[0].isdigit():
        candidate = f"f_{candidate}"
    candidate = _limit_identifier(candidate, candidate)
    suffix = 2
    result = candidate
    while result in used_ids:
        result = _limit_identifier(f"{candidate}_{suffix}", f"{candidate}_{suffix}")
        suffix += 1
    used_ids.add(result)
    return result


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _contains_option_mark(text: str) -> bool:
    return "□" in text or "☑" in text


def _limit_identifier(base: str, seed: str, max_len: int = 48) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", base).strip("_") or "field"
    if len(base) <= max_len:
        return base
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()[:8]
    prefix_len = max_len - len(digest) - 1
    return f"{base[:prefix_len]}_{digest}"


def _visible_rows(table: ParsedTable) -> list[list[ParsedCell]]:
    rows: list[list[ParsedCell]] = []
    for row in table.rows:
        visible = [cell for cell in row if not cell.is_merged_continuation]
        if any(_normalize_text(cell.text) for cell in visible):
            rows.append(visible)
    return rows
