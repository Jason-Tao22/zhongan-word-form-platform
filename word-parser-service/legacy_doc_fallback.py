from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from legacy_field_codes import DOCVARIABLE_PATTERN, MERGEFORMAT_PATTERN, strip_legacy_field_codes
from word_parser import ParsedCell, ParsedTable


def can_extract_legacy_doc_text() -> bool:
    return shutil.which("textutil") is not None


def extract_legacy_doc_text(filename: str, file_bytes: bytes) -> str:
    textutil = shutil.which("textutil")
    if not textutil:
        raise RuntimeError("当前环境未安装 textutil，无法提取旧版 .doc 文本")

    suffix = Path(filename).suffix or ".doc"
    stem = Path(filename).stem
    with tempfile.TemporaryDirectory(prefix="legacy-doc-text-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / f"{stem}{suffix}"
        output_path = tmp_path / f"{stem}.txt"
        input_path.write_bytes(file_bytes)

        result = subprocess.run(
            [
                textutil,
                "-convert",
                "txt",
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
            raise RuntimeError(stderr or "旧版 .doc 文本提取失败")
        return output_path.read_text(encoding="utf-8", errors="ignore")


def build_pseudo_tables_from_legacy_text(text: str) -> list[ParsedTable]:
    sections = [_extract_section_lines(chunk) for chunk in text.split("\f")]
    sections = [section for section in sections if section]
    if not sections:
        return []

    tables: list[ParsedTable] = []
    for table_index, lines in enumerate(sections):
        title = _find_section_title(lines)
        rows: list[list[ParsedCell]] = []
        row_index = 0
        rows.append([
            ParsedCell(text=title, row=row_index, col=0, colspan=2, is_bold=True, paragraphs=[title]),
        ])
        row_index += 1

        pending_label: str | None = None
        start_index = lines.index(title) + 1 if title in lines else 0
        for line in lines[start_index:]:
            if _is_noise_line(line):
                continue

            inline_label, inline_value = _split_inline_variable_line(line)
            if inline_label is not None:
                rows.append(_make_pair_row(row_index, inline_label, inline_value))
                row_index += 1
                pending_label = None
                continue

            if _looks_like_heading(line):
                rows.append([ParsedCell(text=_cleanup_label(line), row=row_index, col=0, colspan=2, is_bold=True, paragraphs=[line])])
                row_index += 1
                pending_label = None
                continue

            if DOCVARIABLE_PATTERN.search(line):
                label = pending_label or _label_from_variable_line(line)
                rows.append(_make_pair_row(row_index, label, line))
                row_index += 1
                pending_label = None
                continue

            if _looks_like_label_only(line):
                pending_label = _cleanup_label(line)
                continue

            if pending_label:
                rows.append(_make_pair_row(row_index, pending_label, line))
                row_index += 1
                pending_label = None
                continue

            rows.append(_make_pair_row(row_index, line, ""))
            row_index += 1

        tables.append(ParsedTable(index=table_index, rows=rows))

    return tables


def _make_pair_row(row_index: int, label: str, value: str) -> list[ParsedCell]:
    safe_label = _cleanup_label(label) or f"字段{row_index}"
    safe_value = _cleanup_value(value)
    unit = _extract_unit(value)
    if unit and unit not in safe_label:
        safe_label = f"{safe_label} ({unit})"
    return [
        ParsedCell(text=safe_label, row=row_index, col=0, paragraphs=[safe_label]),
        ParsedCell(text=safe_value, row=row_index, col=1, paragraphs=[safe_value] if safe_value else []),
    ]


def _normalize_line(line: str) -> str:
    return strip_legacy_field_codes(re.sub(r"\s+", " ", line or "").strip())


def _cleanup_label(label: str) -> str:
    label = _normalize_line(label)
    label = re.sub(r"\s+", " ", label)
    label = label.strip(":： ")
    return label


def _cleanup_value(value: str) -> str:
    value = _normalize_line(value)
    value = re.sub(r"\s+", " ", value)
    if re.fullmatch(r"[A-Za-z%/().0-9+-]+", value):
        return ""
    return value.strip(":： ")


def _extract_unit(value: str) -> str | None:
    cleaned = _normalize_line(value)
    if cleaned in {"", "年", "月", "日"}:
        return None
    if re.fullmatch(r"[A-Za-z%/().0-9+-]+", cleaned):
        return cleaned
    return None


def _looks_like_label_only(line: str) -> bool:
    return (
        "DOCVARIABLE" not in line
        and len(line) <= 24
        and not line.startswith("文件编号")
        and not line.startswith("报告编号")
        and not line.startswith("注：")
    )


def _looks_like_heading(line: str) -> bool:
    return (
        len(line) <= 80
        and "DOCVARIABLE" not in line
        and (
            line.endswith("报告")
            or line.endswith("附页")
            or any(keyword in line for keyword in ["说明", "结论", "结果", "校验", "检验", "检查", "审查"])
        )
    )


def _label_from_variable_line(line: str) -> str:
    return _normalize_line(line) or "内容"


def _is_noise_line(line: str) -> bool:
    return line in {"中安检测集团（湖北）有限公司"} or line.startswith("文件编号")


def _split_inline_variable_line(line: str) -> tuple[str | None, str]:
    if "DOCVARIABLE" not in line:
        return None, ""
    match = DOCVARIABLE_PATTERN.search(line)
    if not match:
        return None, ""
    label = _cleanup_label(line[: match.start()])
    if not label:
        return None, ""
    return label, line[match.start() :]


def _extract_section_lines(chunk: str) -> list[str]:
    lines = [_normalize_line(line) for line in chunk.splitlines()]
    return [line for line in lines if line]


def _find_section_title(lines: list[str]) -> str:
    for line in lines[:8]:
        if _looks_like_heading(line) and not line.startswith("报告编号"):
            return _cleanup_label(line)
    for line in lines[:8]:
        if len(line) >= 4 and not _is_noise_line(line):
            return _cleanup_label(line)
    return "模板片段"
