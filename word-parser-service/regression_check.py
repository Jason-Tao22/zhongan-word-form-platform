"""
本地回归检查脚本。

检查链路：
1. 解析指定 Word 模板
2. 对 AI 原始输出做 post_process
3. 用 Pydantic 验证 schema
4. 生成 DDL
5. 生成交互原型 HTML
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ddl_generator import generate_ddl
from models import FormSchema
from post_processor import post_process
from prototype_builder import build_prototype_html
from word_parser import parse_docx_blocks


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local regression checks for the Word parser pipeline.")
    parser.add_argument("input_docx", help="Input .docx file path")
    parser.add_argument(
        "--raw-json",
        default="../test_output.json",
        help="Raw AI output JSON path. Can be subForms[] or full schema object.",
    )
    parser.add_argument(
        "--out-dir",
        default="output/regression",
        help="Directory to write checked artifacts into.",
    )
    args = parser.parse_args()

    service_root = Path.cwd()
    input_path = Path(args.input_docx).expanduser().resolve()
    raw_json_path = Path(args.raw_json).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_payload = json.loads(raw_json_path.read_text(encoding="utf-8"))
    sub_forms = raw_payload["subForms"] if isinstance(raw_payload, dict) and "subForms" in raw_payload else raw_payload

    blocks = parse_docx_blocks(input_path.read_bytes())
    tables = [block["table"] for block in blocks if block["kind"] == "table"]
    processed = post_process(sub_forms, tables)

    schema = FormSchema(
        templateId="regression-demo",
        templateName=input_path.stem,
        sourceFile=input_path.name,
        createdAt="2026-03-08T00:00:00Z",
        subForms=processed,
    )
    schema_dict = schema.model_dump()

    ddl = generate_ddl(schema_dict["subForms"])
    html = build_prototype_html(input_path.stem, input_path.name, tables, schema_dict["subForms"], blocks=blocks)

    schema_path = out_dir / f"{input_path.stem}.schema.checked.json"
    ddl_path = out_dir / f"{input_path.stem}.ddl.sql"
    html_path = out_dir / f"{input_path.stem}.interactive.html"

    schema_path.write_text(json.dumps(schema_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    ddl_path.write_text(ddl, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    print(f"tables={len(tables)}")
    print(f"sub_forms={len(schema.subForms)}")
    print(f"schema={schema_path}")
    print(f"ddl={ddl_path}")
    print(f"html={html_path}")
    print(f"cwd={service_root}")


if __name__ == "__main__":
    main()
