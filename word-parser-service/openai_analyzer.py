"""
OpenAI 分析模块
- 把解析出的表格文本发给 OpenAI
- 要求返回 subForms JSON
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import re

from openai import OpenAI

SYSTEM_PROMPT = """你是一个专业的表单分析专家。
你会收到从 Word 文档中提取的表格文本（含合并单元格信息 [cs=colspan] [rs=rowspan]）。
你需要分析每张子表的结构，输出一个 JSON 对象，格式必须是 {"subForms": [...]}。

## subForm 输出规则

每个 subForm 包含：
- id: snake_case 英文标识符
- name: 中文名称
- sqlTableName: "t_insp_" 前缀的蛇形命名
- recordType: "single"（整张表一条记录）或 "multi"（有多行数据，每行一条记录）
- layout: 布局对象（见下）
- fields: 字段数组（见下）

## layout.type 选择规则
- "key-value": 左列是标签，右列是输入框，整体是键值对形式
- "data-grid": 有明确的表头行 + 多行数据录入区
- "checklist": 逐条检查项列表，每行有检查项目和检查结果
- "section-group": 多个分块，每块有标题行和若干字段

## field.type 选择规则
- "text": 普通单行文本
- "number": 数字（含单位如 MPa ℃ mm）
- "textarea": 多行文本（自由填写区域）
- "date": 含"年月日"的日期字段
- "radio": 含 □ 符号的单选
- "select": 含 A. B. C. 的选项列表
- "static": 固定文字，不需要填写

## 注意事项
1. 签名行说明文字如果本身不是填写位，识别为 static
2. □ 开头的选项识别为 radio，options 去掉 □
3. A.xxx;B.xxx 格式识别为 select
4. 含表头 + 多行数据的表格识别为 data-grid + multi
5. 大块空白说明区识别为 textarea
6. 只输出 JSON 对象，不要解释文字，不要 markdown 代码块
"""

USER_PROMPT_TEMPLATE = """以下是从 Word 文档"{filename}"中提取的表格内容，请分析并输出 json 对象 {{"subForms": [...]}}：

{table_text}
"""

BATCH_SIZE = 8
DEFAULT_MODEL = "gpt-5"

def _parse_raw(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    payload = json.loads(raw)
    if isinstance(payload, dict) and "subForms" in payload:
        return payload["subForms"]
    if isinstance(payload, list):
        return payload
    raise ValueError("OpenAI 返回格式不是 subForms JSON")


def _extract_output_text(response) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text

    output = getattr(response, "output", None) or []
    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or []
        for chunk in content:
            chunk_text = getattr(chunk, "text", None)
            if chunk_text:
                parts.append(chunk_text)
    return "".join(parts).strip()


def _analyze_batch(table_text: str, filename: str, api_key: str, model: str) -> list[dict]:
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=USER_PROMPT_TEMPLATE.format(
            filename=filename,
            table_text=table_text,
        ),
        max_output_tokens=8000,
        reasoning={"effort": "minimal"},
        text={
            "format": {"type": "json_object"},
            "verbosity": "low",
        },
    )
    return _parse_raw(_extract_output_text(response))


def analyze_tables_with_openai(
    table_text: str,
    filename: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    sections = re.split(r"(?=\n=== Table \d+)", table_text)
    sections = [section.strip() for section in sections if section.strip()]
    if not sections:
        return []

    batches = [
        "\n".join(sections[i:i + BATCH_SIZE])
        for i in range(0, len(sections), BATCH_SIZE)
    ]
    ordered_results: list[list[dict] | None] = [None] * len(batches)
    max_workers = min(4, len(batches))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_analyze_batch, batch_text, filename, api_key, model): index
            for index, batch_text in enumerate(batches)
        }
        for future, index in futures.items():
            ordered_results[index] = future.result()

    all_sub_forms: list[dict] = []
    for sub_forms in ordered_results:
        if sub_forms:
            all_sub_forms.extend(sub_forms)
    return all_sub_forms
