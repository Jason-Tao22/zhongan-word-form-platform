"""
FastAPI 入口
POST /parse-word  →  JSON Schema + PostgreSQL DDL
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv

from doc_converter import ConversionError, normalize_word_bytes
from legacy_doc_html import extract_legacy_doc_html, parse_legacy_doc_html_blocks
from legacy_doc_fallback import build_pseudo_tables_from_legacy_text, extract_legacy_doc_text
from legacy_strategy import choose_legacy_representation
from word_parser import parse_docx_blocks, tables_to_prompt_text
from ddl_generator import generate_ddl
from heuristic_analyzer import analyze_tables_heuristically
from openai_block_hints import analyze_block_hints_with_openai
from openai_analyzer import analyze_tables_with_openai
from models import FormSchema
from post_processor import post_process
from prototype_builder import build_document_blocks, build_prototype_html
from storage_plan import apply_storage_plan
from storage_plan import count_storage_tables
from quality_assessor import assess_quality

app = FastAPI(
    title="Word → Form Schema Service",
    description="上传 Word 文档，返回 JSON Schema 和 PostgreSQL DDL",
    version="1.0.0",
)

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")
ALLOW_HEURISTIC_FALLBACK = os.environ.get("ALLOW_HEURISTIC_FALLBACK", "").lower() in {"1", "true", "yes", "on"}
CACHE_VERSION = "2026-04-02-v5-typography-styles"
CACHE_DIR = Path(__file__).resolve().parent / "data" / "parse-cache"


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

class ParseResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    templateId: str
    templateName: str
    sourceFile: str
    schemaPayload: dict = Field(alias="schema")   # FormSchema dict
    ddl: str              # PostgreSQL DDL string
    reviewNeeded: bool = True
    analysisMode: str = "openai"
    storageTableCount: int = 0
    qualityWarning: Optional[str] = None
    structureFingerprint: str
    sourceSha256: str
    prototypeHtml: Optional[str] = None


class ParserStatus(BaseModel):
    status: str = "ok"
    provider: str = "openai"
    model: str
    openaiConfigured: bool
    heuristicFallbackAllowed: bool
    defaultMode: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_key(
    normalized_filename: str,
    source_sha256: str,
    *,
    include_prototype: bool,
    analysis_mode: str,
    legacy_mode: str | None,
) -> str:
    payload = "|".join([
        CACHE_VERSION,
        normalized_filename,
        source_sha256,
        OPENAI_MODEL,
        analysis_mode,
        legacy_mode or "none",
        "prototype" if include_prototype else "schema-only",
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.json"


def _load_cached_response(cache_key: str) -> dict | None:
    path = _cache_path(cache_key)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _store_cached_response(cache_key: str, status_code: int, content: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(cache_key).write_text(
        json.dumps({"statusCode": status_code, "content": content}, ensure_ascii=False),
        encoding="utf-8",
    )


def _hydrate_cached_content(cached_content: dict) -> dict:
    content = copy.deepcopy(cached_content)
    template_id = str(uuid.uuid4())
    content["templateId"] = template_id
    schema = content.get("schema")
    if isinstance(schema, dict):
        schema["templateId"] = template_id
        schema["createdAt"] = _utc_now_iso()
    return content


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config-status", response_model=ParserStatus, summary="返回当前解析服务的模型配置状态")
def config_status():
    openai_configured = bool(OPENAI_API_KEY)
    default_mode = "openai" if openai_configured else "heuristic" if ALLOW_HEURISTIC_FALLBACK else "unavailable"
    return ParserStatus(
        model=OPENAI_MODEL,
        openaiConfigured=openai_configured,
        heuristicFallbackAllowed=ALLOW_HEURISTIC_FALLBACK,
        defaultMode=default_mode,
    )


@app.post("/parse-word", response_model=ParseResult, summary="上传 Word 文档，生成表单 Schema 和 DDL")
async def parse_word(
    file: UploadFile = File(..., description="Word 文档 (.docx / .doc)"),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    include_prototype: bool = Query(default=False, description="是否在响应中附带 HTML 原型"),
):
    # 校验文件类型
    if not file.filename.lower().endswith((".docx", ".doc")):
        raise HTTPException(status_code=400, detail="只支持 .docx 或 .doc 格式")

    api_key = x_api_key or OPENAI_API_KEY

    upload_bytes = await file.read()
    upload_sha256 = hashlib.sha256(upload_bytes).hexdigest()
    try:
        normalized_filename, file_bytes = normalize_word_bytes(file.filename, upload_bytes)
    except ConversionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 1. 解析 Word
    try:
        blocks = parse_docx_blocks(file_bytes)
        tables = [block["table"] for block in blocks if block["kind"] == "table"]
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Word 解析失败: {e}")

    legacy_mode: str | None = None
    if not tables:
        legacy_html_blocks: list[dict] = []
        legacy_html_tables: list = []
        legacy_text_tables: list = []
        legacy_note: str | None = None
        try:
            legacy_html = extract_legacy_doc_html(file.filename, upload_bytes)
            legacy_html_blocks = parse_legacy_doc_html_blocks(legacy_html)
            legacy_html_tables = [block["table"] for block in legacy_html_blocks if block["kind"] == "table"]
        except Exception:
            legacy_html_blocks = []
            legacy_html_tables = []

        try:
            legacy_text = extract_legacy_doc_text(file.filename, upload_bytes)
            legacy_text_tables = build_pseudo_tables_from_legacy_text(legacy_text)
        except Exception:
            legacy_text_tables = []

        selection = choose_legacy_representation(legacy_html_blocks, legacy_html_tables, legacy_text_tables)
        tables = selection.tables
        blocks = selection.blocks
        legacy_mode = selection.mode if selection.mode != "none" else None
        legacy_note = selection.note
    else:
        legacy_note = None

    if not tables:
        raise HTTPException(status_code=422, detail="文档中未找到任何表格")

    # 2. 转成 AI 可读文本
    table_text = tables_to_prompt_text(tables)
    structure_fingerprint = hashlib.sha256(table_text.encode("utf-8")).hexdigest()
    source_sha256 = upload_sha256

    # 3. 调用 AI 分析
    review_needed = True
    analysis_mode = "openai"
    predicted_analysis_mode = "openai" if api_key else "heuristic" if ALLOW_HEURISTIC_FALLBACK else "unavailable"
    if predicted_analysis_mode != "unavailable":
        cache_key = _cache_key(
            normalized_filename,
            source_sha256,
            include_prototype=include_prototype,
            analysis_mode=predicted_analysis_mode,
            legacy_mode=legacy_mode,
        )
        cached_response = _load_cached_response(cache_key)
        if cached_response:
            hydrated_content = _hydrate_cached_content(cached_response["content"])
            return JSONResponse(status_code=int(cached_response["statusCode"]), content=hydrated_content)

    if not api_key:
        if ALLOW_HEURISTIC_FALLBACK:
            sub_forms_raw = analyze_tables_heuristically(tables, normalized_filename)
            analysis_mode = "heuristic"
        else:
            raise HTTPException(status_code=503, detail="未配置 OPENAI_API_KEY，当前已禁用启发式自动兜底")
    else:
        try:
            sub_forms_raw = analyze_tables_with_openai(table_text, normalized_filename, api_key, OPENAI_MODEL)
        except Exception as e:
            if ALLOW_HEURISTIC_FALLBACK:
                sub_forms_raw = analyze_tables_heuristically(tables, normalized_filename)
                analysis_mode = "heuristic"
            else:
                raise HTTPException(status_code=502, detail=f"OpenAI 分析失败: {e}")

    cache_key = _cache_key(
        normalized_filename,
        source_sha256,
        include_prototype=include_prototype,
        analysis_mode=analysis_mode,
        legacy_mode=legacy_mode,
    )
    cached_response = _load_cached_response(cache_key)
    if cached_response:
        hydrated_content = _hydrate_cached_content(cached_response["content"])
        return JSONResponse(status_code=int(cached_response["statusCode"]), content=hydrated_content)

    # 4. 后处理，尽量用 Word 原始结构补回布局信息
    try:
        sub_forms_processed = post_process(sub_forms_raw, tables)
        sub_forms_processed = apply_storage_plan(normalized_filename.removesuffix(".docx"), sub_forms_processed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"后处理失败: {e}")

    document_hints = {"paragraphs": {}, "cells": {}}
    if api_key and legacy_mode != "text":
        try:
            document_hints = analyze_block_hints_with_openai(blocks, api_key, OPENAI_MODEL)
        except Exception:
            document_hints = {"paragraphs": {}, "cells": {}}

    # 5. 组装 FormSchema
    template_id = str(uuid.uuid4())
    schema_dict = {
        "schemaVersion": "1.0",
        "templateId": template_id,
        "templateName": normalized_filename.removesuffix(".docx"),
        "sourceFile": normalized_filename,
        "createdAt": _utc_now_iso(),
        "sqlDatabase": "postgresql",
        "subForms": sub_forms_processed,
        "documentBlocks": build_document_blocks(
            tables,
            sub_forms_processed,
            blocks=blocks,
            ai_hints=document_hints,
        ),
    }

    # 6. 验证 schema（用 Pydantic）
    try:
        schema_obj = FormSchema(**schema_dict)
    except Exception as e:
        quality_warning = assess_quality(sub_forms_processed, schema_dict["documentBlocks"])
        if legacy_note:
            quality_warning = f"{quality_warning}；{legacy_note}" if quality_warning else legacy_note
        # 验证失败仍返回，但标记需要人工审核
        content = {
            "templateId": template_id,
            "templateName": schema_dict["templateName"],
            "sourceFile": normalized_filename,
            "schema": schema_dict,
            "ddl": "",
            "reviewNeeded": review_needed,
            "analysisMode": analysis_mode,
            "storageTableCount": count_storage_tables(sub_forms_processed),
            "qualityWarning": quality_warning,
            "structureFingerprint": structure_fingerprint,
            "sourceSha256": source_sha256,
            "validationError": str(e),
            "prototypeHtml": build_prototype_html(
                schema_dict["templateName"],
                normalized_filename,
                tables,
                sub_forms_processed,
                blocks=blocks,
                ai_hints=document_hints,
            )
            if include_prototype else None,
        }
        _store_cached_response(cache_key, 207, content)
        return JSONResponse(
            status_code=207,
            content=content,
        )

    # 7. 生成 DDL
    ddl = generate_ddl(schema_obj.model_dump()["subForms"])
    quality_warning = assess_quality(schema_obj.model_dump()["subForms"], schema_obj.model_dump()["documentBlocks"])
    if legacy_note:
        quality_warning = f"{quality_warning}；{legacy_note}" if quality_warning else legacy_note
    prototype_html = None
    if include_prototype:
        prototype_html = build_prototype_html(
            schema_obj.templateName,
            normalized_filename,
            tables,
            schema_obj.model_dump()["subForms"],
            blocks=blocks,
            ai_hints=document_hints,
        )

    result = ParseResult(
        templateId=template_id,
        templateName=schema_obj.templateName,
        sourceFile=normalized_filename,
        schemaPayload=schema_obj.model_dump(),
        ddl=ddl,
        reviewNeeded=review_needed,   # 始终要求人工确认后再写入生产库
        analysisMode=analysis_mode,
        storageTableCount=count_storage_tables(schema_obj.model_dump()["subForms"]),
        qualityWarning=quality_warning,
        structureFingerprint=structure_fingerprint,
        sourceSha256=source_sha256,
        prototypeHtml=prototype_html,
    )
    _store_cached_response(cache_key, 200, result.model_dump(by_alias=True))
    return result
