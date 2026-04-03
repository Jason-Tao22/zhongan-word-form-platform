from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from lxml import html

from legacy_field_codes import strip_legacy_field_codes
from word_parser import ParsedCell, ParsedParagraph, ParsedTable


def can_extract_legacy_doc_html() -> bool:
    return shutil.which("textutil") is not None


def extract_legacy_doc_html(filename: str, file_bytes: bytes) -> str:
    textutil = shutil.which("textutil")
    if not textutil:
        raise RuntimeError("当前环境未安装 textutil，无法提取旧版 .doc HTML")

    suffix = Path(filename).suffix or ".doc"
    stem = Path(filename).stem
    with tempfile.TemporaryDirectory(prefix="legacy-doc-html-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / f"{stem}{suffix}"
        output_path = tmp_path / f"{stem}.html"
        input_path.write_bytes(file_bytes)

        result = subprocess.run(
            [
                textutil,
                "-convert",
                "html",
                "-output",
                str(output_path),
                str(input_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not output_path.exists():
            stderr = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(stderr or "旧版 .doc HTML 提取失败")
        return _sanitize_legacy_html(output_path.read_text(encoding="utf-8", errors="ignore"))


def parse_legacy_doc_html_blocks(html_text: str) -> list[dict]:
    document = html.fromstring(_sanitize_legacy_html(html_text))
    body_nodes = document.xpath("//body")
    if not body_nodes:
        return []

    body = body_nodes[0]
    class_styles = _extract_class_styles(document)
    blocks: list[dict] = []
    table_index = 0
    paragraph_index = 0

    for child in body.iterchildren():
        tag = _local_name(child.tag)
        if tag == "table":
            blocks.append({"kind": "table", "table": _parse_html_table(child, table_index, class_styles)})
            table_index += 1
            continue
        if tag == "p":
            text = _get_inline_text(child)
            if text.strip():
                style = _resolve_style(child, class_styles)
                blocks.append({
                    "kind": "paragraph",
                    "paragraph": ParsedParagraph(
                        text=text.strip(),
                        index=paragraph_index,
                        align=_extract_align(child, style),
                        is_bold=_is_bold_node(child),
                        font_size_px=_css_px(style.get("font-size")),
                        font_family=_css_font_family(style.get("font-family")),
                        line_height=_css_line_height(style.get("line-height")),
                        margin_top_px=_css_px(style.get("margin-top")),
                        margin_bottom_px=_css_px(style.get("margin-bottom")),
                        margin_left_px=_css_px(style.get("margin-left")),
                        margin_right_px=_css_px(style.get("margin-right")),
                        text_indent_px=_css_px(style.get("text-indent")),
                    ),
                })
            paragraph_index += 1

    return blocks


def _sanitize_legacy_html(html_text: str) -> str:
    sanitized = html_text.replace("\x00", "")
    # Strip other non-printable control chars that can confuse lxml but keep tabs/newlines.
    sanitized = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", sanitized)
    return sanitized


def _parse_html_table(table_elem, index: int, class_styles: dict[str, dict[str, str]]) -> ParsedTable:
    table = ParsedTable(index=index)
    rowspan_tracker: dict[int, tuple[int, dict]] = {}

    rows = table_elem.xpath(".//tr")
    for row_index, row_elem in enumerate(rows):
        row_cells: list[ParsedCell] = []
        logical_col = 0
        html_cells = row_elem.xpath("./th|./td")

        for cell_elem in html_cells:
            while logical_col in rowspan_tracker and rowspan_tracker[logical_col][0] > 0:
                remaining, meta = rowspan_tracker[logical_col]
                row_cells.append(ParsedCell(
                    text=meta["text"],
                    row=row_index,
                    col=logical_col,
                    rowspan=1,
                    colspan=meta["colspan"],
                    is_merged_continuation=True,
                    width_twips=meta["width_twips"],
                    min_height_px=meta["min_height_px"],
                    padding_px=meta["padding_px"],
                    align=meta["align"],
                    v_align=meta["v_align"],
                    shading=meta["shading"],
                    border_top=meta["border_top"],
                    border_right=meta["border_right"],
                    border_bottom=meta["border_bottom"],
                    border_left=meta["border_left"],
                    is_bold=meta["is_bold"],
                    paragraphs=meta["paragraphs"],
                    paragraph_details=meta["paragraph_details"],
                ))
                rowspan_tracker[logical_col] = (remaining - 1, meta)
                if rowspan_tracker[logical_col][0] == 0:
                    del rowspan_tracker[logical_col]
                logical_col += meta["colspan"]

            colspan = _safe_int(cell_elem.get("colspan"), 1)
            rowspan = _safe_int(cell_elem.get("rowspan"), 1)
            paragraph_details = _extract_cell_paragraph_details(cell_elem, class_styles)
            paragraphs = [paragraph.text for paragraph in paragraph_details] if paragraph_details else _extract_cell_paragraphs(cell_elem)
            text = "".join(paragraph.strip() for paragraph in paragraphs if paragraph.strip())
            style = _resolve_style(cell_elem, class_styles)
            width_twips = _width_px_to_twips(style.get("min-width") or style.get("width"))
            min_height_px = _css_px(style.get("min-height") or style.get("height"))
            padding_px = _css_padding_px(style)
            align = _extract_align(cell_elem, style)
            v_align = cell_elem.get("valign")
            shading = _color_hex(style.get("background-color"))
            borders = _extract_border_styles(style)
            is_bold = _is_bold_node(cell_elem)

            if rowspan > 1:
                rowspan_tracker[logical_col] = (
                    rowspan - 1,
                    {
                        "text": text,
                        "colspan": colspan,
                        "width_twips": width_twips,
                        "min_height_px": min_height_px,
                        "padding_px": padding_px,
                        "align": align,
                        "v_align": v_align,
                        "shading": shading,
                        "border_top": borders["border_top"],
                        "border_right": borders["border_right"],
                        "border_bottom": borders["border_bottom"],
                        "border_left": borders["border_left"],
                        "is_bold": is_bold,
                        "paragraphs": paragraphs,
                        "paragraph_details": paragraph_details,
                    },
                )

            row_cells.append(ParsedCell(
                text=text,
                row=row_index,
                col=logical_col,
                rowspan=rowspan,
                colspan=colspan,
                width_twips=width_twips,
                min_height_px=min_height_px,
                padding_px=padding_px,
                align=align,
                v_align=v_align,
                shading=shading,
                border_top=borders["border_top"],
                border_right=borders["border_right"],
                border_bottom=borders["border_bottom"],
                border_left=borders["border_left"],
                is_bold=is_bold,
                paragraphs=paragraphs,
                paragraph_details=paragraph_details,
            ))
            logical_col += colspan

        while logical_col in rowspan_tracker and rowspan_tracker[logical_col][0] > 0:
            remaining, meta = rowspan_tracker[logical_col]
            row_cells.append(ParsedCell(
                text=meta["text"],
                row=row_index,
                col=logical_col,
                rowspan=1,
                colspan=meta["colspan"],
                is_merged_continuation=True,
                width_twips=meta["width_twips"],
                min_height_px=meta["min_height_px"],
                padding_px=meta["padding_px"],
                align=meta["align"],
                v_align=meta["v_align"],
                shading=meta["shading"],
                border_top=meta["border_top"],
                border_right=meta["border_right"],
                border_bottom=meta["border_bottom"],
                border_left=meta["border_left"],
                is_bold=meta["is_bold"],
                paragraphs=meta["paragraphs"],
                paragraph_details=meta["paragraph_details"],
            ))
            rowspan_tracker[logical_col] = (remaining - 1, meta)
            if rowspan_tracker[logical_col][0] == 0:
                del rowspan_tracker[logical_col]
            logical_col += meta["colspan"]

        table.rows.append(row_cells)

    return table


def _extract_cell_paragraphs(cell_elem) -> list[str]:
    paragraphs = [_get_inline_text(paragraph) for paragraph in cell_elem.xpath("./p")]
    if paragraphs:
        return paragraphs
    fallback = _get_inline_text(cell_elem)
    return [fallback] if fallback else []


def _extract_cell_paragraph_details(cell_elem, class_styles: dict[str, dict[str, str]]) -> list[ParsedParagraph]:
    paragraph_nodes = cell_elem.xpath("./p")
    if paragraph_nodes:
        details: list[ParsedParagraph] = []
        for index, paragraph in enumerate(paragraph_nodes):
            style = _resolve_style(paragraph, class_styles)
            details.append(ParsedParagraph(
                text=_get_inline_text(paragraph),
                index=index,
                align=_extract_align(paragraph, style),
                is_bold=_is_bold_node(paragraph),
                font_size_px=_css_px(style.get("font-size")),
                font_family=_css_font_family(style.get("font-family")),
                line_height=_css_line_height(style.get("line-height")),
                margin_top_px=_css_px(style.get("margin-top")),
                margin_bottom_px=_css_px(style.get("margin-bottom")),
                margin_left_px=_css_px(style.get("margin-left")),
                margin_right_px=_css_px(style.get("margin-right")),
                text_indent_px=_css_px(style.get("text-indent")),
            ))
        return details

    fallback = _get_inline_text(cell_elem)
    if not fallback:
        return []
    style = _resolve_style(cell_elem, class_styles)
    return [ParsedParagraph(
        text=fallback,
        index=0,
        align=_extract_align(cell_elem, style),
        is_bold=_is_bold_node(cell_elem),
        font_size_px=_css_px(style.get("font-size")),
        font_family=_css_font_family(style.get("font-family")),
        line_height=_css_line_height(style.get("line-height")),
        margin_top_px=_css_px(style.get("margin-top")),
        margin_bottom_px=_css_px(style.get("margin-bottom")),
        margin_left_px=_css_px(style.get("margin-left")),
        margin_right_px=_css_px(style.get("margin-right")),
        text_indent_px=_css_px(style.get("text-indent")),
    )]


def _get_inline_text(node) -> str:
    raw = "".join(node.itertext())
    raw = raw.replace("\r", "")
    raw = re.sub(r"\n+", "", raw)
    return strip_legacy_field_codes(raw)


def _extract_align(node, style_map: dict[str, str] | None = None) -> str | None:
    align = node.get("align")
    if align:
        return align
    style = node.get("style") or ""
    match = re.search(r"text-align:\s*([a-zA-Z]+)", style)
    if match:
        return match.group(1).lower()
    if style_map and style_map.get("text-align"):
        return style_map["text-align"].lower()
    return None


def _is_bold_node(node) -> bool:
    return bool(node.xpath(".//b|.//strong"))


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value else default
    except ValueError:
        return default


def _local_name(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _extract_class_styles(document) -> dict[str, dict[str, str]]:
    styles: dict[str, dict[str, str]] = {}
    css_text = "\n".join(style.text or "" for style in document.xpath("//style"))
    for class_name, body in re.findall(r"\.(\w+)\s*\{([^}]*)\}", css_text):
        declarations: dict[str, str] = {}
        for part in body.split(";"):
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            declarations[key.strip().lower()] = value.strip()
        if declarations:
            styles[class_name] = declarations
    return styles


def _resolve_style(node, class_styles: dict[str, dict[str, str]]) -> dict[str, str]:
    merged: dict[str, str] = {}
    class_attr = node.get("class") or ""
    for class_name in class_attr.split():
        merged.update(class_styles.get(class_name, {}))
    inline_style = node.get("style") or ""
    for part in inline_style.split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        merged[key.strip().lower()] = value.strip()
    return merged


def _width_px_to_twips(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)px", value)
    if not match:
        return None
    return round(float(match.group(1)) * 15)


def _color_hex(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"#([0-9a-fA-F]{6})", value)
    if match:
        return match.group(1).upper()
    return None


def _css_px(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)(px|pt)", value.lower())
    if not match:
        return None
    numeric = float(match.group(1))
    unit = match.group(2)
    return max(0, round(numeric if unit == "px" else numeric * 96 / 72))


def _css_line_height(value: str | None) -> float | None:
    if not value:
        return None
    stripped = value.strip().lower()
    if stripped == "normal":
        return None
    unitless = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)", stripped)
    if unitless:
        return round(float(unitless.group(1)), 2)
    px_value = _css_px(stripped)
    if px_value is None:
        return None
    return max(1.0, round(px_value / 16, 2))


def _css_font_family(value: str | None) -> str | None:
    if not value:
        return None
    first = value.split(",", 1)[0].strip().strip("'\"")
    return first or None


def _css_padding_px(style: dict[str, str]) -> int | None:
    values: list[int] = []
    shorthand = style.get("padding")
    if shorthand:
        parts = [part for part in shorthand.split() if part]
        for part in parts:
            px = _css_px(part)
            if px is not None:
                values.append(px)
    for key in ("padding-top", "padding-right", "padding-bottom", "padding-left"):
        px = _css_px(style.get(key))
        if px is not None:
            values.append(px)
    if not values:
        return None
    return max(0, round(sum(values) / len(values)))


def _normalize_border_css(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    if lowered.strip() in {"none", "0", "0px"}:
        return "none"

    style = next((item for item in ("double", "dashed", "dotted", "solid") if item in lowered), None) or "solid"

    width_px = 1
    width_match = re.search(r"([0-9]+(?:\.[0-9]+)?)(px|pt)", lowered)
    if width_match:
        numeric = float(width_match.group(1))
        unit = width_match.group(2)
        width_px = max(1, round(numeric if unit == "px" else numeric * 96 / 72))

    color = _color_hex(value)
    if color is None and "windowtext" in lowered:
        color = "000000"

    return f"{width_px}px {style} #{color or '000000'}"


def _extract_border_styles(style: dict[str, str]) -> dict[str, str | None]:
    all_border = _normalize_border_css(style.get("border"))
    return {
        "border_top": _normalize_border_css(style.get("border-top")) or all_border,
        "border_right": _normalize_border_css(style.get("border-right")) or all_border,
        "border_bottom": _normalize_border_css(style.get("border-bottom")) or all_border,
        "border_left": _normalize_border_css(style.get("border-left")) or all_border,
    }
