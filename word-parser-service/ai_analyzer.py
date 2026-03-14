"""
AI 分析模块
- 把解析出的表格文本发给 Claude
- 要求返回符合 schema-format.json 格式的 JSON
"""
from __future__ import annotations
import json
import anthropic

SYSTEM_PROMPT = """你是一个专业的表单分析专家。
你会收到从 Word 文档中提取的表格文本（含合并单元格信息 [cs=colspan] [rs=rowspan]）。
你需要分析每张子表的结构，输出一个 JSON 数组，每个元素对应一张子表（subForm）。

## 输出格式规则

每个 subForm 包含：
- id: snake_case 英文标识符
- name: 中文名称
- sqlTableName: "t_insp_" 前缀的蛇形命名
- recordType: "single"（整张表一条记录）或 "multi"（有多行数据，每行一条记录）
- layout: 布局对象（见下）
- fields: 字段数组（见下）

## layout.type 选择规则
- "key-value": 左列是标签，右列是输入框，整体是键值对形式
- "data-grid": 有明确的表头行 + 多行数据录入区（如测量数据表）
- "checklist": 逐条检查项列表，每行有检查项目和检查结果
- "section-group": 多个分块，每块有标题行和若干字段

## field.type 选择规则
- "text": 普通单行文本
- "number": 数字（含单位如 MPa ℃ mm）
- "textarea": 多行文本（自由填写区域）
- "date": 含"年月日"的日期字段
- "radio": 含 □ 符号的单选（□符合要求 □基本符合要求）
- "select": 含 A. B. C. 的选项列表
- "static": 固定文字，不需要填写（如签名区说明文字、表头标注）

## 注意事项
1. 签名行（"检查：年月日"、"审核："等）识别为 static，不生成字段
2. □ 开头的选项识别为 radio，options 去掉 □ 符号
3. A.xxx;B.xxx 格式识别为 select，options 保留选项文字
4. 含数字测量数据的大网格表识别为 data-grid + recordType=multi
5. 只输出 JSON 数组，不要任何解释文字
"""

USER_PROMPT_TEMPLATE = """以下是从 Word 文档"{filename}"中提取的表格内容，请分析并输出 subForms JSON 数组：

{table_text}
"""


BATCH_SIZE = 4   # 每批处理的表格数量，避免输出截断


def _parse_raw(raw: str) -> list[dict]:
    """解析 AI 返回的原始文本为 JSON 列表"""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()
    return json.loads(raw)


def _analyze_batch(table_text: str, filename: str, client) -> list[dict]:
    """分析一批表格"""
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    filename=filename,
                    table_text=table_text,
                )
            }
        ]
    )
    return _parse_raw(message.content[0].text)


def analyze_tables(table_text: str, filename: str, api_key: str) -> list[dict]:
    """
    调用 Claude API 分析表格，返回 subForms 列表。
    按 BATCH_SIZE 分批发送，避免输出过长被截断。
    """
    client = anthropic.Anthropic(api_key=api_key)

    # 按 === Table N === 分割各表
    import re
    sections = re.split(r'(?=\n=== Table \d+)', table_text)
    sections = [s.strip() for s in sections if s.strip()]

    all_sub_forms: list[dict] = []

    for i in range(0, len(sections), BATCH_SIZE):
        batch = sections[i:i + BATCH_SIZE]
        batch_text = "\n".join(batch)
        print(f"   批次 {i // BATCH_SIZE + 1}/{(len(sections) + BATCH_SIZE - 1) // BATCH_SIZE}"
              f"（表格 {i + 1}~{min(i + BATCH_SIZE, len(sections))}）")
        sub_forms = _analyze_batch(batch_text, filename, client)
        all_sub_forms.extend(sub_forms)

    return all_sub_forms
