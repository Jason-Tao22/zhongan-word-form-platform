"""
高保真 HTML 原型构建器。

思路：
1. 直接复用 Word 的表格结构和显示元数据
2. 如果有 schema，则把字段控件嵌入相应单元格，形成可填写原型
3. 原型支持本地草稿、导出 JSON、清空
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape
from typing import Any

TRAILING_FILL_EXCLUDE_KEYWORDS = ("说明", "备注", "内容", "情况")
TRAILING_FILL_WIDTH_RULES = (
    (re.compile(r"日期|时间|年月日"), 7.2),
    (re.compile(r"人员|代表|签字|签名|联系人"), 9.0),
    (re.compile(r"编号|代码|证号|型号|规格|电话|地址"), 8.0),
    (re.compile(r"单位|名称"), 9.0),
)
IMPLICIT_FILL_LABEL_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9（）()]{1,20}[：:]")
BOX_OPTION_RE = re.compile(r"[□☐☑■]\s*([^\s□☐☑■]+)")
CIRCLE_OPTION_RE = re.compile(r"[○◯●〇]\s*([^\s○◯●〇]+)")
INLINE_GAP_RE = re.compile(r"(?:\u3000| ){3,}|[_＿﹍﹎‗—-]{3,}")
CHOICE_OPTION_LEFT_CONTEXT_RE = re.compile(r"[□☐☑■○◯●〇]\s*[^\s□☐☑■○◯●〇_＿﹍﹎‗—-]+$")
CHOICE_OPTION_RIGHT_CONTEXT_RE = re.compile(r"^\s*[□☐☑■○◯●〇]")


@dataclass
class CellBinding:
    key: str
    field: dict[str, Any]
    mode: str = "replace"
    hint_text: str | None = None
    sub_form_id: str | None = None
    row_index: int | None = None


@dataclass
class InlineFieldBindingState:
    sub_form_id: str | None
    available_fields: list[dict[str, Any]]
    last_matched_field: dict[str, Any] | None = None


def twips_to_px(value: int | None) -> int | None:
    if value is None:
        return None
    return max(24, round(value / 15))


def map_align(value: str | None) -> str:
    mapping = {
        "left": "left",
        "start": "left",
        "center": "center",
        "right": "right",
        "end": "right",
        "both": "justify",
        "distribute": "justify",
    }
    return mapping.get((value or "").lower(), "left")


def map_valign(value: str | None) -> str:
    mapping = {
        "top": "top",
        "center": "middle",
        "bottom": "bottom",
    }
    return mapping.get((value or "").lower(), "middle")


def build_prototype_html(
    title: str,
    docx_name: str,
    tables,
    sub_forms: list[dict] | None = None,
    blocks: list[dict] | None = None,
    ai_hints: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> str:
    binding_maps = _build_binding_maps(tables, sub_forms or [])
    ai_hints = ai_hints or {"paragraphs": {}, "cells": {}}

    sections: list[str] = []
    if blocks:
        for block in blocks:
            if block["kind"] == "paragraph":
                sections.append(_render_document_paragraph(block["paragraph"], ai_hints))
            elif block["kind"] == "table":
                table = block["table"]
                sub_form = sub_forms[table.index] if sub_forms and table.index < len(sub_forms) else None
                sections.append(_render_table_section(table, sub_form, binding_maps.get(table.index, {}), ai_hints))
    else:
        for table in tables:
            sub_form = sub_forms[table.index] if sub_forms and table.index < len(sub_forms) else None
            sections.append(_render_table_section(table, sub_form, binding_maps.get(table.index, {}), ai_hints))

    storage_key = f"prototype::{title}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --paper: #ffffff;
      --paper-edge: #d7d7d7;
      --ink: #111111;
      --grid: #bfbfbf;
      --empty: #ffffff;
      --input-bg: #ffffff;
      --muted: #666666;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      padding: 24px 18px 48px;
      color: var(--ink);
      background: #eef2f7;
      font-family: "Songti SC", "STSong", "SimSun", serif;
    }}
    .workspace {{
      max-width: 1320px;
      margin: 0 auto;
      display: grid;
      gap: 12px;
    }}
    .workspace-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px 14px;
      background: #ffffff;
      border: 1px solid #d7deea;
      box-shadow: 0 10px 22px rgba(15, 23, 42, 0.06);
    }}
    .workspace-copy {{
      display: grid;
      gap: 4px;
    }}
    .workspace-title {{
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .workspace-subtitle {{
      font-size: 12px;
      color: var(--muted);
    }}
    .page {{
      max-width: 1200px;
      margin: 0 auto;
      background: var(--paper);
      border: 1px solid var(--paper-edge);
      box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
      padding: 18px 14px 20px;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: flex-end;
    }}
    .tool-btn {{
      border: 1px solid rgba(28, 28, 28, 0.16);
      background: white;
      padding: 10px 14px;
      font: inherit;
      cursor: pointer;
      transition: transform 120ms ease, box-shadow 120ms ease;
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.05);
    }}
    .tool-btn:hover {{
      transform: translateY(-1px);
    }}
    .tool-btn.primary {{
      background: #f5f8ff;
    }}
    .table-section {{
      margin-top: 8px;
    }}
    .doc-paragraph-block {{
      margin: 6px 0;
      font-size: 14px;
      line-height: 1.7;
      white-space: normal;
    }}
    .doc-paragraph-block.is-bold {{
      font-weight: 700;
    }}
    .doc-paragraph-block.is-note {{
      font-size: 12px;
      margin-top: 10px;
    }}
    .align-left {{
      text-align: left;
    }}
    .align-center {{
      text-align: center;
    }}
    .align-right {{
      text-align: right;
    }}
    .align-justify {{
      text-align: justify;
    }}
    .docx-table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: auto;
      background: var(--paper);
    }}
    .docx-cell {{
      border: 1px solid var(--grid);
      padding: 6px 8px;
      font-size: 14px;
      line-height: 1.6;
      background: #ffffff;
      word-break: break-word;
      position: relative;
    }}
    .docx-cell.is-emphasis {{
      background: #fafafa;
    }}
    .docx-cell.is-empty {{
      background: var(--empty);
    }}
    .docx-paragraph + .docx-paragraph {{
      margin-top: 4px;
    }}
    .docx-paragraph.blank-line {{
      min-height: 1.6em;
    }}
    .control-wrap {{
      margin-top: 6px;
      display: grid;
      gap: 6px;
    }}
    .control-wrap.replace {{
      margin-top: 0;
    }}
    .field-note {{
      font-size: 11px;
      color: rgba(28, 28, 28, 0.48);
    }}
    .inline-fill,
    .prototype-input,
    .prototype-select,
    .prototype-textarea {{
      border: 1px solid rgba(28, 28, 28, 0.22);
      background: var(--input-bg);
      font: inherit;
      color: var(--ink);
      border-radius: 0;
      padding: 4px 6px;
    }}
    .inline-fill {{
      display: inline-block;
      vertical-align: baseline;
      min-width: 3.5em;
      border-top: none;
      border-left: none;
      border-right: none;
      padding: 0 2px 1px;
      line-height: 1.2;
      margin: 0 2px;
    }}
    .prototype-input,
    .prototype-select,
    .prototype-textarea {{
      width: 100%;
    }}
    .prototype-input,
    .prototype-select {{
      min-height: 34px;
    }}
    .prototype-textarea {{
      min-height: 92px;
      resize: vertical;
    }}
    .choice-group {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
    }}
    .inline-choice-group {{
      display: inline-flex;
      vertical-align: baseline;
      margin: 0 4px;
      gap: 6px 12px;
    }}
    .choice-item {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      white-space: nowrap;
      font-size: 13px;
    }}
    .inline-choice-item input {{
      margin: 0;
    }}
    .choice-clear {{
      border: none;
      background: transparent;
      color: #4b5563;
      cursor: pointer;
      font: inherit;
      padding: 0 0 0 4px;
    }}
    .footer {{
      margin: 0 auto;
      max-width: 1200px;
      padding: 18px;
      border: 1px solid #d7deea;
      background: #ffffff;
      box-shadow: 0 10px 22px rgba(15, 23, 42, 0.06);
      display: grid;
      gap: 8px;
    }}
    .footer textarea {{
      width: 100%;
      min-height: 160px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      padding: 12px;
      border: 1px solid #d3d9e6;
      background: #ffffff;
    }}
    @media (max-width: 900px) {{
      body {{
        padding: 16px 10px 30px;
      }}
      .page {{
        padding: 18px 14px 28px;
      }}
      .docx-cell {{
        padding: 4px 5px;
        font-size: 12px;
      }}
      .tool-btn {{
        width: 100%;
        justify-content: center;
      }}
      .toolbar {{
        justify-content: stretch;
      }}
    }}
  </style>
</head>
<body>
  <main class="workspace">
    <section class="workspace-bar">
      <div class="workspace-copy">
        <div class="workspace-title">Word 原型预览</div>
        <div class="workspace-subtitle">源文件：{escape(docx_name)}</div>
      </div>
      <div class="toolbar">
        <button class="tool-btn primary" type="button" onclick="saveDraft()">保存草稿</button>
        <button class="tool-btn" type="button" onclick="exportJson()">导出 JSON</button>
        <button class="tool-btn" type="button" onclick="clearDraft()">清空</button>
      </div>
    </section>

    <article class="page">
      {''.join(sections)}
    </article>

    <section class="footer">
      <strong>导出预览</strong>
      <textarea id="jsonOutput" spellcheck="false" placeholder="点击“导出 JSON”后，这里会显示当前填写结果。"></textarea>
    </section>
  </main>

  <script>
    const STORAGE_KEY = {json.dumps(storage_key, ensure_ascii=False)};

    function getValue(el) {{
      if (el.type === 'radio') {{
        return el.checked ? el.value : undefined;
      }}
      if (el.type === 'checkbox') {{
        return el.checked;
      }}
      return el.value;
    }}

    function setValue(el, value) {{
      if (el.type === 'radio') {{
        el.checked = el.value === value;
        return;
      }}
      if (el.type === 'checkbox') {{
        el.checked = Boolean(value);
        return;
      }}
      el.value = value ?? '';
    }}

    function collectData() {{
      const data = {{}};
      const elements = document.querySelectorAll('[data-key]');
      elements.forEach((el) => {{
        const key = el.dataset.key;
        if (!key) return;
        if (el.type === 'radio') {{
          if (!el.checked) return;
          data[key] = el.value;
          return;
        }}
        if (el.dataset.group === 'checkbox_group') {{
          if (!data[key]) data[key] = [];
          if (el.checked) data[key].push(el.value);
          return;
        }}
        data[key] = getValue(el);
      }});
      return data;
    }}

    function writeOutput(data) {{
      document.getElementById('jsonOutput').value = JSON.stringify(data, null, 2);
    }}

    function saveDraft() {{
      const data = collectData();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      writeOutput(data);
    }}

    function loadDraft() {{
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      const elements = document.querySelectorAll('[data-key]');
      elements.forEach((el) => {{
        const key = el.dataset.key;
        if (!(key in data)) return;
        if (el.dataset.group === 'checkbox_group') {{
          el.checked = Array.isArray(data[key]) && data[key].includes(el.value);
          return;
        }}
        setValue(el, data[key]);
      }});
      writeOutput(data);
    }}

    function clearDraft() {{
      localStorage.removeItem(STORAGE_KEY);
      const elements = document.querySelectorAll('[data-key]');
      elements.forEach((el) => {{
        if (el.type === 'radio' || el.type === 'checkbox') {{
          el.checked = false;
        }} else {{
          el.value = '';
        }}
      }});
      writeOutput({{}});
    }}

    function exportJson() {{
      const data = collectData();
      writeOutput(data);
      const blob = new Blob([JSON.stringify(data, null, 2)], {{ type: 'application/json;charset=utf-8' }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = {json.dumps(f"{title}-prototype-data.json", ensure_ascii=False)};
      link.click();
      URL.revokeObjectURL(url);
    }}

    document.addEventListener('pointerdown', (event) => {{
      const el = event.target;
      if (!(el instanceof HTMLInputElement)) return;
      if (el.type !== 'radio' || el.dataset.toggleable !== 'true') return;
      el.dataset.wasChecked = el.checked ? '1' : '0';
    }});

    document.addEventListener('click', (event) => {{
      const el = event.target;
      if (!(el instanceof HTMLInputElement)) return;
      if (el.type !== 'radio' || el.dataset.toggleable !== 'true') return;
      if (el.dataset.wasChecked !== '1') return;
      event.preventDefault();
      el.checked = false;
      delete el.dataset.wasChecked;
      writeOutput(collectData());
    }});

    document.addEventListener('change', () => writeOutput(collectData()));
    document.addEventListener('DOMContentLoaded', loadDraft);
  </script>
</body>
</html>
"""


def build_document_blocks(
    tables,
    sub_forms: list[dict] | None = None,
    blocks: list[dict] | None = None,
    ai_hints: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    binding_maps = _build_binding_maps(tables, sub_forms or [])
    ai_hints = ai_hints or {"paragraphs": {}, "cells": {}}
    document_blocks: list[dict[str, Any]] = []

    if blocks:
        for block in blocks:
            if block["kind"] == "paragraph":
                document_blocks.append(_build_document_paragraph_block(block["paragraph"], ai_hints))
            elif block["kind"] == "table":
                table = block["table"]
                sub_form = sub_forms[table.index] if sub_forms and table.index < len(sub_forms) else None
                document_blocks.append(_build_document_table_block(table, sub_form, binding_maps.get(table.index, {}), ai_hints))
    else:
        for table in tables:
            sub_form = sub_forms[table.index] if sub_forms and table.index < len(sub_forms) else None
            document_blocks.append(_build_document_table_block(table, sub_form, binding_maps.get(table.index, {}), ai_hints))

    return document_blocks


def _render_table_section(
    table,
    sub_form: dict[str, Any] | None,
    binding_map: dict[tuple[int, int], CellBinding],
    ai_hints: dict[str, dict[str, dict[str, Any]]],
) -> str:
    inline_binding_state = _build_inline_binding_state(sub_form, binding_map)
    rows_html: list[str] = []
    for ri, row in enumerate(table.rows):
        visible_cells = [cell for cell in row if not cell.is_merged_continuation]
        if not visible_cells:
            continue
        row_html = "".join(
            _render_cell_html(table, ri, ci, cell, binding_map.get((ri, ci)), ai_hints, inline_binding_state)
            for ci, cell in enumerate(visible_cells)
        )
        rows_html.append(f"<tr>{row_html}</tr>")

    return f'<section class="table-section"><table class="docx-table"><tbody>{"".join(rows_html)}</tbody></table></section>'


def _render_document_paragraph(paragraph, ai_hints: dict[str, dict[str, dict[str, Any]]]) -> str:
    align = map_align(getattr(paragraph, "align", None))
    classes = [f"align-{align}", "doc-paragraph-block"]
    if getattr(paragraph, "is_bold", False):
        classes.append("is-bold")
    if paragraph.text.startswith("注："):
        classes.append("is-note")
    html, _ = _render_inline_fill_text(
        paragraph.text,
        f"doc::paragraph::{paragraph.index}",
        ai_hints.get("paragraphs", {}).get(f"doc::paragraph::{paragraph.index}"),
    )
    style_parts: list[str] = []
    if getattr(paragraph, "font_size_px", None):
        style_parts.append(f'font-size:{paragraph.font_size_px}px')
    if getattr(paragraph, "font_family", None):
        style_parts.append(f'font-family:"{escape(paragraph.font_family)}", serif')
    style_attr = f' style="{";".join(style_parts)}"' if style_parts else ""
    return f'<p class="{" ".join(classes)}"{style_attr}>{html}</p>'


def _render_cell_html(
    table,
    row_index: int,
    col_index: int,
    cell,
    binding: CellBinding | None,
    ai_hints: dict[str, dict[str, dict[str, Any]]],
    inline_binding_state: InlineFieldBindingState | None = None,
) -> str:
    styles: list[str] = []
    width_px = twips_to_px(cell.width_twips)
    if width_px:
        styles.append(f"min-width:{width_px}px")
    styles.append(f"text-align:{map_align(cell.align)}")
    styles.append(f"vertical-align:{map_valign(cell.v_align)}")
    if cell.shading:
        styles.append(f"background:#{cell.shading}")
    if getattr(cell, "border_top", None):
        styles.append(f"border-top:{cell.border_top}")
    if getattr(cell, "border_right", None):
        styles.append(f"border-right:{cell.border_right}")
    if getattr(cell, "border_bottom", None):
        styles.append(f"border-bottom:{cell.border_bottom}")
    if getattr(cell, "border_left", None):
        styles.append(f"border-left:{cell.border_left}")
    if cell.is_bold:
        styles.append("font-weight:700")
    if getattr(cell, "font_size_px", None):
        styles.append(f"font-size:{cell.font_size_px}px")
    if getattr(cell, "font_family", None):
        styles.append(f'font-family:"{escape(cell.font_family)}", serif')

    class_names = ["docx-cell"]
    if cell.is_bold or cell.shading:
        class_names.append("is-emphasis")
    if not cell.text.strip():
        class_names.append("is-empty")

    paragraphs = cell.paragraphs or ([cell.text] if cell.text else [])
    rendered_paragraphs: list[str] = []
    inline_fill_count = 0
    paragraph_hints = ai_hints.get("paragraphs", {})
    for pi, paragraph in enumerate(paragraphs):
        if paragraph.strip():
            paragraph_binding_state = None
            if inline_binding_state:
                paragraph_binding_state = InlineFieldBindingState(
                    inline_binding_state.sub_form_id,
                    inline_binding_state.available_fields,
                )
            html, count = _render_inline_fill_text(
                paragraph,
                f"auto::{table.index}::{row_index}::{col_index}::paragraph::{pi}",
                paragraph_hints.get(f"table::{table.index}::cell::{row_index}::{col_index}::paragraph::{pi}"),
                paragraph_binding_state,
            )
            inline_fill_count += count
            rendered_paragraphs.append(f'<div class="docx-paragraph">{html}</div>')
        else:
            rendered_paragraphs.append('<div class="docx-paragraph blank-line"></div>')
    text_blocks = "".join(rendered_paragraphs)

    control_block = _render_binding(binding) if binding else ""
    cell_hint = ai_hints.get("cells", {}).get(f"table::{table.index}::cell::{row_index}::{col_index}")
    if not control_block and _should_render_auto_control(table, cell, paragraphs, inline_fill_count, cell_hint):
        control_block = _render_auto_control(table, row_index, col_index, cell, paragraphs, cell_hint)

    if binding and binding.mode == "replace" and not text_blocks:
        inner = control_block
    elif binding and binding.mode == "replace" and text_blocks:
        inner = control_block
    else:
        inner = text_blocks + control_block

    return (
        f'<td class="{" ".join(class_names)}" '
        f'colspan="{cell.colspan}" rowspan="{cell.rowspan}" '
        f'style="{";".join(styles)}">{inner}</td>'
    )


def _render_binding(binding: CellBinding) -> str:
    field = binding.field
    field_type = field.get("type", "text")
    options = field.get("options") or []
    key = escape(binding.key)
    field_id = escape(field.get("id", "field"))

    if field_type == "textarea":
        control = f'<textarea class="prototype-textarea" data-key="{key}" data-field-id="{field_id}"></textarea>'
    elif field_type == "date":
        control = f'<input class="prototype-input" type="date" data-key="{key}" data-field-id="{field_id}" />'
    elif field_type == "number":
        control = f'<input class="prototype-input" type="number" step="any" data-key="{key}" data-field-id="{field_id}" />'
    elif field_type == "select":
        options = ['<option value=""></option>'] + [
            f'<option value="{escape(option)}">{escape(option)}</option>'
            for option in options
        ]
        control = f'<select class="prototype-select" data-key="{key}" data-field-id="{field_id}">{"".join(options)}</select>'
    elif field_type == "radio":
        items = []
        for option in options:
            safe_option = escape(option)
            items.append(
                f'<label class="choice-item"><input type="radio" data-key="{key}" '
                f'data-field-id="{field_id}" value="{safe_option}" />{safe_option}</label>'
            )
        control = f'<div class="choice-group">{"".join(items)}</div>'
    elif field_type == "checkbox_group":
        items = []
        for option in options:
            safe_option = escape(option)
            items.append(
                f'<label class="choice-item"><input type="checkbox" data-key="{key}" '
                f'data-group="checkbox_group" data-field-id="{field_id}" value="{safe_option}" />{safe_option}</label>'
            )
        control = f'<div class="choice-group">{"".join(items)}</div>'
    else:
        control = f'<input class="prototype-input" type="text" data-key="{key}" data-field-id="{field_id}" />'

    mode = "replace" if binding.mode == "replace" else "append"
    return f'<div class="control-wrap {mode}">{control}</div>'


def _render_inline_fill_text(
    text: str,
    key_prefix: str,
    paragraph_hint: dict[str, Any] | None = None,
    inline_binding_state: InlineFieldBindingState | None = None,
) -> tuple[str, int]:
    tokens, count = _build_inline_fill_tokens(text, key_prefix, paragraph_hint, inline_binding_state)
    return _render_tokens_html(tokens), count


def _should_render_auto_control(
    table,
    cell,
    paragraphs: list[str],
    inline_fill_count: int,
    cell_hint: dict[str, Any] | None = None,
) -> bool:
    if cell_hint and cell_hint.get("fieldType") in {"text", "textarea"}:
        return True
    if cell_hint and cell_hint.get("fieldType") == "none":
        return False

    if inline_fill_count > 0:
        return False

    if not paragraphs:
        return True

    non_empty = [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]
    if not non_empty:
        return True

    if any(not paragraph.strip() for paragraph in paragraphs):
        return non_empty[-1].endswith(("：", ":"))

    if len(non_empty) == 1 and non_empty[0].endswith(("：", ":")):
        return cell.colspan >= max(2, table.col_count - 1) or cell.rowspan > 1

    return False


def _render_auto_control(
    table,
    row_index: int,
    col_index: int,
    cell,
    paragraphs: list[str],
    cell_hint: dict[str, Any] | None = None,
) -> str:
    payload = _build_auto_control_payload(table, row_index, col_index, cell, paragraphs, cell_hint)
    key = escape(payload["key"])
    style_attr = ""
    if payload.get("fieldType") == "textarea" and payload.get("minHeightPx"):
        style_attr = f' style="min-height:{payload["minHeightPx"]}px"'

    if payload["fieldType"] == "textarea":
        control = f'<textarea class="prototype-textarea" data-key="{key}"{style_attr}></textarea>'
    else:
        control = f'<input class="prototype-input" type="text" data-key="{key}" />'
    return f'<div class="control-wrap append">{control}</div>'


def _build_document_paragraph_block(paragraph, ai_hints: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    tokens, _ = _build_inline_fill_tokens(
        paragraph.text,
        f"doc::paragraph::{paragraph.index}",
        ai_hints.get("paragraphs", {}).get(f"doc::paragraph::{paragraph.index}"),
    )
    return {
        "kind": "paragraph",
        "text": paragraph.text,
        "align": map_align(getattr(paragraph, "align", None)),
        "isBold": bool(getattr(paragraph, "is_bold", False)),
        "style": {
            key: value for key, value in {
                "fontSizePx": getattr(paragraph, "font_size_px", None),
                "fontFamily": getattr(paragraph, "font_family", None),
                "fontWeight": "bold" if getattr(paragraph, "is_bold", False) else None,
            }.items() if value is not None
        },
        "tokens": tokens,
    }


def _build_document_table_block(
    table,
    sub_form: dict[str, Any] | None,
    binding_map: dict[tuple[int, int], CellBinding],
    ai_hints: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    inline_binding_state = _build_inline_binding_state(sub_form, binding_map)
    rows: list[list[dict[str, Any]]] = []
    for ri, row in enumerate(table.rows):
        visible_cells = [cell for cell in row if not cell.is_merged_continuation]
        if not visible_cells:
            continue
        rows.append([
            _build_document_cell_block(table, ri, ci, cell, binding_map.get((ri, ci)), ai_hints, inline_binding_state)
            for ci, cell in enumerate(visible_cells)
        ])

    return {
        "kind": "table",
        "tableIndex": table.index,
        "subFormId": sub_form.get("id") if sub_form else None,
        "rows": rows,
    }


def _build_document_cell_block(
    table,
    row_index: int,
    col_index: int,
    cell,
    binding: CellBinding | None,
    ai_hints: dict[str, dict[str, dict[str, Any]]],
    inline_binding_state: InlineFieldBindingState | None = None,
) -> dict[str, Any]:
    paragraphs = cell.paragraphs or ([cell.text] if cell.text else [])
    rendered_paragraphs: list[dict[str, Any]] = []
    inline_fill_count = 0
    paragraph_hints = ai_hints.get("paragraphs", {})
    for pi, paragraph in enumerate(paragraphs):
        if paragraph.strip():
            paragraph_binding_state = None
            if inline_binding_state:
                paragraph_binding_state = InlineFieldBindingState(
                    inline_binding_state.sub_form_id,
                    inline_binding_state.available_fields,
                )
            tokens, count = _build_inline_fill_tokens(
                paragraph,
                f"auto::{table.index}::{row_index}::{col_index}::paragraph::{pi}",
                paragraph_hints.get(f"table::{table.index}::cell::{row_index}::{col_index}::paragraph::{pi}"),
                paragraph_binding_state,
            )
            inline_fill_count += count
            rendered_paragraphs.append({
                "kind": "text",
                "tokens": tokens,
            })
        else:
            rendered_paragraphs.append({"kind": "blank"})

    control = _build_document_control(binding) if binding else None
    cell_hint = ai_hints.get("cells", {}).get(f"table::{table.index}::cell::{row_index}::{col_index}")
    if not control and _should_render_auto_control(table, cell, paragraphs, inline_fill_count, cell_hint):
        control = _build_auto_control_payload(table, row_index, col_index, cell, paragraphs, cell_hint)

    return {
        "colspan": cell.colspan,
        "rowspan": cell.rowspan,
        "style": _build_cell_style_payload(cell),
        "isEmphasis": bool(cell.is_bold or cell.shading),
        "isEmpty": not cell.text.strip(),
        "paragraphs": rendered_paragraphs,
        "control": control,
    }


def _build_document_control(binding: CellBinding) -> dict[str, Any]:
    field = binding.field
    return {
        "kind": "schema",
        "subFormId": binding.sub_form_id,
        "fieldId": field.get("id"),
        "fieldType": field.get("type", "text"),
        "options": field.get("options") or [],
        "rowIndex": binding.row_index,
        "label": field.get("label", field.get("id", "field")),
    }


def _build_auto_control_payload(
    table,
    row_index: int,
    col_index: int,
    cell,
    paragraphs: list[str],
    cell_hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = f"auto::{table.index}::{row_index}::{col_index}::freeform"
    hinted_field_type = cell_hint.get("fieldType") if cell_hint else None
    is_multiline = hinted_field_type == "textarea" or (
        hinted_field_type != "text"
        and (
            cell.colspan > 1
            or cell.rowspan > 1
            or (cell.width_twips is not None and twips_to_px(cell.width_twips) >= 220)
            or any(not paragraph.strip() for paragraph in paragraphs)
        )
    )
    min_height_px = _estimate_multiline_height_px(cell, paragraphs) if is_multiline else None
    if cell_hint and cell_hint.get("minHeightPx"):
        min_height_px = max(min_height_px or 0, int(cell_hint["minHeightPx"]))
    return {
        "kind": "auto",
        "key": key,
        "fieldType": "textarea" if is_multiline else "text",
        "minHeightPx": min_height_px,
    }


def _build_cell_style_payload(cell) -> dict[str, Any]:
    style = {
        "widthPx": twips_to_px(cell.width_twips),
        "textAlign": map_align(cell.align),
        "verticalAlign": map_valign(cell.v_align),
        "backgroundColor": f"#{cell.shading}" if cell.shading else None,
        "borderTop": getattr(cell, "border_top", None),
        "borderRight": getattr(cell, "border_right", None),
        "borderBottom": getattr(cell, "border_bottom", None),
        "borderLeft": getattr(cell, "border_left", None),
        "fontWeight": "bold" if cell.is_bold else None,
        "fontSizePx": getattr(cell, "font_size_px", None),
        "fontFamily": getattr(cell, "font_family", None),
    }
    return {key: value for key, value in style.items() if value is not None}


def _estimate_multiline_height_px(cell, paragraphs: list[str]) -> int:
    blank_lines = sum(1 for paragraph in paragraphs if not paragraph.strip())
    visible_lines = sum(1 for paragraph in paragraphs if paragraph.strip())
    estimated = 96 + blank_lines * 28 + max(0, visible_lines - 1) * 10
    if cell.colspan >= 3:
        estimated += 28
    if cell.rowspan > 1:
        estimated += (cell.rowspan - 1) * 32
    return min(max(estimated, 132), 420)


def _build_inline_fill_tokens(
    text: str,
    key_prefix: str,
    paragraph_hint: dict[str, Any] | None = None,
    inline_binding_state: InlineFieldBindingState | None = None,
) -> tuple[list[dict[str, Any]], int]:
    if not text:
        return [], 0

    if paragraph_hint:
        hint_tokens = _build_tokens_from_ai_hint(paragraph_hint, text, key_prefix, inline_binding_state)
        if hint_tokens is not None:
            return hint_tokens, _count_interactive_tokens(hint_tokens)

    tokens: list[dict[str, Any]] = []
    count = 0
    last = 0
    for match in INLINE_GAP_RE.finditer(text):
        start, end = match.span()
        if _gap_belongs_to_choice_group(text, start, end):
            continue
        prefix_segment = text[last:start]
        if start > last:
            count = _append_text_with_implicit_fills(
                tokens,
                prefix_segment,
                key_prefix,
                count,
                allow_terminal_fill=False,
                inline_binding_state=inline_binding_state,
            )
        width_em = _estimate_inline_gap_width(match.group())
        token = {
            "kind": "inline-input",
            "key": f"{key_prefix}::gap::{count}",
            "widthEm": width_em,
        }
        matched_field = _consume_inline_field_for_label(
            _extract_trailing_label_text(prefix_segment),
            inline_binding_state,
        )
        if matched_field:
            token["fieldId"] = matched_field["id"]
            token["subFormId"] = inline_binding_state.sub_form_id if inline_binding_state else None
        tokens.append(token)
        count += 1
        last = end

    if last < len(text):
        count = _append_text_with_implicit_fills(tokens, text[last:], key_prefix, count, inline_binding_state=inline_binding_state)

    return tokens, count


def _build_tokens_from_ai_hint(
    paragraph_hint: dict[str, Any],
    original_text: str,
    key_prefix: str,
    inline_binding_state: InlineFieldBindingState | None = None,
) -> list[dict[str, Any]] | None:
    classification = paragraph_hint.get("classification")
    if classification == "static":
        return [{"kind": "text", "text": original_text}]

    if classification != "inline-choice":
        return None

    options = [option.strip() for option in paragraph_hint.get("options", []) if option and option.strip()]
    if len(options) < 2:
        return None

    tokens: list[dict[str, Any]] = []
    prefix_text = paragraph_hint.get("prefixText") or ""
    suffix_text = paragraph_hint.get("suffixText") or ""
    if prefix_text:
        tokens.append({"kind": "text", "text": prefix_text})
    choice_token = {
        "kind": "inline-choice",
        "key": f"{key_prefix}::choice::0",
        "choiceType": paragraph_hint.get("choiceType", "radio"),
        "options": options,
    }
    matched_field = _consume_inline_field_for_label(prefix_text, inline_binding_state)
    if matched_field:
        choice_token["fieldId"] = matched_field["id"]
        choice_token["subFormId"] = inline_binding_state.sub_form_id if inline_binding_state else None
    tokens.append(choice_token)
    if suffix_text:
        tokens.append({"kind": "text", "text": suffix_text})
    return tokens


def _count_interactive_tokens(tokens: list[dict[str, Any]]) -> int:
    return sum(1 for token in tokens if token["kind"] in {"inline-input", "inline-choice"})


def _append_text_with_implicit_fills(
    tokens: list[dict[str, Any]],
    text: str,
    key_prefix: str,
    start_index: int,
    allow_terminal_fill: bool = True,
    inline_binding_state: InlineFieldBindingState | None = None,
) -> int:
    if not text:
        return start_index

    choice_groups = _find_inline_choice_groups(text)
    if choice_groups:
        cursor = 0
        index = start_index
        for start, end, choice_type, options in choice_groups:
            prefix_segment = text[cursor:start]
            if start > cursor:
                index = _append_segment_with_implicit_fills(
                    tokens,
                    prefix_segment,
                    key_prefix,
                    index,
                    allow_terminal_fill=False,
                    inline_binding_state=inline_binding_state,
                )
            token = {
                "kind": "inline-choice",
                "key": f"{key_prefix}::choice::{index}",
                "choiceType": choice_type,
                "options": options,
            }
            matched_field = _consume_inline_field_for_label(
                _extract_trailing_label_text(prefix_segment),
                inline_binding_state,
            )
            if matched_field:
                token["fieldId"] = matched_field["id"]
                token["subFormId"] = inline_binding_state.sub_form_id if inline_binding_state else None
            tokens.append(token)
            index += 1
            cursor = end
        if cursor < len(text):
            index = _append_segment_with_implicit_fills(
                tokens,
                text[cursor:],
                key_prefix,
                index,
                allow_terminal_fill=allow_terminal_fill,
                inline_binding_state=inline_binding_state,
            )
        return index

    return _append_segment_with_implicit_fills(
        tokens,
        text,
        key_prefix,
        start_index,
        allow_terminal_fill,
        inline_binding_state=inline_binding_state,
    )


def _append_segment_with_implicit_fills(
    tokens: list[dict[str, Any]],
    text: str,
    key_prefix: str,
    start_index: int,
    allow_terminal_fill: bool = True,
    inline_binding_state: InlineFieldBindingState | None = None,
) -> int:
    if not text:
        return start_index

    matches = list(IMPLICIT_FILL_LABEL_RE.finditer(text))
    if not matches:
        tokens.append({"kind": "text", "text": text})
        return start_index

    cursor = 0
    index = start_index
    for match_index, match in enumerate(matches):
        next_start = matches[match_index + 1].start() if match_index + 1 < len(matches) else len(text)
        label = match.group()[:-1]
        between_text = text[match.end():next_start]
        has_next_label = match_index + 1 < len(matches)

        if not _should_insert_implicit_fill(label, between_text, has_next_label, allow_terminal_fill):
            continue

        if match.end() > cursor:
            tokens.append({"kind": "text", "text": text[cursor:match.end()]})
        token = {
            "kind": "inline-input",
            "key": f"{key_prefix}::gap::{index}",
            "widthEm": _trailing_fill_width(label),
        }
        matched_field = _consume_inline_field_for_label(label, inline_binding_state)
        if matched_field:
            token["fieldId"] = matched_field["id"]
            token["subFormId"] = inline_binding_state.sub_form_id if inline_binding_state else None
        tokens.append(token)
        index += 1
        cursor = _advance_after_insert(text, match.end(), next_start)

    if cursor < len(text):
        tokens.append({"kind": "text", "text": text[cursor:]})

    return index


def _find_inline_choice_groups(text: str) -> list[tuple[int, int, str, list[str]]]:
    for pattern, choice_type in (
        (CIRCLE_OPTION_RE, "radio"),
        (BOX_OPTION_RE, "radio"),
    ):
        matches = list(pattern.finditer(text))
        if len(matches) < 2:
            continue

        groups: list[tuple[int, int, str, list[str]]] = []
        current = [matches[0]]
        for match in matches[1:]:
            gap = text[current[-1].end():match.start()]
            if _is_choice_group_separator(gap):
                current.append(match)
                continue
            if len(current) >= 2:
                groups.append(_build_choice_group(current, choice_type))
            current = [match]

        if len(current) >= 2:
            groups.append(_build_choice_group(current, choice_type))
        if groups:
            return groups

    return []


def _build_choice_group(matches: list[re.Match[str]], choice_type: str) -> tuple[int, int, str, list[str]]:
    start = matches[0].start()
    end = matches[-1].end()
    options = [_clean_choice_option(match.group(1)) for match in matches if _clean_choice_option(match.group(1))]
    return start, end, choice_type, options


def _clean_choice_option(value: str) -> str:
    return value.strip().rstrip(")）")


def _estimate_inline_gap_width(text: str) -> float:
    stripped = text.strip()
    if stripped and all(char in "_＿﹍﹎‗—-" for char in stripped):
        return max(4.5, round(len(text) * 0.55, 1))
    return max(3.5, round(len(text) * 0.45, 1))


def _is_choice_group_separator(text: str) -> bool:
    if text.strip() == "":
        return True
    stripped = text.strip()
    return bool(stripped) and all(char in "_＿﹍﹎‗—- " for char in stripped)


def _gap_belongs_to_choice_group(text: str, start: int, end: int) -> bool:
    left = text[max(0, start - 48):start].rstrip()
    right = text[end:min(len(text), end + 48)]
    return bool(CHOICE_OPTION_LEFT_CONTEXT_RE.search(left) and CHOICE_OPTION_RIGHT_CONTEXT_RE.search(right))


def _should_insert_implicit_fill(label: str, between_text: str, has_next_label: bool, allow_terminal_fill: bool) -> bool:
    if any(keyword in label for keyword in TRAILING_FILL_EXCLUDE_KEYWORDS):
        return False

    normalized = between_text.strip()
    if not has_next_label and not allow_terminal_fill:
        return False

    if not normalized:
        return True

    if normalized.startswith(("(", "（")):
        return True

    if normalized[0] in {"年", "月", "日", "止", "至"}:
        return True

    if all(char in "年月日止至.-/—~～ " for char in normalized):
        return True

    if has_next_label and not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", normalized):
        return True

    if has_next_label and len(label) <= 8 and any(pattern.search(label) for pattern, _ in TRAILING_FILL_WIDTH_RULES):
        return normalized == ""

    return False


def _advance_after_insert(text: str, start: int, next_start: int) -> int:
    cursor = start
    while cursor < next_start and text[cursor].isspace():
        cursor += 1
    return cursor


def _trailing_fill_width(label: str) -> float:
    for pattern, width in TRAILING_FILL_WIDTH_RULES:
        if pattern.search(label):
            return width
    return 6.5


def _render_tokens_html(tokens: list[dict[str, Any]]) -> str:
    html_parts: list[str] = []
    for token in tokens:
        if token["kind"] == "text":
            html_parts.append(escape(token["text"]))
            continue
        if token["kind"] == "inline-choice":
            options_html = []
            for option in token["options"]:
                safe_option = escape(option)
                data_field = f' data-field-id="{escape(token["fieldId"])}"' if token.get("fieldId") else ""
                data_sub_form = f' data-sub-form-id="{escape(token["subFormId"])}"' if token.get("subFormId") else ""
                if token.get("choiceType") == "checkbox_group":
                    options_html.append(
                        f'<label class="choice-item inline-choice-item"><input type="checkbox" '
                        f'data-key="{escape(token["key"])}" data-group="checkbox_group" '
                        f'value="{safe_option}"{data_field}{data_sub_form} />{safe_option}</label>'
                    )
                else:
                    options_html.append(
                        f'<label class="choice-item inline-choice-item"><input type="radio" '
                        f'data-key="{escape(token["key"])}" data-toggleable="true" '
                        f'value="{safe_option}"{data_field}{data_sub_form} />{safe_option}</label>'
                    )
            html_parts.append(f'<span class="choice-group inline-choice-group">{"".join(options_html)}</span>')
            continue
        if token["kind"] == "inline-input":
            data_field = f' data-field-id="{escape(token["fieldId"])}"' if token.get("fieldId") else ""
            data_sub_form = f' data-sub-form-id="{escape(token["subFormId"])}"' if token.get("subFormId") else ""
            html_parts.append(
                f'<input class="inline-fill" type="text" data-key="{escape(token["key"])}" '
                f'style="width:{token["widthEm"]}em"{data_field}{data_sub_form} />'
            )
    return "".join(html_parts)


def _build_inline_binding_state(
    sub_form: dict[str, Any] | None,
    binding_map: dict[tuple[int, int], CellBinding],
) -> InlineFieldBindingState | None:
    if not sub_form:
        return None
    used_field_ids = {
        binding.field.get("id")
        for binding in binding_map.values()
        if binding.field.get("id")
    }
    available_fields = [
        field for field in sub_form.get("fields", [])
        if field.get("type") != "static" and field.get("id") not in used_field_ids
    ]
    if not available_fields:
        return None
    return InlineFieldBindingState(sub_form.get("id"), available_fields)


def _consume_inline_field_for_label(
    label_text: str,
    inline_binding_state: InlineFieldBindingState | None,
) -> dict[str, Any] | None:
    if not inline_binding_state or not inline_binding_state.available_fields:
        return None

    normalized_label = _normalize_match_text(label_text)
    if not normalized_label:
        return None

    contextual_match = _consume_contextual_date_field(normalized_label, inline_binding_state)
    if contextual_match:
        inline_binding_state.last_matched_field = contextual_match
        return contextual_match

    best_index = -1
    best_score = 0
    for index, field in enumerate(inline_binding_state.available_fields):
        score = _score_inline_field_match(normalized_label, field)
        if score > best_score:
            best_score = score
            best_index = index

    if best_index < 0 or best_score < 35:
        return None
    matched_field = inline_binding_state.available_fields.pop(best_index)
    inline_binding_state.last_matched_field = matched_field
    return matched_field


def _consume_contextual_date_field(
    normalized_label: str,
    inline_binding_state: InlineFieldBindingState,
) -> dict[str, Any] | None:
    if normalized_label not in {"日期", "时间", "年月日"}:
        return None

    previous = inline_binding_state.last_matched_field
    if not previous or previous.get("type") == "date":
        return None

    previous_label = _normalize_match_text(previous.get("label") or previous.get("id") or "")
    if not previous_label:
        return None

    for index, field in enumerate(inline_binding_state.available_fields):
        if field.get("type") != "date":
            continue
        field_label = _normalize_match_text(field.get("label") or field.get("id") or "")
        if previous_label and previous_label in field_label:
            return inline_binding_state.available_fields.pop(index)
    return None


def _normalize_match_text(text: str) -> str:
    compact = re.sub(r"[：:（）()\s]+", "", text or "")
    return compact.strip().lower()


def _extract_trailing_label_text(text: str) -> str:
    matches = list(IMPLICIT_FILL_LABEL_RE.finditer(text or ""))
    if not matches:
        return ""
    return matches[-1].group()[:-1]


def _score_inline_field_match(normalized_label: str, field: dict[str, Any]) -> int:
    field_label = _normalize_match_text(field.get("label") or field.get("id") or "")
    if not field_label:
        return 0

    score = 0
    if normalized_label == field_label:
        score += 100
    if normalized_label in field_label:
        score += 60
        if field_label.endswith(normalized_label):
            score += 15
    elif field_label in normalized_label:
        score += 5 if len(field_label) <= 1 and len(normalized_label) > 1 else 40

    field_type = field.get("type", "text")
    if re.search(r"日期|时间|年月日", normalized_label):
        score += 20 if field_type == "date" else 0
    if re.search(r"问题|意见|结果|说明|内容|情况|结论", normalized_label):
        score += 20 if field_type == "textarea" else 0
    if re.search(r"人员|代表|负责人|单位|名称|编号|代码|型号|证号|证书", normalized_label):
        score += 10 if field_type in {"text", "number"} else 0
    return score


def _build_binding_maps(tables, sub_forms: list[dict[str, Any]]) -> dict[int, dict[tuple[int, int], CellBinding]]:
    result: dict[int, dict[tuple[int, int], CellBinding]] = {}
    for table in tables:
        sub_form = sub_forms[table.index] if table.index < len(sub_forms) else None
        if not sub_form:
            continue

        explicit = _build_explicit_binding_map(table, sub_form)
        result[table.index] = explicit or _build_fallback_binding_map(table, sub_form)
    return result


def _build_explicit_binding_map(table, sub_form: dict[str, Any]) -> dict[tuple[int, int], CellBinding]:
    layout = sub_form.get("layout", {})
    layout_type = layout.get("type")
    fields = {field["id"]: field for field in sub_form.get("fields", []) if field.get("type") != "static"}

    if layout_type == "key-value":
        binding_map: dict[tuple[int, int], CellBinding] = {}
        for ri, row in enumerate(layout.get("rows", [])):
            for ci, cell in enumerate(row):
                if cell.get("kind") != "input":
                    continue
                field_id = cell.get("fieldId")
                field = fields.get(field_id)
                if field:
                    binding_map[(ri, ci)] = CellBinding(
                        key=f"{sub_form['id']}::{field_id}",
                        field=field,
                        sub_form_id=sub_form["id"],
                    )
        return binding_map

    if layout_type == "data-grid":
        binding_map = {}
        header_count = len(layout.get("headers", []))
        data_columns = layout.get("dataColumns", [])
        visible_rows = [
            [cell for cell in row if not cell.is_merged_continuation]
            for row in table.rows
            if any(not cell.is_merged_continuation for cell in row)
        ]
        for ri in range(header_count, len(visible_rows)):
            row_cells = visible_rows[ri]
            if not row_cells:
                continue
            row_index = ri - header_count
            for ci, field_id in enumerate(data_columns[:len(row_cells)]):
                field = fields.get(field_id)
                if not field:
                    continue
                binding_map[(ri, ci)] = CellBinding(
                    key=f"{sub_form['id']}::_rows::{row_index}::{field_id}",
                    field=field,
                    sub_form_id=sub_form["id"],
                    row_index=row_index,
                )
        return binding_map

    return {}


def _build_fallback_binding_map(table, sub_form: dict[str, Any]) -> dict[tuple[int, int], CellBinding]:
    binding_map: dict[tuple[int, int], CellBinding] = {}
    field_queue = _flatten_fallback_fields(sub_form)
    if not field_queue:
        return binding_map

    next_index = 0
    for ri, row in enumerate(table.rows):
        visible_cells = [cell for cell in row if not cell.is_merged_continuation]
        for ci, cell in enumerate(visible_cells):
            if next_index >= len(field_queue):
                return binding_map
            field = field_queue[next_index]
            text = cell.text.strip()
            if _is_input_candidate(text, field):
                key = _make_fallback_key(sub_form, field, ri, ci)
                mode = "append" if text else "replace"
                binding_map[(ri, ci)] = CellBinding(
                    key=key,
                    field=field,
                    mode=mode,
                    hint_text=text or None,
                    sub_form_id=sub_form["id"],
                    row_index=ri if sub_form.get("recordType") == "multi" else None,
                )
                next_index += 1
    return binding_map


def _flatten_fallback_fields(sub_form: dict[str, Any]) -> list[dict[str, Any]]:
    return [field for field in sub_form.get("fields", []) if field.get("type") != "static"]


def _make_fallback_key(sub_form: dict[str, Any], field: dict[str, Any], row_index: int, col_index: int) -> str:
    if sub_form.get("recordType") == "multi":
        return f"{sub_form['id']}::_rows::{row_index}::{field['id']}"
    return f"{sub_form['id']}::{field['id']}::{row_index}_{col_index}"


def _is_input_candidate(text: str, field: dict[str, Any]) -> bool:
    field_type = field.get("type", "text")
    if not text:
        return True
    if field_type == "radio" and "□" in text:
        return True
    if field_type == "select" and _looks_like_option_text(text):
        return True
    return False


def _looks_like_option_text(text: str) -> bool:
    return bool(re.search(r"[A-ZＡ-Ｚ][\.\、．]", text))
