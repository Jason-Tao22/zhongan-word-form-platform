package com.zhongan.form.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zhongan.form.util.FormDdlGenerator;
import com.zhongan.form.util.StoragePlanBuilder;
import com.zhongan.form.util.SqlDialectAdapter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class TemplateService {
    private final JdbcTemplate jdbcTemplate;
    private final WordParserClient wordParserClient;
    private final ObjectMapper objectMapper;
    private final SqlDialectAdapter sqlDialectAdapter;
    private final FormDdlGenerator formDdlGenerator;
    private final StoragePlanBuilder storagePlanBuilder;
    private final AsyncTaskExecutor templateProcessingExecutor;
    private final Path storageRoot;
    private final String datasourceUrl;

    public TemplateService(
        JdbcTemplate jdbcTemplate,
        WordParserClient wordParserClient,
        ObjectMapper objectMapper,
        SqlDialectAdapter sqlDialectAdapter,
        FormDdlGenerator formDdlGenerator,
        StoragePlanBuilder storagePlanBuilder,
        AsyncTaskExecutor templateProcessingExecutor,
        @Value("${spring.datasource.url:}") String datasourceUrl,
        @Value("${template-storage.dir:data/template-sources}") String storageDir
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.wordParserClient = wordParserClient;
        this.objectMapper = objectMapper;
        this.sqlDialectAdapter = sqlDialectAdapter;
        this.formDdlGenerator = formDdlGenerator;
        this.storagePlanBuilder = storagePlanBuilder;
        this.templateProcessingExecutor = templateProcessingExecutor;
        this.datasourceUrl = datasourceUrl;
        this.storageRoot = Path.of(storageDir).toAbsolutePath().normalize();
    }

    public Map<String, Object> upload(MultipartFile file, String createdBy) {
        String sourceFile = asText(file.getOriginalFilename(), "uploaded.docx");
        String templateId = UUID.randomUUID().toString();
        String templateName = stripWordExtension(sourceFile);
        Instant now = Instant.now();
        Timestamp nowTs = Timestamp.from(now);
        byte[] sourceBytes = readBytes(file);
        Path storedSourcePath = storeSourceFile(templateId, sourceFile, sourceBytes);

        jdbcTemplate.update("""
            INSERT INTO t_form_template (
                id, name, source_file, source_sha256, structure_fingerprint, analysis_mode,
                schema_json, ddl_sql, prototype_html, stored_source_path, error_message, quality_warning,
                created_by, created_at, status, sub_form_count, storage_table_count, processing_stage, processing_duration_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            templateId,
            templateName,
            sourceFile,
            "",
            "",
            "processing",
            "{}",
            "",
            "",
            storedSourcePath.toString(),
            "",
            "",
            createdBy,
            nowTs,
            "processing",
            0,
            0,
            "queued",
            null
        );

        scheduleProcessing(templateId, sourceFile, storedSourcePath);

        return Map.of(
            "templateId", templateId,
            "templateName", templateName,
            "subFormCount", 0,
            "createdAt", now.toString(),
            "status", "processing",
            "analysisMode", "processing",
            "processingStage", "queued",
            "structureFingerprint", ""
        );
    }

    public Map<String, Object> getParserStatus() {
        return wordParserClient.getParserStatus();
    }

    public Map<String, Object> retry(String templateId) {
        Map<String, Object> detail = getTemplateDetail(templateId);
        String status = asText(detail.get("status"), "");
        if ("processing".equals(status)) {
            return detail;
        }

        String storedPathText = asText(detail.get("storedSourcePath"), "");
        if (storedPathText.isBlank()) {
            throw new IllegalStateException("未找到模板原始 Word 文件，无法重试。请重新上传。");
        }
        Path storedSourcePath = Path.of(storedPathText);
        if (!Files.exists(storedSourcePath)) {
            throw new IllegalStateException("未找到模板原始 Word 文件，无法重试。请重新上传。");
        }

        jdbcTemplate.update("""
            UPDATE t_form_template
            SET status = ?, analysis_mode = ?, error_message = ?, schema_json = ?, ddl_sql = ?, prototype_html = ?,
                structure_fingerprint = ?, source_sha256 = ?, sub_form_count = ?, storage_table_count = ?, quality_warning = ?, processing_stage = ?, processing_duration_seconds = ?
            WHERE id = ?
            """,
            "processing",
            "processing",
            "",
            "{}",
            "",
            "",
            "",
            "",
            0,
            0,
            "",
            "queued",
            null,
            templateId
        );

        scheduleProcessing(templateId, asText(detail.get("sourceFile"), storedSourcePath.getFileName().toString()), storedSourcePath);
        return getTemplateDetail(templateId);
    }

    public Map<String, Object> publish(String templateId) {
        Map<String, Object> detail = getTemplateDetail(templateId);
        String status = asText(detail.get("status"), "");
        if ("active".equals(status)) {
            return detail;
        }
        if ("processing".equals(status)) {
            throw new IllegalStateException("模板仍在后台解析中，请稍后刷新。");
        }
        if ("failed".equals(status)) {
            throw new IllegalStateException("模板解析失败，不能发布。请先修复后重试。");
        }

        String ddl = asText(detail.get("ddlSql"), "");
        if (ddl.isBlank()) {
            throw new IllegalStateException("模板 DDL 为空，不能发布。请先修复 schema 或重新生成模板。");
        }
        List<String> statements = datasourceUrl.startsWith("jdbc:h2:")
            ? sqlDialectAdapter.adaptPostgresDdlToH2(ddl)
            : sqlDialectAdapter.splitStatements(ddl);
        for (String statement : statements) {
            jdbcTemplate.execute(statement);
        }

        jdbcTemplate.update("UPDATE t_form_template SET status = ?, published_at = ?, processing_stage = ? WHERE id = ?",
            "active", Timestamp.from(Instant.now()), "active", templateId);
        return getTemplateDetail(templateId);
    }

    public Map<String, Object> getSchema(String templateId) {
        Map<String, Object> detail = getTemplateDetail(templateId);
        String schemaJson = asText(detail.get("schemaJson"), asText(detail.get("schema_json"), "{}"));
        return castMap(fromJson(schemaJson, Map.class));
    }

    public Map<String, Object> getTemplateContent(String templateId) {
        try {
            Map<String, Object> row = jdbcTemplate.queryForMap("""
                SELECT id, ddl_sql, prototype_html
                FROM t_form_template
                WHERE id = ?
                """, templateId);
            return withTemplateAliases(row);
        } catch (EmptyResultDataAccessException e) {
            throw new IllegalArgumentException("模板不存在: " + templateId, e);
        }
    }

    public Map<String, Object> updateSchema(String templateId, Map<String, Object> schema) {
        Map<String, Object> detail = getTemplateDetail(templateId);
        String status = asText(detail.get("status"), "");
        if ("processing".equals(status)) {
            throw new IllegalStateException("模板仍在后台解析中，请稍后再修改。");
        }
        if ("inactive".equals(status)) {
            throw new IllegalStateException("模板已停用，不能直接修改。");
        }
        if ("active".equals(status)) {
            throw new IllegalStateException("已发布模板不能直接修改，请重新上传或另存版本后再发布。");
        }

        Map<String, Object> normalized = new HashMap<>(schema);
        normalized.put("templateId", templateId);
        normalized.putIfAbsent("schemaVersion", "1.0");
        normalized.putIfAbsent("sqlDatabase", "postgresql");
        normalized.putIfAbsent("templateName", asText(detail.get("name"), "未命名模板"));
        normalized.putIfAbsent("sourceFile", asText(detail.get("sourceFile"), ""));
        normalized.putIfAbsent("documentBlocks", List.of());

        List<Map<String, Object>> subForms = castList(normalized.get("subForms"));
        String ddl = subForms.isEmpty()
            ? asText(detail.get("ddlSql"), "")
            : formDdlGenerator.generate(subForms);
        String templateName = asText(normalized.get("templateName"), asText(detail.get("name"), "未命名模板"));
        String sourceFile = asText(normalized.get("sourceFile"), asText(detail.get("sourceFile"), ""));

        jdbcTemplate.update("""
            UPDATE t_form_template
            SET name = ?, source_file = ?, schema_json = ?, ddl_sql = ?, error_message = ?, status = ?,
                sub_form_count = ?, storage_table_count = ?, quality_warning = ?, processing_stage = ?
            WHERE id = ?
            """,
            templateName,
            sourceFile,
            toJson(normalized),
            ddl,
            "",
            "pending_review",
            subForms.size(),
            storagePlanBuilder.countStorageTables(subForms),
            "",
            "review_ready",
            templateId
        );
        return getTemplateDetail(templateId);
    }

    public Map<String, Object> getTemplateDetail(String templateId) {
        return getTemplateDetail(templateId, true);
    }

    public Map<String, Object> getTemplateDetail(String templateId, boolean includeContent) {
        try {
            String sql = includeContent
                ? """
                    SELECT id, name, source_file, source_sha256, structure_fingerprint, analysis_mode,
                           schema_json, ddl_sql, prototype_html, stored_source_path, error_message, quality_warning,
                           created_by, created_at,
                           status, sub_form_count, storage_table_count, processing_stage, processing_duration_seconds, published_at
                    FROM t_form_template
                    WHERE id = ?
                    """
                : """
                    SELECT id, name, source_file, source_sha256, structure_fingerprint, analysis_mode,
                           stored_source_path, error_message, quality_warning, created_by, created_at,
                           status, sub_form_count, storage_table_count, processing_stage, processing_duration_seconds, published_at
                    FROM t_form_template
                    WHERE id = ?
                    """;
            Map<String, Object> row = jdbcTemplate.queryForMap(sql, templateId);
            return withTemplateAliases(row);
        } catch (EmptyResultDataAccessException e) {
            throw new IllegalArgumentException("模板不存在: " + templateId, e);
        }
    }

    public Map<String, Object> list(int page, int size, String keyword) {
        String likeKeyword = "%" + (keyword == null ? "" : keyword.trim()) + "%";
        Integer total = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM t_form_template WHERE name LIKE ?",
            Integer.class,
            likeKeyword
        );

        List<Map<String, Object>> list = jdbcTemplate.query("""
            SELECT id AS templateId,
                   name AS templateName,
                   source_file AS sourceFile,
                   analysis_mode AS analysisMode,
                   sub_form_count AS subFormCount,
                   storage_table_count AS storageTableCount,
                   quality_warning AS qualityWarning,
                   processing_stage AS processingStage,
                   processing_duration_seconds AS processingDurationSeconds,
                   error_message AS errorMessage,
                   created_by AS createdBy,
                   created_at AS createdAt,
                   status
            FROM t_form_template
            WHERE name LIKE ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (rs, rowNum) -> {
                Map<String, Object> row = new HashMap<>();
                row.put("templateId", rs.getString("templateId"));
                row.put("templateName", rs.getString("templateName"));
                row.put("sourceFile", rs.getString("sourceFile"));
                row.put("analysisMode", rs.getString("analysisMode"));
                row.put("subFormCount", rs.getInt("subFormCount"));
                row.put("storageTableCount", rs.getInt("storageTableCount"));
                row.put("qualityWarning", rs.getString("qualityWarning"));
                row.put("processingStage", rs.getString("processingStage"));
                row.put("processingDurationSeconds", rs.getObject("processingDurationSeconds"));
                row.put("errorMessage", rs.getString("errorMessage"));
                row.put("createdBy", rs.getString("createdBy"));
                row.put("createdAt", rs.getTimestamp("createdAt"));
                row.put("status", rs.getString("status"));
                return row;
            },
            likeKeyword,
            size,
            Math.max(0, (page - 1) * size)
        );

        return Map.of("total", total == null ? 0 : total, "list", list);
    }

    public void delete(String templateId) {
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM t_form_submission WHERE template_id = ?",
            Integer.class,
            templateId
        );
        if (count != null && count > 0) {
            throw new IllegalStateException("模板已有提交记录，不能删除");
        }
        jdbcTemplate.update("UPDATE t_form_template SET status = ?, processing_stage = ? WHERE id = ?", "inactive", "inactive", templateId);
    }

    public Map<String, Object> requireActiveTemplate(String templateId) {
        Map<String, Object> detail = getTemplateDetail(templateId);
        if (!"active".equals(detail.get("status"))) {
            throw new IllegalStateException("模板尚未发布，不能提交表单");
        }
        return detail;
    }

    private String toJson(Object data) {
        try {
            return objectMapper.writeValueAsString(data);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("JSON 序列化失败", e);
        }
    }

    private <T> T fromJson(String json, Class<T> type) {
        try {
            return objectMapper.readValue(json, type);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("JSON 解析失败", e);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> castMap(Object value) {
        return value instanceof Map<?, ?> map ? (Map<String, Object>) map : new HashMap<>();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> castList(Object value) {
        return value instanceof List<?> list ? (List<Map<String, Object>>) list : List.of();
    }

    private String asText(Object value, String defaultValue) {
        return value == null ? defaultValue : String.valueOf(value);
    }

    private Map<String, Object> withTemplateAliases(Map<String, Object> row) {
        Map<String, Object> normalized = new HashMap<>(row);
        normalized.put("sourceFile", row.get("source_file"));
        normalized.put("sourceSha256", row.get("source_sha256"));
        normalized.put("structureFingerprint", row.get("structure_fingerprint"));
        normalized.put("analysisMode", row.get("analysis_mode"));
        normalized.put("schemaJson", row.get("schema_json"));
        normalized.put("ddlSql", row.get("ddl_sql"));
        normalized.put("prototypeHtml", row.get("prototype_html"));
        normalized.put("storedSourcePath", row.get("stored_source_path"));
        normalized.put("errorMessage", row.get("error_message"));
        normalized.put("qualityWarning", row.get("quality_warning"));
        normalized.put("createdBy", row.get("created_by"));
        normalized.put("createdAt", row.get("created_at"));
        normalized.put("subFormCount", row.get("sub_form_count"));
        normalized.put("storageTableCount", row.get("storage_table_count"));
        normalized.put("processingStage", row.get("processing_stage"));
        normalized.put("processingDurationSeconds", row.get("processing_duration_seconds"));
        normalized.put("publishedAt", row.get("published_at"));
        return normalized;
    }

    private void scheduleProcessing(String templateId, String sourceFile, Path storedSourcePath) {
        templateProcessingExecutor.execute(() -> processTemplate(templateId, sourceFile, storedSourcePath));
    }

    private void processTemplate(String templateId, String sourceFile, Path storedSourcePath) {
        Instant startedAt = Instant.now();
        try {
            jdbcTemplate.update("UPDATE t_form_template SET processing_stage = ? WHERE id = ?", "parsing_word", templateId);
            Map<String, Object> parseResult = wordParserClient.parseWord(sourceFile, Files.readAllBytes(storedSourcePath));
            jdbcTemplate.update("UPDATE t_form_template SET processing_stage = ? WHERE id = ?", "building_schema", templateId);
            Map<String, Object> schema = castMap(parseResult.get("schema"));
            List<Map<String, Object>> subForms = castList(schema.get("subForms"));
            String templateName = asText(parseResult.get("templateName"), stripWordExtension(sourceFile));
            String normalizedSourceFile = asText(parseResult.get("sourceFile"), sourceFile);
            String sourceSha256 = asText(parseResult.get("sourceSha256"), "");
            String structureFingerprint = asText(parseResult.get("structureFingerprint"), "");
            String analysisMode = asText(parseResult.get("analysisMode"), "unknown");
            String ddl = asText(parseResult.get("ddl"), "");
            if (ddl.isBlank() && !subForms.isEmpty()) {
                ddl = formDdlGenerator.generate(subForms);
            }
            String prototypeHtml = asText(parseResult.get("prototypeHtml"), "");
            String qualityWarning = asText(parseResult.get("qualityWarning"), "");
            int subFormCount = subForms.size();
            int storageTableCount = storagePlanBuilder.countStorageTables(subForms);
            int processingDurationSeconds = Math.toIntExact(Math.max(1, Duration.between(startedAt, Instant.now()).toSeconds()));

            jdbcTemplate.update("""
                UPDATE t_form_template
                SET name = ?, source_file = ?, source_sha256 = ?, structure_fingerprint = ?, analysis_mode = ?,
                    schema_json = ?, ddl_sql = ?, prototype_html = ?, error_message = ?, status = ?,
                    sub_form_count = ?, storage_table_count = ?, quality_warning = ?, processing_stage = ?, processing_duration_seconds = ?
                WHERE id = ?
                """,
                templateName,
                normalizedSourceFile,
                sourceSha256,
                structureFingerprint,
                analysisMode,
                toJson(schema),
                ddl,
                prototypeHtml,
                "",
                "pending_review",
                subFormCount,
                storageTableCount,
                qualityWarning,
                "review_ready",
                processingDurationSeconds,
                templateId
            );
        } catch (Exception e) {
            int processingDurationSeconds = Math.toIntExact(Math.max(1, Duration.between(startedAt, Instant.now()).toSeconds()));
            jdbcTemplate.update("""
                UPDATE t_form_template
                SET analysis_mode = ?, error_message = ?, status = ?, schema_json = ?, ddl_sql = ?, prototype_html = ?,
                    quality_warning = ?, processing_stage = ?, processing_duration_seconds = ?
                WHERE id = ?
                """,
                "failed",
                rootMessage(e),
                "failed",
                "{}",
                "",
                "",
                "",
                "failed",
                processingDurationSeconds,
                templateId
            );
        }
    }

    private byte[] readBytes(MultipartFile file) {
        try {
            return file.getBytes();
        } catch (IOException e) {
            throw new IllegalStateException("读取上传文件失败", e);
        }
    }

    private Path storeSourceFile(String templateId, String sourceFile, byte[] sourceBytes) {
        try {
            Path targetDir = storageRoot.resolve(templateId);
            Files.createDirectories(targetDir);
            Path targetFile = targetDir.resolve(sanitizeFilename(sourceFile));
            Files.write(targetFile, sourceBytes);
            return targetFile;
        } catch (IOException e) {
            throw new IllegalStateException("保存原始模板失败", e);
        }
    }

    private String stripWordExtension(String sourceFile) {
        return sourceFile.replaceFirst("(?i)\\.(docx?|DOCX?)$", "");
    }

    private String sanitizeFilename(String sourceFile) {
        String sanitized = sourceFile.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        return sanitized.isBlank() ? "uploaded.docx" : sanitized;
    }

    private String rootMessage(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return asText(current.getMessage(), error.getClass().getSimpleName());
    }
}
