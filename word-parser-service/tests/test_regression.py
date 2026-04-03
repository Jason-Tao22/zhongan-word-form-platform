from __future__ import annotations

import json
import unittest
from pathlib import Path

from ddl_generator import generate_ddl
from legacy_doc_html import parse_legacy_doc_html_blocks
from legacy_doc_fallback import build_pseudo_tables_from_legacy_text
from legacy_field_codes import strip_legacy_field_codes
from models import FormSchema
from openai_block_hints import _collect_candidates
from post_processor import fill_field_sql, normalize_sub_form, post_process
from prototype_builder import (
    InlineFieldBindingState,
    _build_auto_control_payload,
    _build_inline_fill_tokens,
    build_document_blocks,
    build_prototype_html,
)
from quality_assessor import assess_quality
from storage_plan import apply_storage_plan, count_storage_tables
from legacy_strategy import choose_legacy_representation
from word_parser import ParsedCell, ParsedParagraph, ParsedTable, parse_docx_blocks, tables_to_prompt_text


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
RAW_OUTPUT_JSON = WORKSPACE_ROOT / "test_output.json"
PUBLIC_DEMO_DOCX = WORKSPACE_ROOT / "samples" / "public-demo-template.docx"


class RegressionPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw_payload = json.loads(RAW_OUTPUT_JSON.read_text(encoding="utf-8"))
        cls.processed = apply_storage_plan("80.02工业管道年度检查报告", post_process(raw_payload, []))
        cls.schema = FormSchema(
            templateId="test-template",
            templateName="80.02工业管道年度检查报告",
            sourceFile="public-demo-template.docx",
            createdAt="2026-03-08T00:00:00Z",
            subForms=cls.processed,
        )
        cls.schema_dict = cls.schema.model_dump()

    def test_full_schema_validates(self) -> None:
        self.assertEqual(len(self.schema.subForms), 14)
        self.assertEqual(self.schema.subForms[0].layout.type, "key-value")

    def test_document_blocks_carry_width_align_and_emphasis_styles(self) -> None:
        table = ParsedTable(
            index=0,
            rows=[
                [
                    ParsedCell(
                        text="标题",
                        row=0,
                        col=0,
                        width_twips=3600,
                        align="center",
                        shading="D9D9D9",
                        is_bold=True,
                        font_size_px=18,
                        font_family="SimSun",
                        paragraphs=["标题"],
                    )
                ]
            ],
        )
        document_blocks = build_document_blocks([table], [], blocks=[{"kind": "table", "table": table}])
        cell = document_blocks[0]["rows"][0][0]
        self.assertIn("style", cell)
        self.assertGreater(cell["style"]["widthPx"], 0)
        self.assertEqual(cell["style"]["textAlign"], "center")
        self.assertEqual(cell["style"]["backgroundColor"], "#D9D9D9")
        self.assertEqual(cell["style"]["fontSizePx"], 18)
        self.assertEqual(cell["style"]["fontFamily"], "SimSun")
        self.assertTrue(cell["isEmphasis"])

    def test_document_blocks_carry_paragraph_font_styles(self) -> None:
        paragraph = ParsedParagraph(
            text="检验意见通知书",
            index=0,
            align="center",
            is_bold=True,
            font_size_px=24,
            font_family="KaiTi",
        )
        document_blocks = build_document_blocks([], [], blocks=[{"kind": "paragraph", "paragraph": paragraph}])
        block = document_blocks[0]
        self.assertEqual(block["style"]["fontSizePx"], 24)
        self.assertEqual(block["style"]["fontFamily"], "KaiTi")
        self.assertEqual(block["style"]["fontWeight"], "bold")

    def test_parse_docx_blocks_reads_default_typography_from_styles(self) -> None:
        blocks = parse_docx_blocks(PUBLIC_DEMO_DOCX.read_bytes())
        paragraph = next(block["paragraph"] for block in blocks if block["kind"] == "paragraph")
        self.assertIsNotNone(paragraph.font_size_px)
        self.assertGreater(paragraph.font_size_px, 0)

    def test_section_group_fallback_layout_exists(self) -> None:
        sketch_form = next(
            sub_form for sub_form in self.schema_dict["subForms"]
            if sub_form["id"] == "pipe_thickness_measurement_sketch"
        )
        self.assertEqual(sketch_form["layout"]["type"], "section-group")
        self.assertTrue(sketch_form["layout"]["sections"])
        self.assertTrue(sketch_form["layout"]["sections"][0]["rows"])

    def test_generated_ddl_contains_submission_and_sub_tables(self) -> None:
        ddl = generate_ddl(self.schema_dict["subForms"])
        self.assertIn("CREATE TABLE IF NOT EXISTS t_form_submission", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS t_insp__80_02_main", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS t_insp_pipeline_basic_info", ddl)

    def test_interactive_html_contains_controls(self) -> None:
        table = ParsedTable(
            index=0,
            rows=[
                [
                    ParsedCell(
                        text="问题和意见：",
                        row=0,
                        col=0,
                        colspan=3,
                        width_twips=7600,
                        paragraphs=["问题和意见：", "", "", ""],
                    )
                ]
            ],
        )

        html = build_prototype_html("公开演示模板", "public-demo-template.docx", [table], [])
        self.assertIn("saveDraft()", html)
        self.assertIn("data-key=", html)
        self.assertIn("prototype-textarea", html)

    def test_interactive_html_includes_structured_binding_attributes_for_inline_tokens(self) -> None:
        table = ParsedTable(
            index=0,
            rows=[
                [
                    ParsedCell(
                        text="检验人员：       日期：",
                        row=0,
                        col=0,
                        paragraphs=["检验人员：       日期："],
                    )
                ]
            ],
        )
        sub_form = {
            "id": "signoff",
            "name": "签字区",
            "sqlTableName": "t_insp_signoff",
            "recordType": "single",
            "layout": {"type": "key-value", "rows": []},
            "fields": [
                {"id": "inspector", "label": "检验人员", "type": "text"},
                {"id": "inspection_date", "label": "检验人员日期", "type": "date"},
            ],
        }

        html = build_prototype_html("签字区", "signoff.docx", [table], [sub_form])
        self.assertIn('data-field-id="inspector"', html)
        self.assertIn('data-field-id="inspection_date"', html)

    def test_inline_fill_detects_trailing_short_labels(self) -> None:
        tokens, count = _build_inline_fill_tokens("使用单位代表：       日期： ", "doc::test")
        inline_tokens = [token for token in tokens if token["kind"] == "inline-input"]
        self.assertEqual(count, 2)
        self.assertEqual(len(inline_tokens), 2)

    def test_document_blocks_bind_inline_fill_tokens_to_structured_fields(self) -> None:
        table = ParsedTable(
            index=0,
            rows=[
                [
                    ParsedCell(
                        text="使用单位代表：       日期： ",
                        row=0,
                        col=0,
                        paragraphs=["使用单位代表：       日期： "],
                    )
                ]
            ],
        )
        sub_form = {
            "id": "signoff",
            "name": "签字区",
            "sqlTableName": "t_insp_signoff",
            "recordType": "single",
            "layout": {"type": "key-value", "rows": []},
            "fields": [
                {"id": "company_rep", "label": "使用单位代表", "type": "text"},
                {"id": "signed_on", "label": "日期", "type": "date"},
            ],
        }

        document_blocks = build_document_blocks([table], [sub_form])
        tokens = document_blocks[0]["rows"][0][0]["paragraphs"][0]["tokens"]
        interactive_tokens = [token for token in tokens if token["kind"] == "inline-input"]
        self.assertEqual([token.get("fieldId") for token in interactive_tokens], ["company_rep", "signed_on"])
        self.assertTrue(all(token.get("subFormId") == "signoff" for token in interactive_tokens))

    def test_document_blocks_match_contextual_date_field_over_generic_day_field(self) -> None:
        table = ParsedTable(
            index=0,
            rows=[
                [
                    ParsedCell(
                        text="使用单位接收人：       日期： ",
                        row=0,
                        col=0,
                        paragraphs=["使用单位接收人：       日期： "],
                    )
                ]
            ],
        )
        sub_form = {
            "id": "receipt",
            "name": "接收信息",
            "sqlTableName": "t_insp_receipt",
            "recordType": "single",
            "layout": {"type": "key-value", "rows": []},
            "fields": [
                {"id": "seal_day", "label": "日", "type": "date"},
                {"id": "receiver", "label": "使用单位接收人", "type": "text"},
                {"id": "receiver_date", "label": "使用单位接收人日期", "type": "date"},
            ],
        }

        document_blocks = build_document_blocks([table], [sub_form])
        tokens = document_blocks[0]["rows"][0][0]["paragraphs"][0]["tokens"]
        interactive_tokens = [token for token in tokens if token["kind"] == "inline-input"]
        self.assertEqual([token.get("fieldId") for token in interactive_tokens], ["receiver", "receiver_date"])

    def test_document_blocks_reset_context_between_paragraphs(self) -> None:
        table = ParsedTable(
            index=0,
            rows=[
                [
                    ParsedCell(
                        text="处理结果：\n使用单位安全管理负责人：       日期：",
                        row=0,
                        col=0,
                        paragraphs=[
                            "处理结果：       ",
                            "使用单位安全管理负责人：       日期：",
                        ],
                    )
                ]
            ],
        )
        sub_form = {
            "id": "post_disposal",
            "name": "处理后签收",
            "sqlTableName": "t_insp_post_disposal",
            "recordType": "single",
            "layout": {"type": "key-value", "rows": []},
            "fields": [
                {"id": "disposal_result", "label": "处理结果", "type": "textarea"},
                {"id": "disposal_result_date", "label": "处理结果日期", "type": "date"},
                {"id": "safety_leader", "label": "使用单位安全管理负责人", "type": "text"},
                {"id": "safety_leader_date", "label": "使用单位安全管理负责人日期", "type": "date"},
            ],
        }

        document_blocks = build_document_blocks([table], [sub_form])
        second_paragraph_tokens = document_blocks[0]["rows"][0][0]["paragraphs"][1]["tokens"]
        interactive_tokens = [token for token in second_paragraph_tokens if token["kind"] == "inline-input"]
        self.assertEqual([token.get("fieldId") for token in interactive_tokens], ["safety_leader", "safety_leader_date"])

    def test_inline_fill_does_not_convert_description_label_to_single_input(self) -> None:
        tokens, count = _build_inline_fill_tokens("有关情况说明：", "doc::test")
        self.assertEqual(count, 0)
        self.assertEqual(tokens, [{"kind": "text", "text": "有关情况说明："}])

    def test_inline_fill_detects_underline_runs(self) -> None:
        tokens, count = _build_inline_fill_tokens("整改完成时间: ____年__月__日前完成", "doc::test")
        inline_tokens = [token for token in tokens if token["kind"] == "inline-input"]
        self.assertGreaterEqual(count, 1)
        self.assertTrue(inline_tokens)

    def test_inline_choice_detects_checkbox_style_options(self) -> None:
        tokens, count = _build_inline_fill_tokens("检验结论：□合格 □整改 □不合格", "doc::test")
        choice_tokens = [token for token in tokens if token["kind"] == "inline-choice"]
        self.assertEqual(count, 1)
        self.assertEqual(len(choice_tokens), 1)
        self.assertEqual(choice_tokens[0]["options"], ["合格", "整改", "不合格"])

    def test_inline_choice_binds_to_matching_structured_field(self) -> None:
        binding_state = InlineFieldBindingState(
            sub_form_id="inspection_result",
            available_fields=[
                {
                    "id": "conclusion",
                    "label": "检验结论",
                    "type": "radio",
                    "options": ["合格", "整改", "不合格"],
                }
            ],
        )
        tokens, count = _build_inline_fill_tokens(
            "检验结论：□合格 □整改 □不合格",
            "doc::test",
            inline_binding_state=binding_state,
        )
        choice_tokens = [token for token in tokens if token["kind"] == "inline-choice"]
        self.assertEqual(count, 1)
        self.assertEqual(choice_tokens[0].get("fieldId"), "conclusion")
        self.assertEqual(choice_tokens[0].get("subFormId"), "inspection_result")

    def test_inline_choice_allows_blank_fill_between_options(self) -> None:
        tokens, count = _build_inline_fill_tokens("整改方式：□现场确认 ____ □资料确认", "doc::test")
        choice_tokens = [token for token in tokens if token["kind"] == "inline-choice"]
        self.assertEqual(count, 1)
        self.assertEqual(len(choice_tokens), 1)
        self.assertEqual(choice_tokens[0]["options"], ["现场确认", "资料确认"])

    def test_inline_choice_detects_circle_style_options(self) -> None:
        tokens, count = _build_inline_fill_tokens("流动作业(○是 ○否)", "doc::test")
        choice_tokens = [token for token in tokens if token["kind"] == "inline-choice"]
        self.assertEqual(count, 1)
        self.assertEqual(len(choice_tokens), 1)
        self.assertEqual(choice_tokens[0]["options"], ["是", "否"])
        self.assertEqual(choice_tokens[0]["choiceType"], "radio")

    def test_large_statement_cell_gets_tall_textarea(self) -> None:
        table = ParsedTable(
            index=5,
            rows=[
                [
                    ParsedCell(
                        text="问题和意见：",
                        row=12,
                        col=0,
                        colspan=3,
                        width_twips=7600,
                        paragraphs=["问题和意见：", "", "", ""],
                    )
                ]
            ],
        )
        control = _build_auto_control_payload(table, 12, 0, table.rows[0][0], table.rows[0][0].paragraphs)
        self.assertEqual(control["fieldType"], "textarea")
        self.assertGreaterEqual(control["minHeightPx"], 160)

    def test_ai_hint_can_override_choice_type(self) -> None:
        hint = {
            "classification": "inline-choice",
            "choiceType": "checkbox_group",
            "prefixText": "整改方式：",
            "options": ["现场确认", "资料确认"],
        }
        tokens, count = _build_inline_fill_tokens("整改方式：□现场确认 □资料确认", "doc::test", hint)
        choice_tokens = [token for token in tokens if token["kind"] == "inline-choice"]
        self.assertEqual(count, 1)
        self.assertEqual(choice_tokens[0]["choiceType"], "checkbox_group")

    def test_parse_legacy_doc_html_blocks_builds_tables_from_synthetic_html(self) -> None:
        html_text = (
            "<html><body>"
            "<p style='text-align:center'>公开演示模板</p>"
            "<table><tr><td style='width:120px'>字段</td><td>值</td></tr><tr><td>问题和意见</td><td></td></tr></table>"
            "</body></html>"
        )
        legacy_blocks = parse_legacy_doc_html_blocks(html_text)
        legacy_html_tables = [block["table"] for block in legacy_blocks if block["kind"] == "table"]
        self.assertTrue(legacy_html_tables)
        self.assertTrue(any(block["kind"] == "paragraph" for block in legacy_blocks))
        legacy_document_blocks = build_document_blocks(legacy_html_tables, [], blocks=legacy_blocks)
        first_table_block = next(block for block in legacy_document_blocks if block["kind"] == "table")
        first_table_cell_style = first_table_block["rows"][0][0]["style"]
        self.assertIn("widthPx", first_table_cell_style)
        self.assertGreater(first_table_cell_style["widthPx"], 0)

    def test_build_pseudo_tables_from_legacy_text(self) -> None:
        legacy_text = (
            "公开演示报告\n"
            "整改方式： DOCVARIABLE zgfs \\\\* MERGEFORMAT\n"
            "说明信息\n"
            "使用单位代表\n"
            "张三\n"
        )
        pseudo_tables = build_pseudo_tables_from_legacy_text(legacy_text)
        document_blocks = build_document_blocks(pseudo_tables, [], blocks=None)

        self.assertTrue(pseudo_tables)
        self.assertTrue(document_blocks)
        self.assertEqual(document_blocks[0]["kind"], "table")

    def test_prompt_text_compresses_repeated_blank_rows(self) -> None:
        table = ParsedTable(
            index=0,
            rows=[
                [ParsedCell(text="标题", row=0, col=0), ParsedCell(text="值", row=0, col=1)],
                [ParsedCell(text="", row=1, col=0), ParsedCell(text="", row=1, col=1)],
                [ParsedCell(text="", row=2, col=0), ParsedCell(text="", row=2, col=1)],
                [ParsedCell(text="", row=3, col=0), ParsedCell(text="", row=3, col=1)],
            ],
        )
        prompt = tables_to_prompt_text([table])
        self.assertIn("Rows 2-4:", prompt)

    def test_openai_block_hints_keeps_more_than_one_batch_of_candidates(self) -> None:
        blocks = []
        for index in range(30):
            blocks.append({
                "kind": "table",
                "table": ParsedTable(
                    index=index,
                    rows=[
                        [
                            ParsedCell(
                                text="问题和意见：",
                                row=0,
                                col=0,
                                colspan=2,
                                paragraphs=["问题和意见：", "", ""],
                                width_twips=4200,
                            )
                        ]
                    ],
                ),
            })

        candidates = _collect_candidates(blocks)
        self.assertGreaterEqual(len(candidates), 30)

    def test_post_process_rebuilds_invalid_section_group_rows(self) -> None:
        table = ParsedTable(
            index=0,
            rows=[
                [ParsedCell(text="检测参数", row=0, col=0, colspan=4)],
                [
                    ParsedCell(text="检测仪器型号", row=1, col=0),
                    ParsedCell(text="", row=1, col=1),
                    ParsedCell(text="检测仪器编号", row=1, col=2),
                    ParsedCell(text="", row=1, col=3),
                ],
            ],
        )
        raw_sub_form = {
            "id": "ultra_sound",
            "name": "超声检测",
            "sqlTableName": "t_insp_ultra_sound",
            "recordType": "single",
            "layout": {
                "type": "section-group",
                "sections": [
                    {
                        "title": "检测参数",
                        "rows": [["检测仪器型号", "检测仪器编号"], 4],
                    }
                ],
            },
            "fields": [
                {"id": "device_model", "label": "检测仪器型号", "type": "text"},
                {"id": "device_code", "label": "检测仪器编号", "type": "text"},
            ],
        }

        processed = post_process([raw_sub_form], [table])
        section_rows = processed[0]["layout"]["sections"][0]["rows"]
        self.assertIsInstance(section_rows, list)
        self.assertIsInstance(section_rows[0], list)

    def test_storage_plan_groups_multiple_single_subforms_into_one_main_table(self) -> None:
        planned = apply_storage_plan("complex-report", [
            {
                "id": "cover",
                "name": "封面",
                "sqlTableName": "t_insp_cover",
                "recordType": "single",
                "layout": {"type": "key-value", "rows": []},
                "fields": [{"id": "report_no", "label": "报告编号", "type": "text", "sqlColumn": "report_no"}],
            },
            {
                "id": "base",
                "name": "基本信息",
                "sqlTableName": "t_insp_base",
                "recordType": "single",
                "layout": {"type": "key-value", "rows": []},
                "fields": [{"id": "report_no", "label": "报告编号", "type": "text", "sqlColumn": "report_no"}],
            },
            {
                "id": "items",
                "name": "明细",
                "sqlTableName": "t_insp_items",
                "recordType": "multi",
                "layout": {"type": "data-grid", "headers": [], "dataColumns": ["item_name"]},
                "fields": [{"id": "item_name", "label": "项目", "type": "text", "sqlColumn": "item_name"}],
            },
        ])

        self.assertEqual(planned[0]["storageTableName"], "t_insp_complex_report_main")
        self.assertEqual(planned[1]["storageTableName"], "t_insp_complex_report_main")
        self.assertEqual(planned[2]["storageTableName"], "t_insp_items")
        self.assertEqual(count_storage_tables(planned), 2)
        self.assertNotEqual(
            planned[0]["fields"][0]["storageColumn"],
            planned[1]["fields"][0]["storageColumn"],
        )

        ddl = generate_ddl(planned)
        self.assertIn("CREATE TABLE IF NOT EXISTS t_insp_complex_report_main", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS t_insp_items", ddl)
        self.assertEqual(ddl.count("CREATE TABLE IF NOT EXISTS t_insp_"), 2)

    def test_fill_field_sql_rewrites_generic_field_ids_from_labels(self) -> None:
        fields = fill_field_sql([
            {"id": "field_10", "label": "使用单位接收人", "type": "text"},
            {"id": "field_11", "label": "使用单位接收人日期", "type": "date"},
        ])
        self.assertNotEqual(fields[0]["id"], "field_10")
        self.assertNotEqual(fields[1]["id"], "field_11")
        self.assertEqual(fields[0]["sqlColumn"], fields[0]["id"])
        self.assertEqual(fields[1]["sqlColumn"], fields[1]["id"])
        self.assertNotRegex(fields[0]["id"], r"^field_\d+$")
        self.assertNotRegex(fields[1]["id"], r"^field_\d+$")

    def test_normalize_sub_form_rewrites_generic_subform_id_from_name(self) -> None:
        sub_form = normalize_sub_form({
            "id": "sub_form_1",
            "name": "问题和意见与签字信息",
            "layout": {"type": "key-value"},
            "fields": [],
        }, 0)
        self.assertNotEqual(sub_form["id"], "sub_form_1")
        self.assertTrue(sub_form["sqlTableName"].startswith("t_insp_"))

    def test_legacy_strategy_prefers_text_when_html_is_too_fragmented(self) -> None:
        html_tables = [
            ParsedTable(index=i, rows=[[ParsedCell(text="标题", row=0, col=0)]])
            for i in range(50)
        ]
        html_blocks = [{"kind": "table", "table": table} for table in html_tables]
        text_tables = [
            ParsedTable(index=i, rows=[[ParsedCell(text="章节", row=0, col=0)], [ParsedCell(text="内容", row=1, col=0)]])
            for i in range(20)
        ]

        selection = choose_legacy_representation(html_blocks, html_tables, text_tables)
        self.assertEqual(selection.mode, "text")
        self.assertIsNone(selection.blocks)
        self.assertEqual(len(selection.tables), 20)

    def test_legacy_strategy_keeps_html_when_many_tables_are_not_fragmented(self) -> None:
        html_tables = [
            ParsedTable(
                index=i,
                rows=[[ParsedCell(text=f"标题{i}", row=0, col=0), ParsedCell(text="值", row=0, col=1)]]
                + [[ParsedCell(text=f"字段{row}", row=row, col=0), ParsedCell(text="", row=row, col=1)] for row in range(1, 8)],
            )
            for i in range(45)
        ]
        html_blocks = [{"kind": "table", "table": table} for table in html_tables]
        text_tables = [
            ParsedTable(index=i, rows=[[ParsedCell(text="章节", row=0, col=0)], [ParsedCell(text="内容", row=1, col=0)]])
            for i in range(20)
        ]

        selection = choose_legacy_representation(html_blocks, html_tables, text_tables)
        self.assertEqual(selection.mode, "html")
        self.assertEqual(len(selection.tables), 45)
        self.assertIsNotNone(selection.blocks)

    def test_parse_legacy_doc_html_blocks_tolerates_null_bytes(self) -> None:
        html_text = (
            "<html><head><title>\x00\x00</title></head><body>"
            "<p class='p1'>标题</p>"
            "<table><tr><td>字段</td><td>值</td></tr></table>"
            "</body></html>"
        )
        blocks = parse_legacy_doc_html_blocks(html_text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["kind"], "paragraph")
        self.assertEqual(blocks[1]["kind"], "table")

    def test_strip_legacy_field_codes_removes_docvariable_and_page_codes(self) -> None:
        cleaned = strip_legacy_field_codes(
            "报告编号： DOCVARIABLE baogbh \\* MERGEFORMAT 第 PAGE \\* MERGEFORMAT 3 页"
        )
        self.assertEqual(cleaned, "报告编号： 第 3 页")

    def test_parse_legacy_doc_html_blocks_filters_word_field_codes(self) -> None:
        html_text = (
            "<html><body>"
            "<p>报告编号： DOCVARIABLE baogbh \\* MERGEFORMAT</p>"
            "<p>第 PAGE \\* MERGEFORMAT 3 页 共 NUMPAGES \\* MERGEFORMAT 73 页</p>"
            "</body></html>"
        )
        blocks = parse_legacy_doc_html_blocks(html_text)
        self.assertEqual(blocks[0]["paragraph"].text, "报告编号：")
        self.assertEqual(blocks[1]["paragraph"].text, "第 3 页 共 73 页")

    def test_post_process_normalizes_checklist_columns(self) -> None:
        raw_sub_form = {
            "id": "check_form",
            "name": "检查表",
            "sqlTableName": "t_insp_check_form",
            "recordType": "single",
            "layout": {
                "type": "checklist",
                "columns": [
                    {"label": "序号", "name": "xuhao"},
                    {"label": "检验项目", "name": "xiangmu"},
                    {"label": "检查结果", "name": "jieguo"},
                    {"label": "备注", "name": "beizhu"},
                ],
                "items": [{"seq": "1", "label": "项目", "fieldId": "result"}],
            },
            "fields": [
                {"id": "result", "label": "检查结果", "type": "text"},
            ],
        }

        processed = post_process([raw_sub_form], [])
        self.assertEqual(processed[0]["layout"]["columns"], ["序号", "检验项目", "检查结果", "备注"])

    def test_post_process_coerces_non_dict_subforms_and_fields(self) -> None:
        processed = post_process(
            [
                "封面说明",
                {
                    "name": "正文",
                    "layout": {"type": "static"},
                    "fields": ["备注内容", {"id": "report_no", "label": "报告编号", "type": "text"}],
                },
            ],
            [],
        )

        self.assertEqual(processed[0]["layout"]["type"], "key-value")
        self.assertEqual(processed[0]["fields"], [])
        self.assertEqual(processed[1]["layout"]["type"], "key-value")
        self.assertEqual(processed[1]["fields"][0]["type"], "static")
        self.assertEqual(processed[1]["fields"][1]["id"], "report_no")

    def test_quality_assessor_flags_over_fragmented_page_blocks(self) -> None:
        sub_forms = [
            {
                "id": f"sub_{index}",
                "recordType": "single",
                "fields": [{"id": f"field_{index}", "type": "text"}],
            }
            for index in range(61)
        ]

        warning = assess_quality(sub_forms, [])
        self.assertEqual(warning, "页面块过碎：61")

    def test_quality_assessor_does_not_flag_high_subform_count_when_document_blocks_exist_and_storage_is_compact(self) -> None:
        sub_forms = [
            {
                "id": f"sub_{index}",
                "recordType": "single",
                "storageTableName": "t_insp_main",
                "fields": [
                    {"id": f"field_{index}", "type": "text"},
                    {"id": f"field_{index}_2", "type": "text"},
                ],
            }
            for index in range(68)
        ]
        document_blocks = [{"kind": "paragraph", "text": f"段落{index}"} for index in range(120)]

        warning = assess_quality(sub_forms, document_blocks)
        self.assertIsNone(warning)

    def test_quality_assessor_flags_semantic_fragments_when_blocks_and_storage_are_both_too_high(self) -> None:
        sub_forms = [
            {
                "id": f"sub_{index}",
                "recordType": "single",
                "storageTableName": f"t_insp_part_{index}",
                "fields": [{"id": f"field_{index}", "type": "text"}],
            }
            for index in range(91)
        ]
        document_blocks = [{"kind": "table", "rows": []} for _ in range(120)]

        warning = assess_quality(sub_forms, document_blocks)
        self.assertEqual(warning, "语义块过碎：91 / 存储表 91")


if __name__ == "__main__":
    unittest.main()
