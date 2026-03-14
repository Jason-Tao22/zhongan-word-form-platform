"""
兼容旧版 Word 文档的转换工具。

优先支持：
- .docx: 直接使用
- .doc: 通过 soffice 转成 .docx 后继续处理
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class ConversionError(RuntimeError):
    pass


def can_convert_legacy_doc() -> bool:
    return shutil.which("textutil") is not None or shutil.which("soffice") is not None


def normalize_word_bytes(filename: str, file_bytes: bytes) -> tuple[str, bytes]:
    lower_name = filename.lower()
    if lower_name.endswith(".docx"):
        return filename, file_bytes
    if lower_name.endswith(".doc"):
        return _convert_doc_bytes_to_docx(filename, file_bytes)
    raise ConversionError("只支持 .docx 或 .doc 格式")


def _convert_doc_bytes_to_docx(filename: str, file_bytes: bytes) -> tuple[str, bytes]:
    textutil = shutil.which("textutil")
    soffice = shutil.which("soffice")
    if textutil:
        return _convert_with_textutil(filename, file_bytes)
    if soffice:
        return _convert_with_soffice(filename, file_bytes, soffice)
    raise ConversionError("当前环境未安装 textutil/soffice，无法自动转换 .doc，请先转成 .docx")


def _convert_with_textutil(filename: str, file_bytes: bytes) -> tuple[str, bytes]:
    suffix = Path(filename).suffix or ".doc"
    stem = Path(filename).stem

    with tempfile.TemporaryDirectory(prefix="doc-convert-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / f"{stem}{suffix}"
        output_path = tmp_path / f"{stem}.docx"
        input_path.write_bytes(file_bytes)

        result = subprocess.run(
            [
                "textutil",
                "-convert",
                "docx",
                "-output",
                str(output_path),
                str(input_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise ConversionError(f".doc 转换失败: {stderr or 'unknown error'}")

        if not output_path.exists():
            raise ConversionError(".doc 转换失败: 未生成 docx 文件")

        return output_path.name, output_path.read_bytes()


def _convert_with_soffice(filename: str, file_bytes: bytes, soffice: str) -> tuple[str, bytes]:
    suffix = Path(filename).suffix or ".doc"
    stem = Path(filename).stem

    with tempfile.TemporaryDirectory(prefix="doc-convert-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / f"{stem}{suffix}"
        input_path.write_bytes(file_bytes)

        result = subprocess.run(
            [
                soffice,
                "-env:UserInstallation=file:///tmp/libreoffice-codex-profile",
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                str(tmp_path),
                str(input_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise ConversionError(f".doc 转换失败: {stderr or 'unknown error'}")

        output_path = tmp_path / f"{stem}.docx"
        if not output_path.exists():
            raise ConversionError(".doc 转换失败: 未生成 docx 文件")

        return output_path.name, output_path.read_bytes()
