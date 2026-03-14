package com.zhongan.form.util;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class FormDdlGenerator {
    private static final Set<String> VALID_FIELD_TYPES = Set.of(
        "text", "number", "textarea", "date", "radio", "select", "checkbox_group", "static"
    );

    private static final String COMMON_COLUMNS = """
            id              BIGSERIAL PRIMARY KEY,
            submission_id   BIGINT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()""";
    private final StoragePlanBuilder storagePlanBuilder;

    public FormDdlGenerator(StoragePlanBuilder storagePlanBuilder) {
        this.storagePlanBuilder = storagePlanBuilder;
    }

    public String generate(List<Map<String, Object>> subForms) {
        StringBuilder ddl = new StringBuilder("""
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

            """);

        for (StoragePlanBuilder.StorageTablePlan tablePlan : storagePlanBuilder.build(subForms)) {
            String tableName = tablePlan.tableName();
            String subName = tablePlan.subForms().stream()
                .map(StoragePlanBuilder.SubFormPlan::subFormId)
                .distinct()
                .reduce((left, right) -> left + " / " + right)
                .orElse(tableName);
            StringBuilder columnBlock = new StringBuilder(COMMON_COLUMNS);
            Set<String> seen = new HashSet<>();
            for (StoragePlanBuilder.FieldBinding field : tablePlan.allBindings()) {
                String fieldType = asText(field.type(), "text");
                if (!VALID_FIELD_TYPES.contains(fieldType)) {
                    fieldType = "text";
                }
                if ("static".equals(fieldType)) {
                    continue;
                }

                String columnName = asText(field.storageColumn(), asText(field.fieldId(), ""));
                String sqlType = asText(field.sqlType(), "VARCHAR(200)");
                if (columnName.isBlank() || sqlType.isBlank() || !seen.add(columnName)) {
                    continue;
                }
                columnBlock
                    .append(",\n    ")
                    .append(String.format("%-40s", columnName))
                    .append(' ')
                    .append(sqlType);
            }

            ddl.append("-- ")
                .append(subName)
                .append('\n')
                .append("CREATE TABLE IF NOT EXISTS ")
                .append(tableName)
                .append(" (\n")
                .append(columnBlock)
                .append(",\n")
                .append("    CONSTRAINT fk_")
                .append(tableName)
                .append("_submission\n")
                .append("        FOREIGN KEY (submission_id)\n")
                .append("        REFERENCES t_form_submission(id) ON DELETE CASCADE\n")
                .append(");\n\n");

            if ("multi".equals(tablePlan.recordType())) {
                ddl.append("CREATE INDEX IF NOT EXISTS idx_")
                    .append(tableName)
                    .append("_submission_id\n")
                    .append("    ON ")
                    .append(tableName)
                    .append("(submission_id);\n\n");
            }
        }

        return ddl.toString();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> castList(Object value) {
        return value instanceof List<?> list ? (List<Map<String, Object>>) list : List.of();
    }
    private String asText(Object value, String defaultValue) {
        return value == null ? defaultValue : String.valueOf(value);
    }
}
