package com.zhongan.form.util;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class StoragePlanBuilder {

    public List<StorageTablePlan> build(List<Map<String, Object>> subForms) {
        List<Map<String, Object>> persistedSingles = subForms.stream()
            .filter(subForm -> !"multi".equals(asText(subForm.get("recordType"), "single")))
            .filter(this::hasPersistedFields)
            .toList();
        String sharedSingleTable = resolveSharedSingleTableName(persistedSingles);

        Map<String, StorageTablePlanBuilder> grouped = new LinkedHashMap<>();
        for (Map<String, Object> subForm : subForms) {
            if (!hasPersistedFields(subForm)) {
                continue;
            }

            String subFormId = asText(subForm.get("id"), "sub_form");
            String recordType = asText(subForm.get("recordType"), "single");
            String tableName = resolveTableName(subForm, sharedSingleTable);

            StorageTablePlanBuilder tablePlan = grouped.computeIfAbsent(
                tableName,
                ignored -> new StorageTablePlanBuilder(tableName, recordType)
            );
            tablePlan.recordType = "multi".equals(recordType) ? "multi" : tablePlan.recordType;
            tablePlan.addSubForm(subFormId, castList(subForm.get("fields")));
        }

        return grouped.values().stream().map(StorageTablePlanBuilder::build).toList();
    }

    public int countStorageTables(List<Map<String, Object>> subForms) {
        return build(subForms).size();
    }

    private String resolveSharedSingleTableName(List<Map<String, Object>> persistedSingles) {
        if (persistedSingles.isEmpty()) {
            return null;
        }
        if (persistedSingles.size() == 1) {
            return resolveOwnTableName(persistedSingles.get(0));
        }

        Set<String> existing = new LinkedHashSet<>();
        for (Map<String, Object> subForm : persistedSingles) {
            String storageTableName = asText(subForm.get("storageTableName"), "");
            if (!storageTableName.isBlank()) {
                existing.add(storageTableName);
            }
        }
        if (existing.size() == 1) {
            return existing.iterator().next();
        }

        String firstTable = resolveOwnTableName(persistedSingles.get(0));
        return firstTable.endsWith("_main") ? firstTable : firstTable + "_main";
    }

    private String resolveTableName(Map<String, Object> subForm, String sharedSingleTable) {
        if (!"multi".equals(asText(subForm.get("recordType"), "single")) && sharedSingleTable != null) {
            return sharedSingleTable;
        }
        return resolveOwnTableName(subForm);
    }

    private String resolveOwnTableName(Map<String, Object> subForm) {
        String storageTableName = asText(subForm.get("storageTableName"), "");
        if (!storageTableName.isBlank()) {
            return storageTableName;
        }
        String sqlTableName = asText(subForm.get("sqlTableName"), "");
        return sqlTableName.isBlank() ? "t_unknown" : sqlTableName;
    }

    private boolean hasPersistedFields(Map<String, Object> subForm) {
        return castList(subForm.get("fields")).stream()
            .anyMatch(field -> !"static".equals(asText(field.get("type"), "text")));
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> castList(Object value) {
        return value instanceof List<?> list ? (List<Map<String, Object>>) list : List.of();
    }

    private String asText(Object value, String defaultValue) {
        return value == null ? defaultValue : String.valueOf(value);
    }

    public record StorageTablePlan(String tableName, String recordType, List<SubFormPlan> subForms) {
        public List<FieldBinding> allBindings() {
            List<FieldBinding> bindings = new ArrayList<>();
            for (SubFormPlan subForm : subForms) {
                bindings.addAll(subForm.fields());
            }
            return bindings;
        }
    }

    public record SubFormPlan(String subFormId, List<FieldBinding> fields) {
    }

    public record FieldBinding(String fieldId, String storageColumn, String type, String sqlType) {
    }

    private static final class StorageTablePlanBuilder {
        private final String tableName;
        private String recordType;
        private final List<SubFormPlan> subForms = new ArrayList<>();
        private final Set<String> seenColumns = new LinkedHashSet<>();

        private StorageTablePlanBuilder(String tableName, String recordType) {
            this.tableName = tableName;
            this.recordType = recordType;
        }

        private void addSubForm(String subFormId, List<Map<String, Object>> fields) {
            List<FieldBinding> bindings = new ArrayList<>();
            for (Map<String, Object> field : fields) {
                String fieldType = asText(field.get("type"), "text");
                if ("static".equals(fieldType)) {
                    continue;
                }
                String preferred = asText(field.get("storageColumn"), "");
                if (preferred.isBlank()) {
                    preferred = asText(field.get("sqlColumn"), "");
                }
                if (preferred.isBlank()) {
                    preferred = asText(field.get("id"), "field");
                }
                String storageColumn = ensureUnique(preferred, asText(field.get("id"), "field"));
                bindings.add(new FieldBinding(
                    asText(field.get("id"), storageColumn),
                    storageColumn,
                    fieldType,
                    asText(field.get("sqlType"), "VARCHAR(200)")
                ));
            }
            if (!bindings.isEmpty()) {
                subForms.add(new SubFormPlan(subFormId, bindings));
            }
        }

        private StorageTablePlan build() {
            return new StorageTablePlan(tableName, recordType, List.copyOf(subForms));
        }

        private String ensureUnique(String preferred, String fallback) {
            String base = normalizeIdentifier(preferred.isBlank() ? fallback : preferred);
            if (base.isBlank()) {
                base = normalizeIdentifier(fallback);
            }
            if (base.isBlank()) {
                base = "field";
            }
            String candidate = base;
            int index = 2;
            while (!seenColumns.add(candidate)) {
                candidate = base + "_" + index;
                index += 1;
            }
            return candidate;
        }

        private static String asText(Object value, String defaultValue) {
            return value == null ? defaultValue : String.valueOf(value);
        }

        private static String normalizeIdentifier(String value) {
            String normalized = value.trim().toLowerCase().replaceAll("[^a-z0-9]+", "_");
            normalized = normalized.replaceAll("^_+|_+$", "");
            if (normalized.isBlank()) {
                return "";
            }
            if (Character.isDigit(normalized.charAt(0))) {
                return "field_" + normalized;
            }
            return normalized;
        }
    }
}
