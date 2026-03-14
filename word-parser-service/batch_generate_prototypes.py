"""
批量生成 Word 原型 HTML。

默认遍历一个目录下所有 .docx / .doc 文件：
- .docx 直接处理
- .doc 若环境安装了 soffice，则自动转换后处理
"""
from __future__ import annotations

import argparse
from pathlib import Path

from doc_converter import ConversionError, normalize_word_bytes
from prototype_builder import build_prototype_html
from word_parser import parse_docx_blocks


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch generate HTML prototypes for Word templates.")
    parser.add_argument("input_dir", help="Directory containing .docx / .doc files")
    parser.add_argument(
        "--output-dir",
        help="Output directory. Defaults to output/prototype-batch",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"Not a directory: {input_dir}")

    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else Path.cwd() / "output" / "prototype-batch"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0

    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".doc", ".docx"}:
            continue

        try:
            normalized_name, normalized_bytes = normalize_word_bytes(path.name, path.read_bytes())
            blocks = parse_docx_blocks(normalized_bytes)
            tables = [block["table"] for block in blocks if block["kind"] == "table"]
            relative_parent = path.relative_to(input_dir).parent
            target_dir = output_dir / relative_parent
            target_dir.mkdir(parents=True, exist_ok=True)
            html_path = target_dir / f"{Path(normalized_name).stem}.html"
            html = build_prototype_html(Path(normalized_name).stem, normalized_name, tables, blocks=blocks)
            html_path.write_text(html, encoding="utf-8")
            generated += 1
            print(f"OK   {path.relative_to(input_dir)} -> {html_path.relative_to(output_dir)}")
        except ConversionError as exc:
            skipped += 1
            print(f"SKIP {path.relative_to(input_dir)} -> {exc}")
        except Exception as exc:
            skipped += 1
            print(f"FAIL {path.relative_to(input_dir)} -> {exc}")

    print(f"generated={generated}")
    print(f"skipped={skipped}")
    print(f"output_dir={output_dir}")


if __name__ == "__main__":
    main()
