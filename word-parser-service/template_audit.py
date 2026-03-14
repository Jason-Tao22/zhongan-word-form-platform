from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ddl_generator import generate_ddl
from doc_converter import ConversionError, normalize_word_bytes
from heuristic_analyzer import analyze_tables_heuristically
from legacy_doc_html import extract_legacy_doc_html, parse_legacy_doc_html_blocks
from legacy_doc_fallback import build_pseudo_tables_from_legacy_text, extract_legacy_doc_text
from models import FormSchema
from openai_analyzer import analyze_tables_with_openai
from post_processor import post_process
from prototype_builder import build_prototype_html
from word_parser import parse_docx_blocks, tables_to_prompt_text


@dataclass
class AuditEntry:
    file: str
    ext: str
    status: str
    analysis_mode: str | None = None
    converted_to_docx: bool = False
    template_name: str | None = None
    table_count: int = 0
    sub_form_count: int = 0
    ddl_statement_count: int = 0
    fingerprint: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    extraction_mode: str | None = None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _count_ddl_statements(ddl: str) -> int:
    return sum(1 for part in ddl.split(";") if part.strip())


def _audit_one(path: Path, api_key: str | None, include_prototype: bool, allow_heuristic_fallback: bool, model: str) -> AuditEntry:
    started_at = time.perf_counter()
    try:
        normalized_name, normalized_bytes = normalize_word_bytes(path.name, path.read_bytes())
    except ConversionError as exc:
        return AuditEntry(
            file=str(path),
            ext=path.suffix.lower(),
            status="skipped",
            error=str(exc),
            duration_seconds=time.perf_counter() - started_at,
        )

    converted = normalized_name != path.name

    try:
        blocks = parse_docx_blocks(normalized_bytes)
        tables = [block["table"] for block in blocks if block["kind"] == "table"]
        extraction_mode = "docx"
        if not tables:
            try:
                legacy_html = extract_legacy_doc_html(path.name, path.read_bytes())
                blocks = parse_legacy_doc_html_blocks(legacy_html)
                tables = [block["table"] for block in blocks if block["kind"] == "table"]
                extraction_mode = "legacy-html" if tables else extraction_mode
            except Exception:
                tables = []
        if not tables:
            try:
                legacy_text = extract_legacy_doc_text(path.name, path.read_bytes())
                tables = build_pseudo_tables_from_legacy_text(legacy_text)
                blocks = None
                extraction_mode = "legacy-text"
            except Exception:
                tables = []
                blocks = None
        if not tables:
            return AuditEntry(
                file=str(path),
                ext=path.suffix.lower(),
                status="failed",
                converted_to_docx=converted,
                error="文档中未找到表格",
                duration_seconds=time.perf_counter() - started_at,
            )

        table_text = tables_to_prompt_text(tables)
        fingerprint = _sha256_text(table_text)

        analysis_mode = "openai"
        if api_key:
            try:
                sub_forms_raw = analyze_tables_with_openai(table_text, normalized_name, api_key, model)
            except Exception as exc:
                if not allow_heuristic_fallback:
                    raise RuntimeError(f"OpenAI 分析失败: {exc}") from exc
                sub_forms_raw = analyze_tables_heuristically(tables, normalized_name)
                analysis_mode = "heuristic"
        else:
            if not allow_heuristic_fallback:
                raise RuntimeError("未配置 OPENAI_API_KEY，且批量审计未开启启发式兜底")
            sub_forms_raw = analyze_tables_heuristically(tables, normalized_name)
            analysis_mode = "heuristic"

        processed = post_process(sub_forms_raw, tables)
        schema = FormSchema(
            templateId=f"audit-{fingerprint[:12]}",
            templateName=Path(normalized_name).stem,
            sourceFile=normalized_name,
            createdAt=datetime.now(timezone.utc).isoformat(),
            subForms=processed,
        )
        schema_dict = schema.model_dump()
        ddl = generate_ddl(schema_dict["subForms"])

        if include_prototype:
            build_prototype_html(
                schema.templateName,
                normalized_name,
                tables,
                schema_dict["subForms"],
                blocks=blocks,
            )

        return AuditEntry(
            file=str(path),
            ext=path.suffix.lower(),
            status="success",
            analysis_mode=analysis_mode,
            converted_to_docx=converted,
            template_name=schema.templateName,
            table_count=len(tables),
            sub_form_count=len(schema.subForms),
            ddl_statement_count=_count_ddl_statements(ddl),
            fingerprint=fingerprint,
            duration_seconds=time.perf_counter() - started_at,
            extraction_mode=extraction_mode,
        )
    except Exception as exc:
        return AuditEntry(
            file=str(path),
            ext=path.suffix.lower(),
            status="failed",
            converted_to_docx=converted,
            error=str(exc),
            duration_seconds=time.perf_counter() - started_at,
        )


def _build_summary(entries: list[AuditEntry]) -> dict[str, Any]:
    totals = {
        "total": len(entries),
        "success": sum(1 for item in entries if item.status == "success"),
        "failed": sum(1 for item in entries if item.status == "failed"),
        "skipped": sum(1 for item in entries if item.status == "skipped"),
        "docx": sum(1 for item in entries if item.ext == ".docx"),
        "doc": sum(1 for item in entries if item.ext == ".doc"),
        "openai": sum(1 for item in entries if item.analysis_mode == "openai"),
        "heuristic": sum(1 for item in entries if item.analysis_mode == "heuristic"),
    }

    fingerprint_map: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        if entry.fingerprint:
            fingerprint_map[entry.fingerprint].append(entry.file)

    duplicate_groups = [
        {"fingerprint": fingerprint, "files": files}
        for fingerprint, files in fingerprint_map.items()
        if len(files) > 1
    ]

    return {
        "totals": totals,
        "duplicateFingerprintGroups": duplicate_groups,
    }


def _write_markdown_report(out_path: Path, summary: dict[str, Any], entries: list[AuditEntry], source_dir: Path) -> None:
    totals = summary["totals"]
    lines = [
        "# Template Audit Report",
        "",
        f"- source: `{source_dir}`",
        f"- generated_at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- total: `{totals['total']}`",
        f"- success: `{totals['success']}`",
        f"- failed: `{totals['failed']}`",
        f"- skipped: `{totals['skipped']}`",
        f"- docx: `{totals['docx']}`",
        f"- doc: `{totals['doc']}`",
        f"- openai: `{totals['openai']}`",
        f"- heuristic: `{totals['heuristic']}`",
        "",
        "## Failed Or Skipped",
        "",
    ]

    failed_or_skipped = [item for item in entries if item.status != "success"]
    if not failed_or_skipped:
        lines.append("- none")
    else:
        for item in failed_or_skipped:
            lines.append(f"- `{Path(item.file).name}` / `{item.status}` / {item.error}")

    lines.extend(["", "## Duplicate Structure Candidates", ""])
    duplicates = summary["duplicateFingerprintGroups"]
    if not duplicates:
        lines.append("- none")
    else:
        for group in duplicates:
            lines.append(f"- `{group['fingerprint'][:12]}`")
            for file in group["files"]:
                lines.append(f"  - `{Path(file).name}`")

    lines.extend(["", "## Successful Templates", ""])
    for item in entries:
        if item.status != "success":
            continue
            lines.append(
                f"- `{Path(item.file).name}` / mode=`{item.analysis_mode}` / tables=`{item.table_count}` / "
            f"sub_forms=`{item.sub_form_count}` / ddl=`{item.ddl_statement_count}` / "
            f"extract=`{item.extraction_mode}` / seconds=`{item.duration_seconds:.1f}`"
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Audit a directory of Word templates for parser readiness.")
    parser.add_argument("input_dir", help="Directory containing .docx / .doc templates")
    parser.add_argument(
        "--output-dir",
        default="output/template-audit",
        help="Directory to write audit report files",
    )
    parser.add_argument(
        "--include-prototype",
        action="store_true",
        help="Also build prototype HTML during audit to catch renderer errors",
    )
    parser.add_argument(
        "--allow-heuristic-fallback",
        action="store_true",
        help="If OPENAI_API_KEY is missing or OpenAI fails, allow local heuristic fallback",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-5")

    entries: list[AuditEntry] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".docx", ".doc"}:
            continue
        entries.append(
            _audit_one(
                path,
                api_key,
                include_prototype=args.include_prototype,
                allow_heuristic_fallback=args.allow_heuristic_fallback,
                model=model,
            )
        )

    summary = _build_summary(entries)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceDir": str(input_dir),
        "summary": summary,
        "entries": [asdict(item) for item in entries],
    }

    json_path = out_dir / "template-audit.json"
    md_path = out_dir / "template-audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown_report(md_path, summary, entries, input_dir)

    print(f"json={json_path}")
    print(f"markdown={md_path}")
    print(json.dumps(summary["totals"], ensure_ascii=False))


if __name__ == "__main__":
    main()
