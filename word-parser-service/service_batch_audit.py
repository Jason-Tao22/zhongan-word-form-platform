from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from storage_plan import count_storage_tables
from quality_assessor import assess_quality


@dataclass
class AuditEntry:
    file: str
    ext: str
    status: str
    http_status: int
    duration_seconds: float
    template_name: str | None = None
    analysis_mode: str | None = None
    sub_form_count: int = 0
    storage_table_count: int = 0
    document_block_count: int = 0
    validation_warning: str | None = None
    quality_warning: str | None = None
    error: str | None = None


def audit_one(base_url: str, path: Path, include_prototype: bool, timeout_seconds: int) -> AuditEntry:
    started_at = time.perf_counter()
    try:
        with path.open("rb") as handle:
            response = requests.post(
                f"{base_url.rstrip('/')}/parse-word",
                params={"include_prototype": str(include_prototype).lower()},
                files={"file": (path.name, handle)},
                timeout=timeout_seconds,
            )
    except Exception as exc:
        return AuditEntry(
            file=str(path),
            ext=path.suffix.lower(),
            status="failed",
            http_status=0,
            duration_seconds=time.perf_counter() - started_at,
            error=str(exc),
        )

    duration_seconds = time.perf_counter() - started_at
    payload = {}
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}

    if response.status_code not in {200, 207}:
        error = payload.get("detail") or payload.get("msg") or payload.get("raw") or f"HTTP {response.status_code}"
        return AuditEntry(
            file=str(path),
            ext=path.suffix.lower(),
            status="failed",
            http_status=response.status_code,
            duration_seconds=duration_seconds,
            error=str(error),
        )

    schema = payload.get("schema", {})
    document_blocks = schema.get("documentBlocks", [])
    sub_forms = schema.get("subForms", [])
    computed_quality_warning = assess_quality(sub_forms, document_blocks)
    parser_quality_warning = payload.get("qualityWarning")
    if parser_quality_warning and computed_quality_warning and parser_quality_warning != computed_quality_warning:
        quality_warning = f"{parser_quality_warning}；{computed_quality_warning}"
    else:
        quality_warning = parser_quality_warning or computed_quality_warning
    status = "warning" if response.status_code == 207 or quality_warning else "success"
    return AuditEntry(
        file=str(path),
        ext=path.suffix.lower(),
        status=status,
        http_status=response.status_code,
        duration_seconds=duration_seconds,
        template_name=payload.get("templateName"),
        analysis_mode=payload.get("analysisMode"),
        sub_form_count=len(sub_forms),
        storage_table_count=count_storage_tables(sub_forms),
        document_block_count=len(document_blocks),
        validation_warning=payload.get("validationError"),
        quality_warning=quality_warning,
    )


def write_reports(output_dir: Path, entries: list[AuditEntry], source_dir: Path, parser_url: str) -> None:
    totals = {
        "total": len(entries),
        "success": sum(1 for entry in entries if entry.status == "success"),
        "warning": sum(1 for entry in entries if entry.status == "warning"),
        "failed": sum(1 for entry in entries if entry.status == "failed"),
        "quality_warning": sum(1 for entry in entries if entry.quality_warning),
        "docx": sum(1 for entry in entries if entry.ext == ".docx"),
        "doc": sum(1 for entry in entries if entry.ext == ".doc"),
        "openai": sum(1 for entry in entries if entry.analysis_mode == "openai"),
        "max_seconds": max((entry.duration_seconds for entry in entries), default=0.0),
    }
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceDir": str(source_dir),
        "parserUrl": parser_url,
        "summary": totals,
        "entries": [asdict(entry) for entry in entries],
    }
    json_path = output_dir / "service-audit.json"
    md_path = output_dir / "service-audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Parser Service Audit",
        "",
        f"- source: `{source_dir}`",
        f"- parser: `{parser_url}`",
        f"- generated_at: `{payload['generatedAt']}`",
        f"- total: `{totals['total']}`",
        f"- success: `{totals['success']}`",
        f"- warning: `{totals['warning']}`",
        f"- failed: `{totals['failed']}`",
        f"- quality_warning: `{totals['quality_warning']}`",
        f"- docx: `{totals['docx']}`",
        f"- doc: `{totals['doc']}`",
        f"- openai: `{totals['openai']}`",
        f"- max_seconds: `{totals['max_seconds']:.1f}`",
        "",
        "## Failed Or Warning",
        "",
    ]

    issues = [entry for entry in entries if entry.status != "success" or entry.quality_warning]
    if not issues:
        lines.append("- none")
    else:
        for entry in issues:
            reason = entry.error or entry.validation_warning or entry.quality_warning or "unknown"
            lines.append(
                f"- `{Path(entry.file).name}` / status=`{entry.status}` / http=`{entry.http_status}` / "
                f"seconds=`{entry.duration_seconds:.1f}` / storage_tables=`{entry.storage_table_count}` / {reason}"
            )

    lines.extend(["", "## Successful Templates", ""])
    for entry in entries:
        if entry.status != "success":
            continue
        lines.append(
            f"- `{Path(entry.file).name}` / mode=`{entry.analysis_mode}` / sub_forms=`{entry.sub_form_count}` / "
            f"storage_tables=`{entry.storage_table_count}` / blocks=`{entry.document_block_count}` / "
            f"seconds=`{entry.duration_seconds:.1f}`"
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"json={json_path}")
    print(f"markdown={md_path}")
    print(json.dumps(totals, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Call the live parser service for every .doc/.docx in a directory.")
    parser.add_argument("input_dir", help="Directory containing Word templates")
    parser.add_argument("--parser-url", default="http://127.0.0.1:8001", help="Parser service base URL")
    parser.add_argument("--output-dir", default="output/service-audit", help="Directory for reports")
    parser.add_argument("--resume-json", help="Existing service-audit.json to reuse previous success entries")
    parser.add_argument("--include-prototype", action="store_true", help="Generate prototype HTML during audit")
    parser.add_argument("--timeout-seconds", type=int, default=1200, help="Per-file request timeout")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    previous_entries: dict[str, AuditEntry] = {}
    if args.resume_json:
        resume_path = Path(args.resume_json).expanduser().resolve()
        if resume_path.exists():
            payload = json.loads(resume_path.read_text(encoding="utf-8"))
            previous_entries = {
                entry["file"]: AuditEntry(**entry)
                for entry in payload.get("entries", [])
            }

    entries: list[AuditEntry] = []
    for path in sorted(input_dir.rglob("*")):
        if path.suffix.lower() not in {".doc", ".docx"} or not path.is_file():
            continue
        previous_entry = previous_entries.get(str(path))
        if previous_entry and previous_entry.status == "success":
            entry = previous_entry
            print(
                json.dumps(
                    {
                        "file": path.name,
                        "status": "reused-success",
                        "http": entry.http_status,
                        "seconds": round(entry.duration_seconds, 1),
                        "mode": entry.analysis_mode,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            entry = audit_one(args.parser_url, path, args.include_prototype, args.timeout_seconds)
            print(
                json.dumps(
                    {
                        "file": path.name,
                        "status": entry.status,
                        "http": entry.http_status,
                        "seconds": round(entry.duration_seconds, 1),
                        "mode": entry.analysis_mode,
                    },
                    ensure_ascii=False,
                )
            )
        entries.append(entry)
        write_reports(output_dir, entries, input_dir, args.parser_url)

    write_reports(output_dir, entries, input_dir, args.parser_url)


if __name__ == "__main__":
    main()
