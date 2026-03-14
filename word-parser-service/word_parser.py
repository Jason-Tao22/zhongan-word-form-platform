"""
Word 文档解析模块
- 直接操作 word/document.xml 以正确获取 colspan / rowspan
- 输出结构化的表格数据，供 AI 分析
"""
from __future__ import annotations
import zipfile
import re
from dataclasses import dataclass, field
from lxml import etree

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W  = lambda tag: f"{{{NS}}}{tag}"


@dataclass
class ParsedCell:
    text: str
    row: int
    col: int          # 逻辑列（已展开合并）
    rowspan: int = 1
    colspan: int = 1
    is_merged_continuation: bool = False  # vMerge 续行，跳过
    width_twips: int | None = None
    align: str | None = None
    v_align: str | None = None
    shading: str | None = None
    is_bold: bool = False
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class ParsedParagraph:
    text: str
    index: int
    align: str | None = None
    is_bold: bool = False


@dataclass
class ParsedTable:
    index: int
    rows: list[list[ParsedCell]] = field(default_factory=list)

    @property
    def preview(self) -> list[list[str]]:
        """仅返回文本，供 AI prompt 使用"""
        return [[c.text for c in row] for row in self.rows]

    @property
    def col_count(self) -> int:
        if not self.rows:
            return 0
        return max(len(row) for row in self.rows)


def _get_text(elem) -> str:
    """提取元素下所有 w:t 文本"""
    parts = []
    for t in elem.iter(W("t")):
        parts.append(t.text or "")
    return "".join(parts).strip()


def _get_paragraph_text(p_elem, strip: bool = True) -> str:
    parts: list[str] = []
    for child in p_elem.iter():
        if child.tag == W("t"):
            parts.append(child.text or "")
        elif child.tag == W("tab"):
            parts.append("    ")
    text = "".join(parts)
    return text.strip() if strip else text


def _get_paragraph_texts(tc_elem) -> list[str]:
    paragraphs: list[str] = []
    for p in tc_elem.findall(W("p")):
        paragraphs.append(_get_paragraph_text(p, strip=False))
    if any(text.strip() for text in paragraphs):
        return paragraphs
    return []


def _get_grid_span(tc_elem) -> int:
    """获取横向合并数（colspan）"""
    tcPr = tc_elem.find(W("tcPr"))
    if tcPr is None:
        return 1
    gs = tcPr.find(W("gridSpan"))
    if gs is None:
        return 1
    return int(gs.get(W("val"), 1))


def _get_v_merge(tc_elem) -> str | None:
    """
    返回 vMerge 状态：
    - "restart" → 纵向合并的起始单元格
    - "continue" → 续行（应跳过）
    - None → 无纵向合并
    """
    tcPr = tc_elem.find(W("tcPr"))
    if tcPr is None:
        return None
    vm = tcPr.find(W("vMerge"))
    if vm is None:
        return None
    val = vm.get(W("val"), "continue")
    return val if val == "restart" else "continue"


def _get_cell_width(tc_elem) -> int | None:
    tcPr = tc_elem.find(W("tcPr"))
    if tcPr is None:
        return None
    tcw = tcPr.find(W("tcW"))
    if tcw is None:
        return None
    value = tcw.get(W("w")) or tcw.get("w")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _get_cell_v_align(tc_elem) -> str | None:
    tcPr = tc_elem.find(W("tcPr"))
    if tcPr is None:
        return None
    valign = tcPr.find(W("vAlign"))
    if valign is None:
        return None
    return valign.get(W("val")) or valign.get("val")


def _get_cell_shading(tc_elem) -> str | None:
    tcPr = tc_elem.find(W("tcPr"))
    if tcPr is None:
        return None
    shd = tcPr.find(W("shd"))
    if shd is None:
        return None
    fill = shd.get(W("fill")) or shd.get("fill")
    if fill in {None, "", "auto"}:
        return None
    return fill


def _get_cell_alignment(tc_elem) -> str | None:
    for p in tc_elem.findall(W("p")):
        p_pr = p.find(W("pPr"))
        if p_pr is None:
            continue
        jc = p_pr.find(W("jc"))
        if jc is None:
            continue
        value = jc.get(W("val")) or jc.get("val")
        if value:
            return value
    return None


def _get_paragraph_alignment(p_elem) -> str | None:
    p_pr = p_elem.find(W("pPr"))
    if p_pr is None:
        return None
    jc = p_pr.find(W("jc"))
    if jc is None:
        return None
    return jc.get(W("val")) or jc.get("val")


def _is_cell_bold(tc_elem) -> bool:
    has_text = False
    for run in tc_elem.findall(f".//{W('r')}"):
        texts = [t.text or "" for t in run.findall(W("t"))]
        if not any(texts):
            continue
        has_text = True
        r_pr = run.find(W("rPr"))
        if r_pr is None:
            return False
        bold = r_pr.find(W("b"))
        if bold is None:
            return False
        val = bold.get(W("val")) or bold.get("val") or "true"
        if val in {"0", "false"}:
            return False
    return has_text


def _is_paragraph_bold(p_elem) -> bool:
    has_text = False
    for run in p_elem.findall(f".//{W('r')}"):
        texts = [t.text or "" for t in run.findall(W("t"))]
        if not any(texts):
            continue
        has_text = True
        r_pr = run.find(W("rPr"))
        if r_pr is None:
            return False
        bold = r_pr.find(W("b"))
        if bold is None:
            return False
        val = bold.get(W("val")) or bold.get("val") or "true"
        if val in {"0", "false"}:
            return False
    return has_text


def _parse_table_element(tbl, idx: int) -> ParsedTable:
    parsed = ParsedTable(index=idx)
    raw_rows = tbl.findall(W("tr"))

    # 用于追踪跨行合并：grid_col -> (remaining_rows, colspan, text)
    vmerge_tracker: dict[int, tuple[int, dict]] = {}

    for ri, tr in enumerate(raw_rows):
        row_cells: list[ParsedCell] = []
        logical_col = 0

        for tc in tr.findall(W("tc")):
            # 跳过被 vMerge 占用的逻辑列
            while logical_col in vmerge_tracker and vmerge_tracker[logical_col][0] > 0:
                rem, cell_meta = vmerge_tracker[logical_col]
                row_cells.append(ParsedCell(
                    text=cell_meta["text"], row=ri, col=logical_col,
                    rowspan=1, colspan=cell_meta["colspan"], is_merged_continuation=True,
                    width_twips=cell_meta["width_twips"],
                    align=cell_meta["align"],
                    v_align=cell_meta["v_align"],
                    shading=cell_meta["shading"],
                    is_bold=cell_meta["is_bold"],
                    paragraphs=cell_meta["paragraphs"],
                ))
                vmerge_tracker[logical_col] = (rem - 1, cell_meta)
                if vmerge_tracker[logical_col][0] == 0:
                    del vmerge_tracker[logical_col]
                logical_col += cell_meta["colspan"]

            colspan = _get_grid_span(tc)
            vmerge = _get_v_merge(tc)
            text = _get_text(tc)
            paragraphs = _get_paragraph_texts(tc)
            width_twips = _get_cell_width(tc)
            align = _get_cell_alignment(tc)
            v_align = _get_cell_v_align(tc)
            shading = _get_cell_shading(tc)
            is_bold = _is_cell_bold(tc)

            if vmerge == "restart":
                # 找出这次合并跨多少行
                rowspan = 1
                for future_tr in raw_rows[ri + 1:]:
                    future_cells = future_tr.findall(W("tc"))
                    # 检查对应逻辑列是否是 continue
                    fc_col = 0
                    for ftc in future_cells:
                        if fc_col == logical_col:
                            if _get_v_merge(ftc) == "continue":
                                rowspan += 1
                            break
                        fc_col += _get_grid_span(ftc)
                    else:
                        break
                    if _get_v_merge(future_cells[0]) != "continue":
                        break

                vmerge_tracker[logical_col] = (
                    rowspan - 1,
                    {
                        "text": text,
                        "colspan": colspan,
                        "width_twips": width_twips,
                        "align": align,
                        "v_align": v_align,
                        "shading": shading,
                        "is_bold": is_bold,
                        "paragraphs": paragraphs,
                    },
                )
                row_cells.append(ParsedCell(
                    text=text, row=ri, col=logical_col,
                    rowspan=rowspan, colspan=colspan,
                    width_twips=width_twips,
                    align=align,
                    v_align=v_align,
                    shading=shading,
                    is_bold=is_bold,
                    paragraphs=paragraphs,
                ))
            elif vmerge == "continue":
                # 占位，已由 tracker 处理
                pass
            else:
                row_cells.append(ParsedCell(
                    text=text, row=ri, col=logical_col,
                    rowspan=1, colspan=colspan,
                    width_twips=width_twips,
                    align=align,
                    v_align=v_align,
                    shading=shading,
                    is_bold=is_bold,
                    paragraphs=paragraphs,
                ))

            logical_col += colspan

        parsed.rows.append(row_cells)

    return parsed


def parse_docx_blocks(file_bytes: bytes) -> list[dict]:
    with zipfile.ZipFile(file_bytes if hasattr(file_bytes, "read") else __import__("io").BytesIO(file_bytes)) as z:
        xml = z.read("word/document.xml")

    root = etree.fromstring(xml)
    body = root.find(W("body"))
    if body is None:
        return []

    blocks: list[dict] = []
    table_index = 0
    paragraph_index = 0
    for child in body:
        if child.tag == W("p"):
            text = _get_paragraph_text(child)
            if text:
                blocks.append({
                    "kind": "paragraph",
                    "paragraph": ParsedParagraph(
                        text=text,
                        index=paragraph_index,
                        align=_get_paragraph_alignment(child),
                        is_bold=_is_paragraph_bold(child),
                    ),
                })
            paragraph_index += 1
        elif child.tag == W("tbl"):
            blocks.append({
                "kind": "table",
                "table": _parse_table_element(child, table_index),
            })
            table_index += 1
    return blocks


def parse_docx(file_bytes: bytes) -> list[ParsedTable]:
    """解析 docx 字节，返回所有表格"""
    return [block["table"] for block in parse_docx_blocks(file_bytes) if block["kind"] == "table"]


def tables_to_prompt_text(tables: list[ParsedTable]) -> str:
    """将解析后的表格转成供 AI 阅读的纯文本"""
    lines = []
    for tbl in tables:
        lines.append(f"\n=== Table {tbl.index + 1} ({len(tbl.rows)} rows, ~{tbl.col_count} cols) ===")
        rendered_rows = [_render_prompt_row(row) for row in tbl.rows]
        row_index = 0
        while row_index < len(rendered_rows):
            current = rendered_rows[row_index]
            if _is_compressible_prompt_row(current):
                run_end = row_index + 1
                while run_end < len(rendered_rows) and rendered_rows[run_end] == current:
                    run_end += 1
                if run_end - row_index >= 3:
                    lines.append(f"  Rows {row_index + 1}-{run_end}: {' | '.join(current)}")
                    row_index = run_end
                    continue
            lines.append(f"  Row {row_index + 1}: {' | '.join(current)}")
            row_index += 1
    return "\n".join(lines)


def _render_prompt_row(row: list[ParsedCell]) -> list[str]:
    visible = [cell for cell in row if not cell.is_merged_continuation]
    cell_strs: list[str] = []
    for cell in visible:
        cs = f"[cs={cell.colspan}]" if cell.colspan > 1 else ""
        rs = f"[rs={cell.rowspan}]" if cell.rowspan > 1 else ""
        cell_strs.append(f"{cell.text!r}{cs}{rs}")
    return cell_strs


def _is_compressible_prompt_row(cell_strs: list[str]) -> bool:
    if not cell_strs:
        return False
    blank_like = 0
    for cell in cell_strs:
        raw_text = cell.split("[", 1)[0].strip("'")
        if raw_text.strip() in {"", "：", ":"}:
            blank_like += 1
    return blank_like / len(cell_strs) >= 0.8
