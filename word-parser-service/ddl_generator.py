"""
PostgreSQL DDL 生成模块
直接从 dict 生成，不依赖 Pydantic 验证（兼容 AI 输出的字段名差异）
"""
from __future__ import annotations

VALID_FIELD_TYPES = {"text", "number", "textarea", "date", "radio", "select", "checkbox_group", "static"}

_COMMON_COLUMNS = """
    id              BIGSERIAL PRIMARY KEY,
    submission_id   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()"""

_FK_TEMPLATE = (
    "    CONSTRAINT fk_{table}_submission\n"
    "        FOREIGN KEY (submission_id)\n"
    "        REFERENCES t_form_submission(id) ON DELETE CASCADE"
)


def _field_to_column(f: dict) -> str | None:
    """
    单个字段 dict → SQL 列定义。
    兼容 AI 可能用 'name' 代替 'label'，type 不合法时降级为 text。
    """
    ftype = f.get("type", "text")
    if ftype not in VALID_FIELD_TYPES:
        ftype = "text"

    if ftype == "static":
        return None

    sql_col  = f.get("storageColumn") or f.get("sqlColumn") or f.get("id")
    sql_type = f.get("sqlType", "VARCHAR(200)")

    if not sql_col or not sql_type:
        return None

    return f"    {sql_col:<40} {sql_type}"


def generate_ddl(sub_forms: list[dict]) -> str:
    """
    从 subForms list[dict] 生成完整 DDL。
    接受原始 AI 输出（post_process 之后），不需要 FormSchema 对象。
    """
    blocks: list[str] = []

    blocks.append("""\
-- ============================================================
-- 表单提交主记录（每次用户提交一份表单生成一条记录）
-- ============================================================
CREATE TABLE IF NOT EXISTS t_form_submission (
    id              BIGSERIAL PRIMARY KEY,
    template_id     VARCHAR(64)  NOT NULL,
    template_name   VARCHAR(200),
    submitted_by    VARCHAR(100),
    submitted_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status          VARCHAR(20)  NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'approved', 'rejected'))
);
""")

    storage_groups: dict[str, dict] = {}
    for sub in sub_forms:
        table_name = sub.get("storageTableName") or sub.get("sqlTableName", "t_unknown")
        fields = sub.get("fields", [])
        if not any(field.get("type") != "static" for field in fields):
            continue
        group = storage_groups.setdefault(table_name, {
            "recordType": sub.get("recordType", "single"),
            "names": [],
            "fields": [],
        })
        group["recordType"] = "multi" if sub.get("recordType") == "multi" else group["recordType"]
        group["names"].append(sub.get("name", table_name))
        group["fields"].extend(fields)

    for table_name, group in storage_groups.items():
        columns: list[str] = [_COMMON_COLUMNS]
        seen: set[str] = set()

        for field in group["fields"]:
            col_def = _field_to_column(field)
            if not col_def:
                continue
            col_name = (field.get("storageColumn") or field.get("sqlColumn") or field.get("id", "")).strip()
            if col_name and col_name not in seen:
                columns.append(col_def)
                seen.add(col_name)

        fk = _FK_TEMPLATE.format(table=table_name)
        col_block = ",\n".join(columns)
        sub_name = " / ".join(dict.fromkeys(group["names"]))

        blocks.append(
            f"-- {sub_name}\n"
            f"CREATE TABLE IF NOT EXISTS {table_name} (\n"
            f"{col_block},\n"
            f"{fk}\n"
            f");\n"
        )

        if group["recordType"] == "multi":
            blocks.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_submission_id\n"
                f"    ON {table_name}(submission_id);\n"
            )

    return "\n".join(blocks)
