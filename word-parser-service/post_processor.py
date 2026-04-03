"""
后处理模块：补全 AI 输出的缺失信息
1. 从 field.type 推导 sqlColumn / sqlType
2. 从 word_parser 输出重建 layout.rows / headers / items / sections
"""
from __future__ import annotations
import hashlib
import re
from word_parser import ParsedTable, ParsedCell

try:
    from pypinyin import lazy_pinyin  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    lazy_pinyin = None

# field.type → sqlType 映射
TYPE_TO_SQL: dict[str, str] = {
    "text":           "VARCHAR(200)",
    "number":         "NUMERIC(10,2)",
    "textarea":       "TEXT",
    "date":           "DATE",
    "radio":          "VARCHAR(50)",
    "select":         "VARCHAR(100)",
    "checkbox_group": "JSONB",
    "static":         None,   # 不建列
}

VALID_FIELD_TYPES = set(TYPE_TO_SQL.keys())
VALID_LAYOUT_TYPES = {"key-value", "data-grid", "checklist", "section-group"}
GENERIC_IDENTIFIER_RE = re.compile(r"^(?:field|col|column|item|value|input|sub_form|section|part)_?\d*$")
TRAILING_LABEL_PUNCTUATION_RE = re.compile(r"[：:]+$")


def _slugify_identifier(value: str | None, fallback: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    if not text:
        return fallback
    if text[0].isdigit():
        text = f"{fallback}_{text}"
    return text


def _looks_generic_identifier(value: str | None) -> bool:
    text = (value or "").strip().lower()
    return not text or bool(GENERIC_IDENTIFIER_RE.fullmatch(text))


def _slugify_semantic_identifier(
    preferred_value: str | None,
    label: str | None,
    fallback: str,
) -> str:
    if not _looks_generic_identifier(preferred_value):
        return _slugify_identifier(preferred_value, fallback)

    semantic = _semantic_slug(label)
    if semantic:
        if semantic[0].isdigit():
            semantic = f"{fallback}_{semantic}"
        return semantic
    return fallback


def _semantic_slug(label: str | None) -> str:
    text = (label or "").strip()
    if not text:
        return ""

    direct = _slugify_identifier(text, "")
    if direct:
        return direct

    if lazy_pinyin:
        pinyin_text = "_".join(part for part in lazy_pinyin(text) if part)
        transliterated = _slugify_identifier(pinyin_text, "")
        if transliterated:
            return transliterated

    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"zh_{digest}"


def _ensure_unique(base: str, seen: set[str]) -> str:
    candidate = base
    index = 2
    while candidate in seen:
        candidate = f"{base}_{index}"
        index += 1
    seen.add(candidate)
    return candidate


def _clean_placeholder_label(label: str | None) -> str:
    text = str(label or "").strip()
    text = TRAILING_LABEL_PUNCTUATION_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_field_placeholder(label: str | None, field_type: str) -> str | None:
    cleaned_label = _clean_placeholder_label(label)
    if field_type == "static":
        return None
    if field_type in {"radio", "checkbox_group", "select"}:
        return f"请选择{cleaned_label}" if cleaned_label else "请选择"
    if field_type == "date":
        return f"请选择{cleaned_label}" if cleaned_label else "请选择日期"
    if field_type == "textarea":
        return f"请输入{cleaned_label}" if cleaned_label else "请输入内容"
    if field_type == "number":
        return f"请输入{cleaned_label}" if cleaned_label else "请输入数字"
    return f"请输入{cleaned_label}" if cleaned_label else "请输入"


def _coerce_sub_form(raw_sub_form: object, index: int) -> dict:
    if isinstance(raw_sub_form, dict):
        return dict(raw_sub_form)
    label = str(raw_sub_form).strip() or f"子表{index + 1}"
    return {
        "name": label,
        "layout": {"type": "key-value"},
        "fields": [],
        "recordType": "single",
    }


def _coerce_field(raw_field: object, index: int) -> dict:
    if isinstance(raw_field, dict):
        return dict(raw_field)
    label = str(raw_field).strip() or f"静态内容{index + 1}"
    return {
        "label": label,
        "type": "static",
    }


def normalize_sub_form(sf: dict, index: int) -> dict:
    layout = sf.get("layout")
    if not isinstance(layout, dict):
        layout = {"type": "key-value"}
        sf["layout"] = layout

    layout_type = layout.get("type", "key-value")
    if layout_type not in VALID_LAYOUT_TYPES:
        layout_type = "key-value"
        layout = {"type": "key-value", "rows": layout.get("rows", [])}
        sf["layout"] = layout

    sf["name"] = sf.get("name") or sf.get("title") or f"子表{index + 1}"
    sf["id"] = _slugify_semantic_identifier(sf.get("id"), sf.get("name"), f"sub_form_{index + 1}")
    sf["sqlTableName"] = _slugify_semantic_identifier(sf.get("sqlTableName"), sf.get("name"), f"t_insp_{sf['id']}")
    if not sf["sqlTableName"].startswith("t_insp_"):
        sf["sqlTableName"] = f"t_insp_{sf['sqlTableName']}"
    sf["recordType"] = sf.get("recordType") if sf.get("recordType") in {"single", "multi"} else (
        "multi" if layout_type == "data-grid" else "single"
    )
    return sf


# ---------------------------------------------------------------------------
# 1. 补全字段的 sqlColumn / sqlType
# ---------------------------------------------------------------------------

def fill_field_sql(fields: list[dict]) -> list[dict]:
    """给每个 field 规范化 label/type，并补充 sqlColumn/sqlType。"""
    coerced_fields = [_coerce_field(field, index) for index, field in enumerate(fields or [])]
    seen_ids: set[str] = set()
    seen_columns: set[str] = set()
    for index, f in enumerate(coerced_fields):
        base_label = f.get("label") or f.get("name") or f.get("id") or f"field_{index + 1}"
        f["id"] = _ensure_unique(
            _slugify_semantic_identifier(f.get("id"), str(base_label), f"field_{index + 1}"),
            seen_ids,
        )

        if not f.get("label"):
            f["label"] = base_label

        ftype = f.get("type", "text")
        if ftype not in VALID_FIELD_TYPES:
            # AI 偶尔会把嵌套 data-grid 当成 field.type，这里降级成 textarea，
            # 至少先保证 schema 可消费，后续可再针对嵌套表格单独升级。
            f["type"] = "textarea" if ftype == "data-grid" else "text"

        if (_looks_generic_identifier(f.get("sqlColumn")) or not f.get("sqlColumn")) and f.get("type") != "static":
            f["sqlColumn"] = f["id"]
        if f.get("sqlColumn"):
            f["sqlColumn"] = _ensure_unique(
                _slugify_semantic_identifier(str(f["sqlColumn"]), f.get("label") or f["id"], f["id"]),
                seen_columns,
            )
        if not f.get("sqlType"):
            f["sqlType"] = TYPE_TO_SQL.get(f.get("type", "text"))
        if not f.get("placeholder"):
            f["placeholder"] = _build_field_placeholder(f.get("label"), f.get("type", "text"))
    return coerced_fields


# ---------------------------------------------------------------------------
# 2. 判断一个单元格文本是否是「标签」
# ---------------------------------------------------------------------------

def _is_label_cell(text: str) -> bool:
    """非空且不含 □ 选项的格子认为是标签"""
    return bool(text.strip()) and "□" not in text


def _is_empty_cell(text: str) -> bool:
    return not text.strip()


def _map_align(value: str | None) -> str | None:
    mapping = {
        "left": "left",
        "start": "left",
        "center": "center",
        "right": "right",
        "end": "right",
        "both": "justify",
        "distribute": "justify",
    }
    return mapping.get((value or "").lower())


def _map_v_align(value: str | None) -> str | None:
    mapping = {
        "top": "top",
        "center": "middle",
        "bottom": "bottom",
    }
    return mapping.get((value or "").lower())


def _cell_style(cell: ParsedCell) -> dict | None:
    style = {
        "widthPx": max(24, round(cell.width_twips / 15)) if cell.width_twips else None,
        "textAlign": _map_align(cell.align),
        "verticalAlign": _map_v_align(cell.v_align),
        "backgroundColor": f"#{cell.shading}" if cell.shading else None,
        "borderTop": cell.border_top,
        "borderRight": cell.border_right,
        "borderBottom": cell.border_bottom,
        "borderLeft": cell.border_left,
        "fontWeight": "bold" if cell.is_bold else None,
        "fontSizePx": cell.font_size_px,
        "fontFamily": cell.font_family,
    }
    compact = {k: v for k, v in style.items() if v is not None}
    return compact or None


# ---------------------------------------------------------------------------
# 3. key-value layout：从 word parser 重建 rows
# ---------------------------------------------------------------------------

def build_key_value_rows(table: ParsedTable, fields: list[dict]) -> list[list[dict]]:
    """
    遍历 word parser 的行，把每个 cell 标记为 label / input / static
    空格子按顺序匹配 fields 中的非 static 字段
    """
    input_fields = [f for f in fields if f.get("type") != "static"]
    field_iter = iter(input_fields)
    current_field = next(field_iter, None)

    rows = []
    for parsed_row in table.rows:
        visible = [c for c in parsed_row if not c.is_merged_continuation]
        row_cells = []
        for cell in visible:
            cs = cell.colspan
            rs = cell.rowspan
            if _is_empty_cell(cell.text):
                if current_field:
                    row_cells.append({
                        "kind": "input",
                        "fieldId": current_field["id"],
                        "colspan": cs,
                        "rowspan": rs,
                        "style": _cell_style(cell),
                    })
                    current_field = next(field_iter, None)
                else:
                    row_cells.append({
                        "kind": "static",
                        "text": "",
                        "colspan": cs,
                        "rowspan": rs,
                        "style": _cell_style(cell),
                    })
            elif _is_label_cell(cell.text):
                # 签名行（含"检查："或"审核："且没有对应 field）→ static
                is_signature = any(kw in cell.text for kw in ["检查：", "审核：", "批准：", "检验机构", "检验人员"])
                if is_signature:
                    row_cells.append({
                        "kind": "static",
                        "text": cell.text,
                        "colspan": cs,
                        "rowspan": rs,
                        "style": _cell_style(cell),
                    })
                else:
                    row_cells.append({
                        "kind": "label",
                        "text": cell.text.strip(),
                        "colspan": cs,
                        "rowspan": rs,
                        "style": _cell_style(cell),
                    })
            else:
                row_cells.append({
                    "kind": "static",
                    "text": cell.text,
                    "colspan": cs,
                    "rowspan": rs,
                    "style": _cell_style(cell),
                })
        if row_cells:
            rows.append(row_cells)
    return rows


def build_key_value_rows_from_fields(fields: list[dict]) -> list[list[dict]]:
    rows = []
    for field in fields:
        if field.get("type") == "static":
            rows.append([{"kind": "static", "text": field.get("label", "")}])
        else:
            rows.append([
                {"kind": "label", "text": field.get("label", field.get("id", ""))},
                {"kind": "input", "fieldId": field["id"]},
            ])
    return rows


# ---------------------------------------------------------------------------
# 4. data-grid layout：从 word parser 推断表头和数据列
# ---------------------------------------------------------------------------

def build_data_grid_layout(table: ParsedTable, fields: list[dict], existing_layout: dict) -> dict:
    """
    自动推断表头行数（连续有内容的行）和数据列
    """
    non_prefix_fields = [f for f in fields if not f.get("isPrefix") and f.get("type") != "static"]

    # 如果 AI 已给了 columns，用 field id 顺序作 dataColumns
    data_columns = [f["id"] for f in non_prefix_fields]

    # 从 word parser 提取表头（直到出现全空行为止，最多前 3 行）
    header_rows = []
    for ri, parsed_row in enumerate(table.rows[:4]):
        visible = [c for c in parsed_row if not c.is_merged_continuation]
        texts = [c.text.strip() for c in visible]
        if all(t == "" for t in texts):
            break   # 全空行 = 数据开始
        header_cells = []
        for cell in visible:
            header_cells.append({
                "text": cell.text.strip(),
                "colspan": cell.colspan,
                "rowspan": cell.rowspan,
                "style": _cell_style(cell),
            })
        header_rows.append(header_cells)

    # 估算数据行数（总行数 - 表头行数 - 1（签名行））
    default_row_count = max(5, len(table.rows) - len(header_rows) - 1)

    return {
        "type": "data-grid",
        "headers": header_rows if header_rows else existing_layout.get("headers", []),
        "dataColumns": data_columns,
        "prefixFields": existing_layout.get("prefixFields", []),
        "defaultRowCount": default_row_count,
    }


def build_data_grid_layout_from_fields(fields: list[dict], existing_layout: dict) -> dict:
    non_prefix_fields = [f for f in fields if not f.get("isPrefix") and f.get("type") != "static"]
    header_row = [{
        "text": field.get("label", field["id"]),
        "colspan": 1,
        "rowspan": 1,
    } for field in non_prefix_fields]
    return {
        "type": "data-grid",
        "headers": existing_layout.get("headers") or ([header_row] if header_row else []),
        "dataColumns": existing_layout.get("dataColumns") or [field["id"] for field in non_prefix_fields],
        "prefixFields": existing_layout.get("prefixFields", []),
        "defaultRowCount": existing_layout.get("defaultRowCount", 5),
    }


# ---------------------------------------------------------------------------
# 5. checklist layout：从 word parser 重建 items
# ---------------------------------------------------------------------------

def build_checklist_items(table: ParsedTable, fields: list[dict]) -> list[dict]:
    """
    从 word parser 行中提取 checklist items
    有跨行（rowspan > 1）的标签格 → 父项带子项
    """
    input_fields = [f for f in fields if f.get("type") != "static"]
    field_iter = iter(input_fields)

    items = []
    rows = table.rows
    ri = 0
    while ri < len(rows):
        parsed_row = rows[ri]
        visible = [c for c in parsed_row if not c.is_merged_continuation]
        if not visible:
            ri += 1
            continue

        first_cell = visible[0]
        # 检查是否是合并行（签名行）→ 跳过
        if any(kw in first_cell.text for kw in ["检查：", "审核："]):
            ri += 1
            continue

        # 序号格
        seq = first_cell.text.strip() if len(visible) > 1 else ""

        if first_cell.rowspan > 1:
            # 父项（含子项）
            parent_label = visible[1].text.strip() if len(visible) > 1 else first_cell.text.strip()
            sub_items = []
            # 当前行的子项
            if len(visible) > 2:
                sub_label = visible[2].text.strip()
                f = next(field_iter, None)
                rf = next(field_iter, None)
                sub_item = {"label": sub_label}
                if f:
                    sub_item["fieldId"] = f["id"]
                if rf:
                    sub_item["remarkFieldId"] = rf["id"]
                sub_items.append(sub_item)
            # 续行
            for _ in range(first_cell.rowspan - 1):
                ri += 1
                if ri >= len(rows):
                    break
                cont_row = rows[ri]
                cont_visible = [c for c in cont_row if not c.is_merged_continuation]
                if cont_visible:
                    sub_label = cont_visible[0].text.strip()
                    f = next(field_iter, None)
                    rf = next(field_iter, None)
                    sub_item = {"label": sub_label}
                    if f:
                        sub_item["fieldId"] = f["id"]
                    if rf:
                        sub_item["remarkFieldId"] = rf["id"]
                    sub_items.append(sub_item)
            items.append({"seq": seq, "label": parent_label, "subItems": sub_items})
        else:
            # 普通行
            label = visible[1].text.strip() if len(visible) > 1 else first_cell.text.strip()
            f = next(field_iter, None)
            rf = next(field_iter, None)
            item = {"seq": seq, "label": label}
            if f:
                item["fieldId"] = f["id"]
            if rf:
                item["remarkFieldId"] = rf["id"]
            items.append(item)

        ri += 1

    return items


def build_checklist_items_from_fields(fields: list[dict]) -> list[dict]:
    items = []
    sequence = 1
    for field in fields:
        if field.get("type") == "static":
            continue
        items.append({
            "seq": str(sequence),
            "label": field.get("label", field["id"]),
            "fieldId": field["id"],
        })
        sequence += 1
    return items


def normalize_checklist_columns(columns: list) -> list[str]:
    normalized: list[str] = []
    for column in columns or []:
        if isinstance(column, str):
            normalized.append(column)
            continue
        if isinstance(column, dict):
            label = column.get("label") or column.get("text") or column.get("name")
            if label:
                normalized.append(str(label))
                continue
        if column is not None:
            normalized.append(str(column))
    return normalized


# ---------------------------------------------------------------------------
# 6. section-group layout：从 word parser 重建 sections
# ---------------------------------------------------------------------------

def build_section_group(table: ParsedTable, fields: list[dict]) -> dict:
    """
    每次遇到全行合并单元格（colspan 等于最大列数）认为是 section 标题
    其余行按 label-input 对处理
    """
    max_cols = table.col_count
    input_fields = [f for f in fields if f.get("type") != "static"]
    field_iter = iter(input_fields)

    sections = []
    current_section = None

    for parsed_row in table.rows:
        visible = [c for c in parsed_row if not c.is_merged_continuation]
        if not visible:
            continue

        texts = [c.text.strip() for c in visible]
        all_empty = all(t == "" for t in texts)
        if all_empty:
            continue

        # 签名行 → 跳过
        if any(kw in texts[0] for kw in ["检查：", "审核：", "批准："]):
            continue

        # 判断是否是 section 标题（单格 + colspan 覆盖大部分列）
        is_title = len(visible) == 1 and visible[0].colspan >= max(2, max_cols // 2)
        if is_title:
            current_section = {
                "title": texts[0],
                "titleStyle": _cell_style(visible[0]),
                "rows": [],
            }
            sections.append(current_section)
            continue

        # 普通字段行：每两格一对 (label, input)
        if current_section is None:
            current_section = {"title": "", "rows": []}
            sections.append(current_section)

        row_items = []
        i = 0
        while i < len(visible):
            label_cell = visible[i]
            input_cell = visible[i + 1] if i + 1 < len(visible) else None
            f = next(field_iter, None)
            item = {
                "label": label_cell.text.strip(),
                "fieldId": f["id"] if f else f"_field_{i}",
                "colspan": input_cell.colspan if input_cell else 1,
                "labelColspan": label_cell.colspan,
                "labelStyle": _cell_style(label_cell),
                "inputStyle": _cell_style(input_cell) if input_cell else None,
            }
            row_items.append(item)
            i += 2  # 跳过 input 格

        if row_items:
            current_section["rows"].append(row_items)

    return {"type": "section-group", "sections": sections}


def normalize_section_group_layout(layout: dict, fields: list[dict]) -> dict:
    """
    AI 若已给 sections 但只写了 fieldIds，没有 rows，这里降级重建成可渲染 rows。
    """
    sections = layout.get("sections", [])
    if not sections:
        return {
            "type": "section-group",
            "sections": [{
                "title": "",
                "rows": _build_section_rows_from_field_ids(
                    [field["id"] for field in fields],
                    {field["id"]: field for field in fields},
                ),
            }],
        }

    field_map = {field["id"]: field for field in fields}
    normalized_sections = []

    for section in sections:
        rows = section.get("rows")
        if _is_valid_section_rows(rows):
            normalized_sections.append(section)
            continue

        field_ids = section.get("fieldIds", [])
        if not field_ids and isinstance(rows, list):
            field_ids = _extract_section_field_ids(rows)
        normalized_sections.append({
            "title": section.get("title", ""),
            "rows": _build_section_rows_from_field_ids(field_ids, field_map),
        })

    return {
        "type": "section-group",
        "sections": normalized_sections,
    }


def needs_section_group_rebuild(layout: dict) -> bool:
    sections = layout.get("sections")
    if not sections:
        return True
    return any(not _is_valid_section_rows(section.get("rows")) for section in sections)


def _build_section_rows_from_field_ids(field_ids: list[str], field_map: dict[str, dict]) -> list[list[dict]]:
    row_items = []
    current_row = []

    for field_id in field_ids:
        field = field_map.get(field_id)
        if not field:
            continue
        current_row.append({
            "label": field.get("label", field_id),
            "fieldId": field_id,
            "labelColspan": 1,
            "colspan": 3 if field.get("type") in {"textarea", "static"} else 1,
        })
        if len(current_row) == 2 or field.get("type") in {"textarea", "static"}:
            row_items.append(current_row)
            current_row = []

    if current_row:
        row_items.append(current_row)

    return row_items


def _is_valid_section_rows(rows: object) -> bool:
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, list):
            return False
        for item in row:
            if not isinstance(item, dict):
                return False
    return True


def _extract_section_field_ids(rows: list) -> list[str]:
    field_ids: list[str] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        for item in row:
            if isinstance(item, dict) and item.get("fieldId"):
                field_ids.append(item["fieldId"])
    return field_ids


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def post_process(sub_forms: list[dict], tables: list[ParsedTable]) -> list[dict]:
    """
    对 AI 输出的 sub_forms 做后处理：
    1. 补全 sqlColumn / sqlType
    2. 重建 layout 结构
    """
    normalized_sub_forms = [_coerce_sub_form(sub_form, index) for index, sub_form in enumerate(sub_forms or [])]
    for i, sf in enumerate(normalized_sub_forms):
        sf = normalize_sub_form(sf, i)
        # 补全字段 SQL 信息
        sf["fields"] = fill_field_sql(sf.get("fields", []))

        layout = sf.get("layout", {})
        layout_type = layout.get("type", "key-value")
        fields = sf["fields"]

        # 找对应的 word parser 表格（按顺序）
        table = tables[i] if i < len(tables) else None

        if table is None:
            if layout_type == "key-value":
                sf["layout"] = {
                    "type": "key-value",
                    "rows": layout.get("rows") or build_key_value_rows_from_fields(fields),
                }
            elif layout_type == "data-grid":
                sf["layout"] = build_data_grid_layout_from_fields(fields, layout)
            elif layout_type == "checklist":
                sf["layout"] = {
                    "type": "checklist",
                    "columns": normalize_checklist_columns(layout.get("columns")) or ["序号", "检查项目", "检查结果"],
                    "items": layout.get("items") or build_checklist_items_from_fields(fields),
                }
            elif layout_type == "section-group":
                sf["layout"] = normalize_section_group_layout(layout, fields)
            continue

        if layout_type == "key-value" and not layout.get("rows"):
            layout["rows"] = build_key_value_rows(table, fields)

        elif layout_type == "data-grid" and (not layout.get("headers") or not layout.get("dataColumns")):
            sf["layout"] = build_data_grid_layout(table, fields, layout)

        elif layout_type == "checklist" and not layout.get("items"):
            layout["items"] = build_checklist_items(table, fields)
            layout["columns"] = normalize_checklist_columns(layout.get("columns")) or ["序号", "检查项目", "检查结果", "备注"]

        elif layout_type == "section-group":
            if needs_section_group_rebuild(layout):
                rebuilt = build_section_group(table, fields)
                if rebuilt.get("sections"):
                    sf["layout"] = rebuilt
                else:
                    sf["layout"] = normalize_section_group_layout(layout, fields)
            else:
                sf["layout"] = normalize_section_group_layout(layout, fields)
        elif layout_type == "checklist":
            layout["columns"] = normalize_checklist_columns(layout.get("columns")) or ["序号", "检查项目", "检查结果", "备注"]

    return normalized_sub_forms
