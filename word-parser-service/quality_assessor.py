from __future__ import annotations

from storage_plan import count_storage_tables


def assess_quality(sub_forms: list[dict], document_blocks: list[dict]) -> str | None:
    if not sub_forms:
        return "未生成任何页面块"

    storage_table_count = count_storage_tables(sub_forms)

    single_forms = [sub_form for sub_form in sub_forms if sub_form.get("recordType") != "multi"]
    avg_fields = sum(
        len([field for field in sub_form.get("fields", []) if field.get("type") != "static"])
        for sub_form in sub_forms
    ) / max(1, len(sub_forms))

    if document_blocks and len(sub_forms) > 90 and avg_fields < 1.6 and storage_table_count > 10:
        return f"语义块过碎：{len(sub_forms)} / 存储表 {storage_table_count}"

    if storage_table_count > 15:
        return f"存储表偏多：{storage_table_count}"

    if not document_blocks and len(sub_forms) > 60:
        return f"页面块过碎：{len(sub_forms)}"

    if not document_blocks and len(single_forms) >= 20 and avg_fields < 2.2:
        return f"single 块过碎：{len(single_forms)} / 平均字段 {avg_fields:.1f}"

    if len(sub_forms) > max(18, len(document_blocks) * 1.5):
        return f"页面块偏多：{len(sub_forms)}"

    return None
