"""
命令行原型渲染器。

支持：
1. 直接从 .docx / .doc 渲染 HTML 原型
2. 可选加载 schema，把字段控件嵌入原型
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from doc_converter import normalize_word_bytes
from post_processor import post_process
from prototype_builder import build_prototype_html
from word_parser import parse_docx_blocks


def load_sub_forms(schema_path: Path) -> list[dict]:
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "subForms" in payload:
        return payload["subForms"]
    if isinstance(payload, list):
        return payload
    raise SystemExit("Schema JSON 必须是 subForms 数组，或包含 subForms 的顶层对象。")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Word tables into an HTML prototype preview.")
    parser.add_argument("input_word", help="Input .docx or .doc file path")
    parser.add_argument("--schema-json", help="Optional JSON file containing subForms or full schema")
    parser.add_argument(
        "--output",
        help="Output HTML path. Defaults to output/prototype/<word_stem>.html",
    )
    args = parser.parse_args()

    input_path = Path(args.input_word).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"File not found: {input_path}")

    normalized_name, normalized_bytes = normalize_word_bytes(input_path.name, input_path.read_bytes())
    blocks = parse_docx_blocks(normalized_bytes)
    tables = [block["table"] for block in blocks if block["kind"] == "table"]

    sub_forms = None
    if args.schema_json:
        schema_path = Path(args.schema_json).expanduser().resolve()
        raw_sub_forms = load_sub_forms(schema_path)
        sub_forms = post_process(raw_sub_forms, tables)

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else Path.cwd() / "output" / "prototype" / f"{Path(normalized_name).stem}.html"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html = build_prototype_html(Path(normalized_name).stem, normalized_name, tables, sub_forms, blocks=blocks)
    output_path.write_text(html, encoding="utf-8")

    mode = "interactive" if sub_forms else "layout-only"
    print(f"Rendered {len(tables)} tables to {output_path} ({mode})")


if __name__ == "__main__":
    main()
