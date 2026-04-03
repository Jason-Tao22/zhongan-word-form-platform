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
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
A = lambda tag: f"{{{A_NS}}}{tag}"


@dataclass
class ParsedCell:
    text: str
    row: int
    col: int          # 逻辑列（已展开合并）
    rowspan: int = 1
    colspan: int = 1
    is_merged_continuation: bool = False  # vMerge 续行，跳过
    width_twips: int | None = None
    min_height_px: int | None = None
    padding_px: int | None = None
    align: str | None = None
    v_align: str | None = None
    shading: str | None = None
    border_top: str | None = None
    border_right: str | None = None
    border_bottom: str | None = None
    border_left: str | None = None
    is_bold: bool = False
    font_size_px: int | None = None
    font_family: str | None = None
    paragraphs: list[str] = field(default_factory=list)
    paragraph_details: list["ParsedParagraph"] = field(default_factory=list)


@dataclass
class ParsedParagraph:
    text: str
    index: int
    align: str | None = None
    is_bold: bool = False
    font_size_px: int | None = None
    font_family: str | None = None
    line_height: float | None = None
    margin_top_px: int | None = None
    margin_bottom_px: int | None = None
    margin_left_px: int | None = None
    margin_right_px: int | None = None
    text_indent_px: int | None = None


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


def _twips_to_px(value: int | None) -> int | None:
    if value is None:
        return None
    return round(value / 15)


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


def _get_row_min_height_px(tr_elem) -> int | None:
    tr_pr = tr_elem.find(W("trPr"))
    if tr_pr is None:
        return None
    tr_height = tr_pr.find(W("trHeight"))
    if tr_height is None:
        return None
    raw = tr_height.get(W("val")) or tr_height.get("val")
    if not raw:
        return None
    try:
        return _twips_to_px(int(raw))
    except ValueError:
        return None


def _extract_margin_values(margin_parent_elem) -> dict[str, int]:
    if margin_parent_elem is None:
        return {}
    values: dict[str, int] = {}
    for side in ("top", "right", "bottom", "left"):
        margin = margin_parent_elem.find(W(side))
        if margin is None:
            continue
        raw = margin.get(W("w")) or margin.get("w")
        if not raw:
            continue
        try:
            values[side] = int(raw)
        except ValueError:
            continue
    return values


def _get_table_cell_margin_defaults(tbl_elem) -> dict[str, int]:
    tbl_pr = tbl_elem.find(W("tblPr"))
    if tbl_pr is None:
        return {}
    return _extract_margin_values(tbl_pr.find(W("tblCellMar")))


def _get_cell_margin_values(tc_elem) -> dict[str, int]:
    tc_pr = tc_elem.find(W("tcPr"))
    if tc_pr is None:
        return {}
    return _extract_margin_values(tc_pr.find(W("tcMar")))


def _resolve_effective_cell_padding_px(tc_elem, table_margins: dict[str, int]) -> int | None:
    margins = {**table_margins, **_get_cell_margin_values(tc_elem)}
    if not margins:
        return None
    values_px = [_twips_to_px(value) for value in margins.values() if value is not None]
    values_px = [value for value in values_px if value is not None]
    if not values_px:
        return None
    return max(0, round(sum(values_px) / len(values_px)))


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


def _map_word_border_style(value: str | None) -> str | None:
    normalized = (value or "").lower()
    if normalized in {"", "nil", "none"}:
        return "none" if normalized else None
    if normalized in {"single", "thick", "thin"}:
        return "solid"
    if normalized in {"double", "triple"}:
        return "double"
    if normalized in {"dashed", "dashsmallgap", "dashdotstroked", "dashdot", "dashdotdot"}:
        return "dashed"
    if normalized in {"dotted", "dotdash", "dotdotdash"}:
        return "dotted"
    return "solid"


def _word_border_to_css(border_elem) -> str | None:
    if border_elem is None:
        return None
    border_style = _map_word_border_style(border_elem.get(W("val")) or border_elem.get("val"))
    if border_style is None:
        return None
    if border_style == "none":
        return "none"

    color = border_elem.get(W("color")) or border_elem.get("color") or "000000"
    if color.lower() == "auto":
        color = "000000"

    width_px = 1
    size_raw = border_elem.get(W("sz")) or border_elem.get("sz")
    if size_raw:
        try:
            width_px = max(1, round(int(size_raw) / 6))
        except ValueError:
            width_px = 1

    return f"{width_px}px {border_style} #{color.upper()}"


def _get_border_values(border_parent_elem) -> dict[str, str]:
    if border_parent_elem is None:
        return {}

    values: dict[str, str] = {}
    for side in ("top", "right", "bottom", "left", "insideH", "insideV"):
        border = border_parent_elem.find(W(side))
        css = _word_border_to_css(border)
        if css is not None:
            values[side] = css
    return values


def _get_table_border_defaults(tbl_elem) -> dict[str, str]:
    tbl_pr = tbl_elem.find(W("tblPr"))
    if tbl_pr is None:
        return {}
    return _get_border_values(tbl_pr.find(W("tblBorders")))


def _get_cell_border_values(tc_elem) -> dict[str, str]:
    tc_pr = tc_elem.find(W("tcPr"))
    if tc_pr is None:
        return {}
    return _get_border_values(tc_pr.find(W("tcBorders")))


def _resolve_effective_cell_borders(
    tc_elem,
    table_borders: dict[str, str],
    *,
    row_index: int,
    row_count: int,
    logical_col: int,
    col_count: int,
    colspan: int,
    rowspan: int,
) -> dict[str, str | None]:
    cell_borders = _get_cell_border_values(tc_elem)
    last_row = row_index + rowspan >= row_count
    last_col = logical_col + colspan >= col_count

    def pick(side: str, fallback_key: str) -> str | None:
        if side in cell_borders:
            return cell_borders[side]
        return table_borders.get(fallback_key)

    return {
        "border_top": pick("top", "top" if row_index == 0 else "insideH"),
        "border_right": pick("right", "right" if last_col else "insideV"),
        "border_bottom": pick("bottom", "bottom" if last_row else "insideH"),
        "border_left": pick("left", "left" if logical_col == 0 else "insideV"),
    }


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


def _get_paragraph_spacing(p_elem) -> tuple[int | None, int | None, float | None]:
    p_pr = p_elem.find(W("pPr"))
    if p_pr is None:
        return None, None, None
    spacing = p_pr.find(W("spacing"))
    if spacing is None:
        return None, None, None

    before_raw = spacing.get(W("before")) or spacing.get("before")
    after_raw = spacing.get(W("after")) or spacing.get("after")
    line_raw = spacing.get(W("line")) or spacing.get("line")
    line_rule = (spacing.get(W("lineRule")) or spacing.get("lineRule") or "auto").lower()

    def parse_twips(raw: str | None) -> int | None:
        if not raw:
            return None
        try:
            return _twips_to_px(int(raw))
        except ValueError:
            return None

    margin_top_px = parse_twips(before_raw)
    margin_bottom_px = parse_twips(after_raw)

    line_height = None
    if line_raw:
        try:
            line_value = int(line_raw)
            if line_rule == "auto":
                line_height = max(1.0, round(line_value / 240, 2))
            else:
                # Approximate exact/atLeast line spacing as a CSS unitless line-height.
                line_height = max(1.0, round((line_value / 20) / 12, 2))
        except ValueError:
            line_height = None

    return margin_top_px, margin_bottom_px, line_height


def _get_paragraph_indent(p_elem) -> tuple[int | None, int | None, int | None]:
    p_pr = p_elem.find(W("pPr"))
    if p_pr is None:
        return None, None, None
    ind = p_pr.find(W("ind"))
    if ind is None:
        return None, None, None

    def parse_twips(value: str | None) -> int | None:
        if not value:
            return None
        try:
            return _twips_to_px(int(value))
        except ValueError:
            return None

    left_px = parse_twips(ind.get(W("left")) or ind.get("left") or ind.get(W("start")) or ind.get("start"))
    right_px = parse_twips(ind.get(W("right")) or ind.get("right") or ind.get(W("end")) or ind.get("end"))
    first_line_px = parse_twips(ind.get(W("firstLine")) or ind.get("firstLine"))
    hanging_px = parse_twips(ind.get(W("hanging")) or ind.get("hanging"))
    text_indent_px = first_line_px if first_line_px is not None else (-hanging_px if hanging_px is not None else None)
    return left_px, right_px, text_indent_px


def _get_cell_paragraph_details(
    tc_elem,
    *,
    default_font_size_px: int | None = None,
    default_font_family: str | None = None,
    theme_root=None,
) -> list[ParsedParagraph]:
    paragraphs: list[ParsedParagraph] = []
    for index, p in enumerate(tc_elem.findall(W("p"))):
        text = _get_paragraph_text(p, strip=False)
        font_size_px, font_family = _get_text_run_display_style(
            p,
            default_font_size_px=default_font_size_px,
            default_font_family=default_font_family,
            theme_root=theme_root,
        )
        margin_top_px, margin_bottom_px, line_height = _get_paragraph_spacing(p)
        margin_left_px, margin_right_px, text_indent_px = _get_paragraph_indent(p)
        paragraphs.append(ParsedParagraph(
            text=text,
            index=index,
            align=_get_paragraph_alignment(p),
            is_bold=_is_paragraph_bold(p),
            font_size_px=font_size_px,
            font_family=font_family,
            line_height=line_height,
            margin_top_px=margin_top_px,
            margin_bottom_px=margin_bottom_px,
            margin_left_px=margin_left_px,
            margin_right_px=margin_right_px,
            text_indent_px=text_indent_px,
        ))
    return paragraphs


def _resolve_theme_typeface(theme_root, family: str) -> str | None:
    font_scheme = theme_root.find(f".//{A('fontScheme')}")
    if font_scheme is None:
        return None
    if family.startswith("minor"):
        scheme = font_scheme.find(A("minorFont"))
    elif family.startswith("major"):
        scheme = font_scheme.find(A("majorFont"))
    else:
        return None
    if scheme is None:
        return None

    if family.endswith("EastAsia"):
        east_asia = scheme.find(A("ea"))
        east_asia_face = east_asia.get("typeface") if east_asia is not None else ""
        if east_asia_face:
            return east_asia_face
        hans = next((font.get("typeface") for font in scheme.findall(A("font")) if font.get("script") == "Hans"), None)
        if hans:
            return hans
    elif family.endswith("Bidi"):
        cs = scheme.find(A("cs"))
        cs_face = cs.get("typeface") if cs is not None else ""
        if cs_face:
            return cs_face

    latin = scheme.find(A("latin"))
    latin_face = latin.get("typeface") if latin is not None else ""
    return latin_face or None


def _resolve_rpr_font_family(r_pr, theme_root=None) -> str | None:
    if r_pr is None:
        return None
    fonts = r_pr.find(W("rFonts"))
    if fonts is None:
        return None
    direct = (
        fonts.get(W("eastAsia"))
        or fonts.get("eastAsia")
        or fonts.get(W("ascii"))
        or fonts.get("ascii")
        or fonts.get(W("hAnsi"))
        or fonts.get("hAnsi")
        or fonts.get(W("cs"))
        or fonts.get("cs")
    )
    if direct:
        return direct
    theme_key = (
        fonts.get(W("eastAsiaTheme"))
        or fonts.get("eastAsiaTheme")
        or fonts.get(W("asciiTheme"))
        or fonts.get("asciiTheme")
        or fonts.get(W("hAnsiTheme"))
        or fonts.get("hAnsiTheme")
        or fonts.get(W("cstheme"))
        or fonts.get("cstheme")
    )
    if not theme_key or theme_root is None:
        return None
    return _resolve_theme_typeface(theme_root, theme_key)


def _resolve_rpr_font_size_px(r_pr) -> int | None:
    if r_pr is None:
        return None
    sz = r_pr.find(W("sz"))
    if sz is None:
        sz = r_pr.find(W("szCs"))
    if sz is None:
        return None
    raw = sz.get(W("val")) or sz.get("val")
    if not raw:
        return None
    try:
        half_points = int(raw)
    except ValueError:
        return None
    return max(10, round(half_points * 2 / 3))


def _get_default_run_style(styles_root, theme_root=None) -> tuple[int | None, str | None]:
    if styles_root is None:
        return None, None
    r_pr = styles_root.find(f".//{W('docDefaults')}/{W('rPrDefault')}/{W('rPr')}")
    if r_pr is None:
        return None, None
    return _resolve_rpr_font_size_px(r_pr), _resolve_rpr_font_family(r_pr, theme_root)


def _get_run_rpr(run):
    return run.find(W("rPr"))


def _get_run_font_family(run, theme_root=None) -> str | None:
    r_pr = _get_run_rpr(run)
    return _resolve_rpr_font_family(r_pr, theme_root)


def _get_run_font_size_px(run) -> int | None:
    r_pr = _get_run_rpr(run)
    return _resolve_rpr_font_size_px(r_pr)


def _weighted_choice(weights: dict[str | int, int]) -> str | int | None:
    if not weights:
        return None
    return max(weights.items(), key=lambda item: item[1])[0]


def _get_text_run_display_style(
    elem,
    default_font_size_px: int | None = None,
    default_font_family: str | None = None,
    theme_root=None,
) -> tuple[int | None, str | None]:
    family_weights: dict[str, int] = {}
    size_weights: dict[int, int] = {}

    for run in elem.findall(f".//{W('r')}"):
        text = "".join((t.text or "") for t in run.findall(W("t"))).strip()
        if not text:
            continue
        weight = max(1, len(text))
        font_family = _get_run_font_family(run, theme_root)
        font_size_px = _get_run_font_size_px(run)
        if font_family:
            family_weights[font_family] = family_weights.get(font_family, 0) + weight
        if font_size_px:
            size_weights[font_size_px] = size_weights.get(font_size_px, 0) + weight

    chosen_size = _weighted_choice(size_weights)
    chosen_family = _weighted_choice(family_weights)
    resolved_size = chosen_size if isinstance(chosen_size, int) else default_font_size_px
    resolved_family = chosen_family if isinstance(chosen_family, str) else default_font_family
    return resolved_size, resolved_family


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


def _parse_table_element(
    tbl,
    idx: int,
    *,
    default_font_size_px: int | None = None,
    default_font_family: str | None = None,
    theme_root=None,
) -> ParsedTable:
    parsed = ParsedTable(index=idx)
    raw_rows = tbl.findall(W("tr"))
    table_border_defaults = _get_table_border_defaults(tbl)
    table_cell_margin_defaults = _get_table_cell_margin_defaults(tbl)
    table_col_count = max((sum(_get_grid_span(tc) for tc in tr.findall(W("tc"))) for tr in raw_rows), default=0)

    # 用于追踪跨行合并：grid_col -> (remaining_rows, colspan, text)
    vmerge_tracker: dict[int, tuple[int, dict]] = {}

    for ri, tr in enumerate(raw_rows):
        row_cells: list[ParsedCell] = []
        logical_col = 0
        row_min_height_px = _get_row_min_height_px(tr)

        for tc in tr.findall(W("tc")):
            # 跳过被 vMerge 占用的逻辑列
            while logical_col in vmerge_tracker and vmerge_tracker[logical_col][0] > 0:
                rem, cell_meta = vmerge_tracker[logical_col]
                row_cells.append(ParsedCell(
                    text=cell_meta["text"], row=ri, col=logical_col,
                    rowspan=1, colspan=cell_meta["colspan"], is_merged_continuation=True,
                    width_twips=cell_meta["width_twips"],
                    min_height_px=cell_meta["min_height_px"],
                    padding_px=cell_meta["padding_px"],
                    align=cell_meta["align"],
                    v_align=cell_meta["v_align"],
                    shading=cell_meta["shading"],
                    border_top=cell_meta["border_top"],
                    border_right=cell_meta["border_right"],
                    border_bottom=cell_meta["border_bottom"],
                    border_left=cell_meta["border_left"],
                    is_bold=cell_meta["is_bold"],
                    font_size_px=cell_meta["font_size_px"],
                    font_family=cell_meta["font_family"],
                    paragraphs=cell_meta["paragraphs"],
                    paragraph_details=cell_meta["paragraph_details"],
                ))
                vmerge_tracker[logical_col] = (rem - 1, cell_meta)
                if vmerge_tracker[logical_col][0] == 0:
                    del vmerge_tracker[logical_col]
                logical_col += cell_meta["colspan"]

            colspan = _get_grid_span(tc)
            vmerge = _get_v_merge(tc)
            text = _get_text(tc)
            paragraph_details = _get_cell_paragraph_details(
                tc,
                default_font_size_px=default_font_size_px,
                default_font_family=default_font_family,
                theme_root=theme_root,
            )
            paragraphs = [paragraph.text for paragraph in paragraph_details] if paragraph_details else _get_paragraph_texts(tc)
            width_twips = _get_cell_width(tc)
            padding_px = _resolve_effective_cell_padding_px(tc, table_cell_margin_defaults)
            align = _get_cell_alignment(tc)
            v_align = _get_cell_v_align(tc)
            shading = _get_cell_shading(tc)
            is_bold = _is_cell_bold(tc)
            font_size_px, font_family = _get_text_run_display_style(
                tc,
                default_font_size_px=default_font_size_px,
                default_font_family=default_font_family,
                theme_root=theme_root,
            )

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

                borders = _resolve_effective_cell_borders(
                    tc,
                    table_border_defaults,
                    row_index=ri,
                    row_count=len(raw_rows),
                    logical_col=logical_col,
                    col_count=table_col_count,
                    colspan=colspan,
                    rowspan=rowspan,
                )

                vmerge_tracker[logical_col] = (
                    rowspan - 1,
                    {
                        "text": text,
                        "colspan": colspan,
                        "width_twips": width_twips,
                        "min_height_px": row_min_height_px,
                        "padding_px": padding_px,
                        "align": align,
                        "v_align": v_align,
                        "shading": shading,
                        "border_top": borders["border_top"],
                        "border_right": borders["border_right"],
                        "border_bottom": borders["border_bottom"],
                        "border_left": borders["border_left"],
                        "is_bold": is_bold,
                        "font_size_px": font_size_px,
                        "font_family": font_family,
                        "paragraphs": paragraphs,
                        "paragraph_details": paragraph_details,
                    },
                )
                row_cells.append(ParsedCell(
                    text=text, row=ri, col=logical_col,
                    rowspan=rowspan, colspan=colspan,
                    width_twips=width_twips,
                    min_height_px=row_min_height_px,
                    padding_px=padding_px,
                    align=align,
                    v_align=v_align,
                    shading=shading,
                    border_top=borders["border_top"],
                    border_right=borders["border_right"],
                    border_bottom=borders["border_bottom"],
                    border_left=borders["border_left"],
                    is_bold=is_bold,
                    font_size_px=font_size_px,
                    font_family=font_family,
                    paragraphs=paragraphs,
                    paragraph_details=paragraph_details,
                ))
            elif vmerge == "continue":
                # 占位，已由 tracker 处理
                pass
            else:
                borders = _resolve_effective_cell_borders(
                    tc,
                    table_border_defaults,
                    row_index=ri,
                    row_count=len(raw_rows),
                    logical_col=logical_col,
                    col_count=table_col_count,
                    colspan=colspan,
                    rowspan=1,
                )
                row_cells.append(ParsedCell(
                    text=text, row=ri, col=logical_col,
                    rowspan=1, colspan=colspan,
                    width_twips=width_twips,
                    min_height_px=row_min_height_px,
                    padding_px=padding_px,
                    align=align,
                    v_align=v_align,
                    shading=shading,
                    border_top=borders["border_top"],
                    border_right=borders["border_right"],
                    border_bottom=borders["border_bottom"],
                    border_left=borders["border_left"],
                    is_bold=is_bold,
                    font_size_px=font_size_px,
                    font_family=font_family,
                    paragraphs=paragraphs,
                    paragraph_details=paragraph_details,
                ))

            logical_col += colspan

        parsed.rows.append(row_cells)

    return parsed


def parse_docx_blocks(file_bytes: bytes) -> list[dict]:
    with zipfile.ZipFile(file_bytes if hasattr(file_bytes, "read") else __import__("io").BytesIO(file_bytes)) as z:
        xml = z.read("word/document.xml")
        styles_xml = z.read("word/styles.xml") if "word/styles.xml" in z.namelist() else None
        theme_xml = z.read("word/theme/theme1.xml") if "word/theme/theme1.xml" in z.namelist() else None

    root = etree.fromstring(xml)
    styles_root = etree.fromstring(styles_xml) if styles_xml else None
    theme_root = etree.fromstring(theme_xml) if theme_xml else None
    default_font_size_px, default_font_family = _get_default_run_style(styles_root, theme_root)
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
                font_size_px, font_family = _get_text_run_display_style(
                    child,
                    default_font_size_px=default_font_size_px,
                    default_font_family=default_font_family,
                    theme_root=theme_root,
                )
                margin_top_px, margin_bottom_px, line_height = _get_paragraph_spacing(child)
                margin_left_px, margin_right_px, text_indent_px = _get_paragraph_indent(child)
                blocks.append({
                    "kind": "paragraph",
                    "paragraph": ParsedParagraph(
                        text=text,
                        index=paragraph_index,
                        align=_get_paragraph_alignment(child),
                        is_bold=_is_paragraph_bold(child),
                        font_size_px=font_size_px,
                        font_family=font_family,
                        line_height=line_height,
                        margin_top_px=margin_top_px,
                        margin_bottom_px=margin_bottom_px,
                        margin_left_px=margin_left_px,
                        margin_right_px=margin_right_px,
                        text_indent_px=text_indent_px,
                    ),
                })
            paragraph_index += 1
        elif child.tag == W("tbl"):
            blocks.append({
                "kind": "table",
                "table": _parse_table_element(
                    child,
                    table_index,
                    default_font_size_px=default_font_size_px,
                    default_font_family=default_font_family,
                    theme_root=theme_root,
                ),
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
