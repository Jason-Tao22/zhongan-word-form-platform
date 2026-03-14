from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

BOX_OR_CIRCLE_RE = re.compile(r"[□☐☑■○◯●〇]")

SYSTEM_PROMPT = """你是 Word 表单控件分类助手。
系统已经可靠地提取了 Word 的表格结构，你的任务不是重建整份 schema，而是只判断“歧义块”更适合渲染成什么控件。

返回 JSON 对象，格式必须是：
{
  "paragraphHints": [
    {
      "candidateId": "...",
      "classification": "inline-choice" | "static",
      "choiceType": "radio" | "checkbox_group",
      "prefixText": "可选，保留在控件前面的文字",
      "options": ["选项1", "选项2"],
      "suffixText": "可选，保留在控件后面的文字"
    }
  ],
  "cellHints": [
    {
      "candidateId": "...",
      "fieldType": "textarea" | "text" | "none",
      "minHeightPx": 160
    }
  ]
}

规则：
1. 只给出你有把握的候选项；没把握就不要输出该 candidate。
2. “问题和意见”“有关情况说明”“备注”“整改情况”等大块填写区优先判为 textarea。
3. 连续的 □ / ○ / ● 选项组识别成 inline-choice。
4. 如果语义明显是二选一或多选一，choiceType 用 radio。
5. 只有明确允许多选时，choiceType 才用 checkbox_group。
6. 不要编造新的字段，也不要改结构顺序。
7. 只输出 JSON，不要 markdown。
"""

USER_PROMPT_TEMPLATE = """请根据这些候选歧义块给出控件建议，并返回 json 对象：

{payload}
"""

BATCH_SIZE = 24
MAX_CANDIDATES = 96


def analyze_block_hints_with_openai(
    blocks: list[dict],
    api_key: str,
    model: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    candidates = _collect_candidates(blocks)
    if not candidates:
        return {"paragraphs": {}, "cells": {}}

    client = OpenAI(api_key=api_key)
    paragraph_hints: dict[str, dict[str, Any]] = {}
    cell_hints: dict[str, dict[str, Any]] = {}

    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start:start + BATCH_SIZE]
        response = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            input=USER_PROMPT_TEMPLATE.format(
                payload=json.dumps({"candidates": batch}, ensure_ascii=False, indent=2),
            ),
            max_output_tokens=6000,
            reasoning={"effort": "minimal"},
            text={"format": {"type": "json_object"}, "verbosity": "low"},
        )
        payload = _parse_response(_extract_output_text(response))
        for hint in payload.get("paragraphHints", []):
            candidate_id = hint.get("candidateId")
            if candidate_id:
                paragraph_hints[candidate_id] = hint
        for hint in payload.get("cellHints", []):
            candidate_id = hint.get("candidateId")
            if candidate_id:
                cell_hints[candidate_id] = hint

    return {"paragraphs": paragraph_hints, "cells": cell_hints}


def _collect_candidates(blocks: list[dict]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for block in blocks:
        if block["kind"] != "table":
            paragraph = block.get("paragraph")
            if paragraph and _looks_like_choice_line(paragraph.text):
                candidates.append({
                    "candidateId": f"doc::paragraph::{paragraph.index}",
                    "candidateType": "paragraph",
                    "text": paragraph.text,
                    "ruleGuess": "choice",
                    "_priority": 3,
                })
            continue

        table = block["table"]
        for row_index, row in enumerate(table.rows):
            visible_cells = [cell for cell in row if not cell.is_merged_continuation]
            for col_index, cell in enumerate(visible_cells):
                paragraphs = cell.paragraphs or ([cell.text] if cell.text else [])
                blank_paragraphs = sum(1 for paragraph in paragraphs if not paragraph.strip())
                width_px = _twips_to_px(cell.width_twips)
                cell_id = f"table::{table.index}::cell::{row_index}::{col_index}"

                if _looks_like_multiline_candidate(cell, paragraphs, blank_paragraphs, width_px):
                    candidates.append({
                        "candidateId": cell_id,
                        "candidateType": "cell",
                        "text": cell.text,
                        "paragraphs": paragraphs,
                        "blankParagraphs": blank_paragraphs,
                        "colspan": cell.colspan,
                        "rowspan": cell.rowspan,
                        "widthPx": width_px,
                        "ruleGuess": "textarea" if blank_paragraphs >= 2 else "text",
                        "_priority": 2 + min(blank_paragraphs, 2),
                    })

                for paragraph_index, paragraph in enumerate(paragraphs):
                    stripped = paragraph.strip()
                    if not stripped or not _looks_like_choice_line(stripped):
                        continue
                    candidates.append({
                        "candidateId": f"{cell_id}::paragraph::{paragraph_index}",
                        "candidateType": "paragraph",
                        "text": stripped,
                        "cellColspan": cell.colspan,
                        "cellRowspan": cell.rowspan,
                        "widthPx": width_px,
                        "ruleGuess": "choice",
                        "_priority": 4 if "整改" in stripped else 3,
                    })

    candidates.sort(key=lambda item: (-item.get("_priority", 0), item["candidateId"]))
    trimmed = candidates[:MAX_CANDIDATES] if MAX_CANDIDATES else candidates
    for candidate in trimmed:
        candidate.pop("_priority", None)
    return trimmed


def _looks_like_multiline_candidate(cell, paragraphs: list[str], blank_paragraphs: int, width_px: int | None) -> bool:
    if not paragraphs:
        return False
    non_empty = [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]
    if len(non_empty) != 1:
        return False
    label = non_empty[0]
    if not label.endswith(("：", ":")):
        return False
    if not any(keyword in label for keyword in ("说明", "意见", "备注", "情况", "结果", "整改")):
        return False
    return blank_paragraphs >= 2 or cell.rowspan > 1 or cell.colspan > 1 or (width_px or 0) >= 220


def _looks_like_choice_line(text: str) -> bool:
    return bool(BOX_OR_CIRCLE_RE.search(text))


def _twips_to_px(value: int | None) -> int | None:
    if value is None:
        return None
    return max(24, round(value / 15))


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


def _parse_response(raw: str) -> dict[str, Any]:
    payload = json.loads(raw.strip())
    return {
        "paragraphHints": payload.get("paragraphHints", []),
        "cellHints": payload.get("cellHints", []),
    }
