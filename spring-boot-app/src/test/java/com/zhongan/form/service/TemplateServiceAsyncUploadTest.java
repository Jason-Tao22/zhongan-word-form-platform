package com.zhongan.form.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
    "template-storage.dir=target/test-template-sources",
    "spring.datasource.url=jdbc:h2:mem:formdb;MODE=PostgreSQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE",
})
class TemplateServiceAsyncUploadTest {

    @Autowired
    private TemplateService templateService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @MockBean
    private WordParserClient wordParserClient;

    @BeforeEach
    void setUp() throws IOException {
        jdbcTemplate.update("DELETE FROM t_form_submission");
        jdbcTemplate.update("DELETE FROM t_form_template");
        Path storageRoot = Path.of("target/test-template-sources");
        if (Files.exists(storageRoot)) {
            try (var stream = Files.walk(storageRoot)) {
                stream.sorted((left, right) -> right.compareTo(left)).forEach(path -> {
                    try {
                        Files.deleteIfExists(path);
                    } catch (IOException e) {
                        throw new IllegalStateException(e);
                    }
                });
            }
        }
    }

    @Test
    void uploadQueuesTemplateAndEventuallyPersistsParsedResult() {
        when(wordParserClient.parseWord(eq("sample.docx"), any(byte[].class)))
            .thenReturn(fakeParseResult("sample.docx", "openai"));

        Map<String, Object> accepted = templateService.upload(
            new MockMultipartFile("file", "sample.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "hello".getBytes()),
            "tester"
        );

        assertThat(accepted.get("status")).isEqualTo("processing");
        String templateId = String.valueOf(accepted.get("templateId"));

        Map<String, Object> detail = awaitStatus(templateId, "pending_review", Duration.ofSeconds(5));
        assertThat(detail.get("analysisMode")).isEqualTo("openai");
        assertThat(detail.get("name")).isEqualTo("sample");
        assertThat(String.valueOf(detail.get("ddlSql"))).contains("CREATE TABLE");
        assertThat(String.valueOf(detail.get("prototypeHtml"))).contains("<html");
        assertThat(Path.of(String.valueOf(detail.get("storedSourcePath")))).exists();
        assertThat(detail.get("processingStage")).isEqualTo("review_ready");
        assertThat(detail.get("storageTableCount")).isEqualTo(1);
    }

    @Test
    void retryReusesStoredSourceAfterBackgroundFailure() {
        AtomicInteger attempts = new AtomicInteger();
        when(wordParserClient.parseWord(eq("legacy.doc"), any(byte[].class)))
            .thenAnswer(invocation -> {
                if (attempts.getAndIncrement() == 0) {
                    throw new IllegalStateException("mock parser failure");
                }
                return fakeParseResult("legacy.docx", "openai");
            });

        Map<String, Object> accepted = templateService.upload(
            new MockMultipartFile("file", "legacy.doc", "application/msword", "hello".getBytes()),
            "tester"
        );
        String templateId = String.valueOf(accepted.get("templateId"));

        Map<String, Object> failed = awaitStatus(templateId, "failed", Duration.ofSeconds(5));
        assertThat(String.valueOf(failed.get("errorMessage"))).contains("mock parser failure");

        templateService.retry(templateId);

        Map<String, Object> recovered = awaitStatus(templateId, "pending_review", Duration.ofSeconds(5));
        assertThat(recovered.get("analysisMode")).isEqualTo("openai");
        verify(wordParserClient, times(2)).parseWord(eq("legacy.doc"), any(byte[].class));
    }

    @Test
    void uploadBackfillsDdlWhenParserReturnsBlank() {
        when(wordParserClient.parseWord(eq("blank-ddl.docx"), any(byte[].class)))
            .thenReturn(fakeParseResult("blank-ddl.docx", "openai", ""));

        Map<String, Object> accepted = templateService.upload(
            new MockMultipartFile("file", "blank-ddl.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "hello".getBytes()),
            "tester"
        );

        Map<String, Object> detail = awaitStatus(String.valueOf(accepted.get("templateId")), "pending_review", Duration.ofSeconds(5));
        assertThat(String.valueOf(detail.get("ddlSql"))).contains("CREATE TABLE IF NOT EXISTS t_insp_sample_form");
    }

    @Test
    void uploadBackfillsMergedDdlWhenParserReturnsMultipleSingleSubForms() {
        when(wordParserClient.parseWord(eq("merged.docx"), any(byte[].class)))
            .thenReturn(fakeMergedParseResult());

        Map<String, Object> accepted = templateService.upload(
            new MockMultipartFile("file", "merged.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "hello".getBytes()),
            "tester"
        );

        Map<String, Object> detail = awaitStatus(String.valueOf(accepted.get("templateId")), "pending_review", Duration.ofSeconds(5));
        String ddl = String.valueOf(detail.get("ddlSql"));
        assertThat(ddl).contains("CREATE TABLE IF NOT EXISTS t_insp_cover_main");
        assertThat(ddl).doesNotContain("CREATE TABLE IF NOT EXISTS t_insp_base_info");
        assertThat(detail.get("storageTableCount")).isEqualTo(1);
    }

    @Test
    void updateSchemaPersistsManualAdjustments() {
        when(wordParserClient.parseWord(eq("editable.docx"), any(byte[].class)))
            .thenReturn(fakeParseResult("editable.docx", "openai"));

        Map<String, Object> accepted = templateService.upload(
            new MockMultipartFile("file", "editable.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "hello".getBytes()),
            "tester"
        );

        String templateId = String.valueOf(accepted.get("templateId"));
        awaitStatus(templateId, "pending_review", Duration.ofSeconds(5));

        Map<String, Object> schema = templateService.getSchema(templateId);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> subForms = (List<Map<String, Object>>) schema.get("subForms");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> fields = (List<Map<String, Object>>) subForms.get(0).get("fields");
        Map<String, Object> originalField = fields.get(0);
        fields.set(0, Map.of(
            "id", originalField.get("id"),
            "label", originalField.get("label"),
            "type", "textarea",
            "sqlColumn", "field_text"
        ));
        schema.put("documentBlocks", List.of(Map.of("kind", "paragraph", "tokens", List.of())));

        Map<String, Object> updated = templateService.updateSchema(templateId, schema);
        assertThat(updated.get("status")).isEqualTo("pending_review");

        Map<String, Object> reloadedSchema = templateService.getSchema(templateId);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> reloadedSubForms = (List<Map<String, Object>>) reloadedSchema.get("subForms");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> reloadedFields = (List<Map<String, Object>>) reloadedSubForms.get(0).get("fields");
        assertThat(reloadedFields.get(0).get("type")).isEqualTo("textarea");
        assertThat(String.valueOf(templateService.getTemplateDetail(templateId).get("ddlSql")))
            .contains("CREATE TABLE IF NOT EXISTS t_insp_sample_form");
    }

    private Map<String, Object> awaitStatus(String templateId, String expectedStatus, Duration timeout) {
        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            Map<String, Object> detail = templateService.getTemplateDetail(templateId);
            if (expectedStatus.equals(detail.get("status"))) {
                return detail;
            }
            try {
                Thread.sleep(50);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("等待模板状态时被中断", e);
            }
        }
        throw new AssertionError("模板未在预期时间内进入状态: " + expectedStatus);
    }

    private Map<String, Object> fakeParseResult(String sourceFile, String analysisMode) {
        return fakeParseResult(sourceFile, analysisMode, "CREATE TABLE t_insp_sample_form (id BIGINT);");
    }

    private Map<String, Object> fakeParseResult(String sourceFile, String analysisMode, String ddl) {
        Map<String, Object> field = Map.of(
            "id", "field_text",
            "label", "文本字段",
            "type", "text"
        );
        Map<String, Object> row = Map.of(
            "cells", List.of(Map.of("fieldId", "field_text"))
        );
        Map<String, Object> subForm = Map.of(
            "id", "sample_form",
            "name", "样例表",
            "sqlTableName", "t_insp_sample_form",
            "recordType", "single",
            "layout", Map.of("type", "key-value", "rows", List.of(row)),
            "fields", List.of(field)
        );
        Map<String, Object> schema = Map.of(
            "schemaVersion", "1.0",
            "templateId", "ignored",
            "templateName", sourceFile.replaceFirst("\\.docx?$", ""),
            "sourceFile", sourceFile,
            "createdAt", "2026-03-08T00:00:00Z",
            "sqlDatabase", "postgresql",
            "subForms", List.of(subForm),
            "documentBlocks", List.of()
        );
        return Map.of(
            "templateId", "ignored",
            "templateName", sourceFile.replaceFirst("\\.docx?$", ""),
            "sourceFile", sourceFile,
            "schema", schema,
            "ddl", ddl,
            "analysisMode", analysisMode,
            "structureFingerprint", "fingerprint",
            "sourceSha256", "sha",
            "prototypeHtml", "<html><body>ok</body></html>"
        );
    }

    private Map<String, Object> fakeMergedParseResult() {
        Map<String, Object> cover = Map.of(
            "id", "cover",
            "name", "封面",
            "sqlTableName", "t_insp_cover",
            "recordType", "single",
            "layout", Map.of("type", "key-value", "rows", List.of()),
            "fields", List.of(Map.of("id", "report_no", "label", "报告编号", "type", "text", "sqlColumn", "report_no"))
        );
        Map<String, Object> base = Map.of(
            "id", "base_info",
            "name", "基本信息",
            "sqlTableName", "t_insp_base_info",
            "recordType", "single",
            "layout", Map.of("type", "key-value", "rows", List.of()),
            "fields", List.of(Map.of("id", "device_code", "label", "设备代码", "type", "text", "sqlColumn", "device_code"))
        );
        Map<String, Object> schema = Map.of(
            "schemaVersion", "1.0",
            "templateId", "ignored",
            "templateName", "merged",
            "sourceFile", "merged.docx",
            "createdAt", "2026-03-08T00:00:00Z",
            "sqlDatabase", "postgresql",
            "subForms", List.of(cover, base),
            "documentBlocks", List.of()
        );
        return Map.of(
            "templateId", "ignored",
            "templateName", "merged",
            "sourceFile", "merged.docx",
            "schema", schema,
            "ddl", "",
            "analysisMode", "openai",
            "structureFingerprint", "fingerprint",
            "sourceSha256", "sha",
            "prototypeHtml", "<html><body>ok</body></html>"
        );
    }
}
