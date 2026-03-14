package com.zhongan.form.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zhongan.form.util.StoragePlanBuilder;
import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;

@Service
public class SubmissionService {
    private final JdbcTemplate jdbcTemplate;
    private final TemplateService templateService;
    private final ObjectMapper objectMapper;
    private final StoragePlanBuilder storagePlanBuilder;

    public SubmissionService(
        JdbcTemplate jdbcTemplate,
        TemplateService templateService,
        ObjectMapper objectMapper,
        StoragePlanBuilder storagePlanBuilder
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.templateService = templateService;
        this.objectMapper = objectMapper;
        this.storagePlanBuilder = storagePlanBuilder;
    }

    public Map<String, Object> createSubmission(String templateId, Map<String, Object> body, String submittedBy) {
        Map<String, Object> template = templateService.requireActiveTemplate(templateId);
        Map<String, Object> schema = templateService.getSchema(templateId);
        Map<String, Object> formData = castMap(body.get("formData"));
        String status = normalizeStatus(String.valueOf(body.getOrDefault("status", "submitted")));
        Instant now = Instant.now();

        GeneratedKeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement("""
                INSERT INTO t_form_submission (template_id, template_name, form_data_json, submitted_by, submitted_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, new String[]{"id"});
            ps.setString(1, templateId);
            ps.setString(2, String.valueOf(template.get("name")));
            ps.setString(3, toJson(formData));
            ps.setString(4, submittedBy);
            ps.setTimestamp(5, Timestamp.from(now));
            ps.setTimestamp(6, Timestamp.from(now));
            ps.setString(7, status);
            return ps;
        }, keyHolder);

        Number submissionId = keyHolder.getKey();
        if (submissionId == null) {
            throw new IllegalStateException("无法生成 submissionId");
        }

        List<Map<String, Object>> subForms = castList(schema.get("subForms"));
        insertDynamicRecords(submissionId.longValue(), subForms, formData);
        return Map.of(
            "submissionId", submissionId.longValue(),
            "status", status,
            "submittedAt", now.toString()
        );
    }

    public Map<String, Object> listSubmissions(String templateId, int page, int size, String status) {
        String statusFilter = status == null || status.isBlank() ? "%" : status.trim();
        Integer total = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM t_form_submission WHERE template_id = ? AND status LIKE ?",
            Integer.class,
            templateId,
            statusFilter
        );
        List<Map<String, Object>> list = jdbcTemplate.query("""
            SELECT id AS submissionId,
                   template_name AS templateName,
                   submitted_by AS submittedBy,
                   submitted_at AS submittedAt,
                   status
            FROM t_form_submission
            WHERE template_id = ? AND status LIKE ?
            ORDER BY submitted_at DESC
            LIMIT ? OFFSET ?
            """,
            (rs, rowNum) -> Map.of(
                "submissionId", rs.getLong("submissionId"),
                "templateName", rs.getString("templateName"),
                "submittedBy", rs.getString("submittedBy"),
                "submittedAt", rs.getTimestamp("submittedAt"),
                "status", rs.getString("status")
            ),
            templateId,
            statusFilter,
            size,
            Math.max(0, (page - 1) * size)
        );
        return Map.of("total", total == null ? 0 : total, "list", list);
    }

    public Map<String, Object> getSubmission(Long submissionId) {
        Map<String, Object> meta = getSubmissionMeta(submissionId);
        String templateId = String.valueOf(meta.get("template_id"));
        Map<String, Object> formData = loadRawFormData(meta);
        if (formData.isEmpty()) {
            Map<String, Object> schema = templateService.getSchema(templateId);
            formData = loadFormData(submissionId, castList(schema.get("subForms")));
        }

        return Map.of(
            "submissionId", submissionId,
            "templateId", templateId,
            "status", meta.get("status"),
            "submittedBy", meta.get("submitted_by"),
            "submittedAt", meta.get("submitted_at"),
            "formData", formData
        );
    }

    public Map<String, Object> updateDraft(Long submissionId, Map<String, Object> body, String submittedBy) {
        Map<String, Object> meta = getSubmissionMeta(submissionId);
        if (!"draft".equals(meta.get("status"))) {
            throw new IllegalStateException("只有 draft 状态的提交才允许修改");
        }
        String templateId = String.valueOf(meta.get("template_id"));
        Map<String, Object> schema = templateService.getSchema(templateId);
        Map<String, Object> formData = castMap(body.get("formData"));

        List<Map<String, Object>> subForms = castList(schema.get("subForms"));
        deleteDynamicRecords(submissionId, subForms);
        insertDynamicRecords(submissionId, subForms, formData);

        jdbcTemplate.update("""
            UPDATE t_form_submission
            SET submitted_by = ?, updated_at = ?, status = 'draft', form_data_json = ?
            WHERE id = ?
            """, submittedBy, Timestamp.from(Instant.now()), toJson(formData), submissionId);

        return getSubmission(submissionId);
    }

    public void deleteDraft(Long submissionId) {
        Map<String, Object> meta = getSubmissionMeta(submissionId);
        if (!"draft".equals(meta.get("status"))) {
            throw new IllegalStateException("只有 draft 状态的提交才允许删除");
        }
        String templateId = String.valueOf(meta.get("template_id"));
        Map<String, Object> schema = templateService.getSchema(templateId);
        deleteDynamicRecords(submissionId, castList(schema.get("subForms")));
        jdbcTemplate.update("DELETE FROM t_form_submission WHERE id = ?", submissionId);
    }

    public void updateStatus(Long submissionId, String targetStatus) {
        getSubmissionMeta(submissionId);
        jdbcTemplate.update(
            "UPDATE t_form_submission SET status = ?, updated_at = ? WHERE id = ?",
            targetStatus,
            Timestamp.from(Instant.now()),
            submissionId
        );
    }

    private void insertDynamicRecords(Long submissionId, List<Map<String, Object>> subForms, Map<String, Object> formData) {
        for (StoragePlanBuilder.StorageTablePlan tablePlan : storagePlanBuilder.build(subForms)) {
            if ("multi".equals(tablePlan.recordType())) {
                for (StoragePlanBuilder.SubFormPlan subFormPlan : tablePlan.subForms()) {
                    Map<String, Object> data = castMap(formData.get(subFormPlan.subFormId()));
                    Map<String, Object> prefix = castMap(data.get("_prefix"));
                    List<Map<String, Object>> rows = castList(data.get("_rows"));
                    for (Map<String, Object> row : rows) {
                        Map<String, Object> payload = new LinkedHashMap<>();
                        for (StoragePlanBuilder.FieldBinding binding : subFormPlan.fields()) {
                            Object value = prefix.containsKey(binding.fieldId())
                                ? prefix.get(binding.fieldId())
                                : row.get(binding.fieldId());
                            payload.put(binding.storageColumn(), convertValue(value));
                        }
                        insertSingle(tablePlan.tableName(), submissionId, payload);
                    }
                }
                continue;
            }

            Map<String, Object> payload = new LinkedHashMap<>();
            for (StoragePlanBuilder.SubFormPlan subFormPlan : tablePlan.subForms()) {
                Map<String, Object> data = castMap(formData.get(subFormPlan.subFormId()));
                for (StoragePlanBuilder.FieldBinding binding : subFormPlan.fields()) {
                    payload.put(binding.storageColumn(), convertValue(data.get(binding.fieldId())));
                }
            }
            insertSingle(tablePlan.tableName(), submissionId, payload);
        }
    }

    private void deleteDynamicRecords(Long submissionId, List<Map<String, Object>> subForms) {
        for (StoragePlanBuilder.StorageTablePlan tablePlan : storagePlanBuilder.build(subForms)) {
            jdbcTemplate.update("DELETE FROM " + tablePlan.tableName() + " WHERE submission_id = ?", submissionId);
        }
    }

    private void insertSingle(String tableName, Long submissionId, Map<String, Object> data) {
        List<String> columns = new ArrayList<>(data.keySet());
        if (columns.isEmpty()) {
            jdbcTemplate.update("INSERT INTO " + tableName + " (submission_id) VALUES (?)", submissionId);
            return;
        }

        String columnPart = String.join(", ", columns);
        String placeholders = columns.stream().map(column -> "?").collect(Collectors.joining(", "));
        List<Object> params = new ArrayList<>();
        params.add(submissionId);
        for (String column : columns) {
            params.add(data.get(column));
        }

        jdbcTemplate.update(
            "INSERT INTO " + tableName + " (submission_id, " + columnPart + ") VALUES (?, " + placeholders + ")",
            params.toArray()
        );
    }

    private Map<String, Object> loadFormData(Long submissionId, List<Map<String, Object>> subForms) {
        Map<String, Object> formData = new LinkedHashMap<>();
        for (StoragePlanBuilder.StorageTablePlan tablePlan : storagePlanBuilder.build(subForms)) {
            List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT * FROM " + tablePlan.tableName() + " WHERE submission_id = ? ORDER BY id",
                submissionId
            );
            if ("multi".equals(tablePlan.recordType())) {
                for (StoragePlanBuilder.SubFormPlan subFormPlan : tablePlan.subForms()) {
                    List<Map<String, Object>> rowData = rows.stream()
                        .map(this::stripMetaColumns)
                        .map(row -> mapToFieldIds(row, subFormPlan.fields()))
                        .toList();
                    formData.put(subFormPlan.subFormId(), Map.of("_prefix", Map.of(), "_rows", rowData));
                }
                continue;
            }

            Map<String, Object> row = rows.isEmpty() ? Map.of() : stripMetaColumns(rows.get(0));
            for (StoragePlanBuilder.SubFormPlan subFormPlan : tablePlan.subForms()) {
                formData.put(subFormPlan.subFormId(), mapToFieldIds(row, subFormPlan.fields()));
            }
        }
        return formData;
    }

    private Map<String, Object> mapToFieldIds(Map<String, Object> row, List<StoragePlanBuilder.FieldBinding> bindings) {
        Map<String, Object> mapped = new LinkedHashMap<>();
        for (StoragePlanBuilder.FieldBinding binding : bindings) {
            mapped.put(binding.fieldId(), row.get(binding.storageColumn()));
        }
        return mapped;
    }

    private Map<String, Object> stripMetaColumns(Map<String, Object> row) {
        Map<String, Object> data = new LinkedHashMap<>(row);
        data.remove("ID");
        data.remove("SUBMISSION_ID");
        data.remove("CREATED_AT");
        data.remove("UPDATED_AT");
        data.remove("id");
        data.remove("submission_id");
        data.remove("created_at");
        data.remove("updated_at");
        return data;
    }

    private Map<String, Object> getSubmissionMeta(Long submissionId) {
        try {
            return jdbcTemplate.queryForMap("SELECT * FROM t_form_submission WHERE id = ?", submissionId);
        } catch (EmptyResultDataAccessException e) {
            throw new IllegalArgumentException("提交不存在: " + submissionId, e);
        }
    }

    private Map<String, Object> loadRawFormData(Map<String, Object> meta) {
        Object raw = meta.get("form_data_json");
        if (raw == null || String.valueOf(raw).isBlank()) {
            return Map.of();
        }
        return castMap(fromJson(String.valueOf(raw), Map.class));
    }

    private Object convertValue(Object value) {
        if (value instanceof List<?> || value instanceof Map<?, ?>) {
            return toJson(value);
        }
        return value;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
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
        return value instanceof Map<?, ?> map ? (Map<String, Object>) map : Map.of();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> castList(Object value) {
        return value instanceof List<?> list ? (List<Map<String, Object>>) list : List.of();
    }

    private String normalizeStatus(String raw) {
        return switch (raw) {
            case "draft", "submitted", "approved", "rejected" -> raw;
            default -> "draft";
        };
    }
}
