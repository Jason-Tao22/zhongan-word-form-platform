from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import main as main_module
from openai_analyzer import _parse_raw
from post_processor import post_process


SAMPLE_DOCX = (
    "/Users/yifantao/Documents/ZhongAn/03报告/2 压力容器/"
    "20.05压力容器特种设备定期检验意见通知书（1）.docx"
)


class OpenAIModeTest(unittest.TestCase):
    def test_parse_raw_supports_wrapped_object(self) -> None:
        payload = _parse_raw('{"subForms": [{"id": "demo"}]}')
        self.assertEqual(payload, [{"id": "demo"}])

    def test_config_status_reports_unavailable_without_key(self) -> None:
        client = TestClient(main_module.app)
        with patch.object(main_module, "OPENAI_API_KEY", ""), patch.object(main_module, "ALLOW_HEURISTIC_FALLBACK", False):
            response = client.get("/config-status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["defaultMode"], "unavailable")
        self.assertFalse(response.json()["openaiConfigured"])

    def test_parse_endpoint_requires_openai_key_when_fallback_disabled(self) -> None:
        client = TestClient(main_module.app)
        with open(SAMPLE_DOCX, "rb") as file_handle:
            with patch.object(main_module, "OPENAI_API_KEY", ""), patch.object(main_module, "ALLOW_HEURISTIC_FALLBACK", False):
                response = client.post(
                    "/parse-word",
                    files={"file": ("20.05.docx", file_handle, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                )

        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["detail"])

    def test_post_process_backfills_missing_subform_and_field_ids(self) -> None:
        sub_forms = [{
            "name": "意见通知书",
            "layout": {"type": "key-value", "rows": []},
            "fields": [{"label": "使用单位", "type": "text"}],
        }]

        processed = post_process(sub_forms, [])

        self.assertNotRegex(processed[0]["id"], r"^sub_form_\d+$")
        self.assertTrue(processed[0]["sqlTableName"].startswith("t_insp_"))
        self.assertNotRegex(processed[0]["fields"][0]["id"], r"^field_\d+$")
        self.assertEqual(processed[0]["fields"][0]["sqlColumn"], processed[0]["fields"][0]["id"])

    def test_parse_endpoint_reuses_cached_openai_result_for_same_file(self) -> None:
        client = TestClient(main_module.app)
        raw_sub_forms = [{
            "name": "意见通知书",
            "layout": {"type": "key-value", "rows": []},
            "fields": [{"label": "使用单位", "type": "text"}],
        }]

        with tempfile.TemporaryDirectory() as tmp_dir:
            with open(SAMPLE_DOCX, "rb") as file_handle:
                payload = file_handle.read()

            with patch.object(main_module, "OPENAI_API_KEY", "test-key"), \
                patch.object(main_module, "CACHE_DIR", Path(tmp_dir)), \
                patch.object(main_module, "analyze_tables_with_openai", return_value=raw_sub_forms) as analyze_mock, \
                patch.object(main_module, "analyze_block_hints_with_openai", return_value={"paragraphs": {}, "cells": {}}):
                response_1 = client.post(
                    "/parse-word",
                    files={"file": ("20.05.docx", payload, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                )
                response_2 = client.post(
                    "/parse-word",
                    files={"file": ("20.05.docx", payload, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                )

        self.assertEqual(response_1.status_code, 200)
        self.assertEqual(response_2.status_code, 200)
        self.assertEqual(analyze_mock.call_count, 1)
        self.assertNotEqual(response_1.json()["templateId"], response_2.json()["templateId"])
        self.assertNotEqual(response_1.json()["schema"]["templateId"], response_2.json()["schema"]["templateId"])

    def test_parse_endpoint_reuses_cache_for_same_legacy_upload_when_conversion_bytes_vary(self) -> None:
        client = TestClient(main_module.app)
        raw_sub_forms = [{
            "name": "意见通知书",
            "layout": {"type": "key-value", "rows": []},
            "fields": [{"label": "使用单位", "type": "text"}],
        }]
        processed_sub_forms = post_process(raw_sub_forms, [])
        fake_blocks = [{"kind": "table", "table": [[{"text": "使用单位"}]]}]

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(main_module, "OPENAI_API_KEY", "test-key"), \
                patch.object(main_module, "CACHE_DIR", Path(tmp_dir)), \
                patch.object(main_module, "normalize_word_bytes", side_effect=[
                    ("legacy.docx", b"converted-v1"),
                    ("legacy.docx", b"converted-v2"),
                ]), \
                patch.object(main_module, "parse_docx_blocks", return_value=fake_blocks), \
                patch.object(main_module, "tables_to_prompt_text", return_value="legacy-table"), \
                patch.object(main_module, "post_process", return_value=processed_sub_forms), \
                patch.object(main_module, "build_document_blocks", return_value=[]), \
                patch.object(main_module, "analyze_tables_with_openai", return_value=raw_sub_forms) as analyze_mock, \
                patch.object(main_module, "analyze_block_hints_with_openai", return_value={"paragraphs": {}, "cells": {}}):
                response_1 = client.post(
                    "/parse-word",
                    files={"file": ("legacy.doc", b"legacy-source-bytes", "application/msword")},
                )
                response_2 = client.post(
                    "/parse-word",
                    files={"file": ("legacy.doc", b"legacy-source-bytes", "application/msword")},
                )

        self.assertEqual(response_1.status_code, 200)
        self.assertEqual(response_2.status_code, 200)
        self.assertEqual(analyze_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
