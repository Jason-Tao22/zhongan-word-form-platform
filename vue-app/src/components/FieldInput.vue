<template>
  <span v-if="field.type === 'static'" class="cell-static">{{ field.label }}</span>

  <el-input
    v-else-if="field.type === 'text'"
    v-model="innerValue"
    size="small"
    class="cell-input"
    :placeholder="field.required ? '请输入' : ''"
  />

  <el-input-number
    v-else-if="field.type === 'number'"
    v-model="innerValue"
    :controls="false"
    size="small"
    class="cell-input"
  />

  <el-input
    v-else-if="field.type === 'textarea'"
    v-model="innerValue"
    type="textarea"
    :autosize="{ minRows: textareaRows }"
    resize="vertical"
    size="small"
    class="cell-input"
  />

  <el-date-picker
    v-else-if="field.type === 'date'"
    v-model="innerValue"
    type="date"
    size="small"
    class="cell-input"
    value-format="YYYY-MM-DD"
  />

  <div
    v-else-if="field.type === 'radio'"
    class="cell-choice-wrap"
  >
    <el-radio-group
      v-model="innerValue"
      size="small"
      class="cell-radio-group"
    >
      <el-radio
        v-for="opt in field.options || []"
        :key="opt"
        :label="opt"
        class="choice-pill"
      >
        {{ opt }}
      </el-radio>
    </el-radio-group>
    <button
      v-if="modelValue"
      type="button"
      class="choice-clear"
      @click="clearRadio"
    >
      清空
    </button>
  </div>

  <el-select
    v-else-if="field.type === 'select'"
    v-model="innerValue"
    size="small"
    class="cell-input"
    clearable
  >
    <el-option
      v-for="opt in field.options || []"
      :key="opt"
      :label="opt"
      :value="opt"
    />
  </el-select>

  <el-checkbox-group
    v-else-if="field.type === 'checkbox_group'"
    v-model="innerValue"
    size="small"
    class="cell-checkbox-group"
  >
    <el-checkbox
      v-for="opt in field.options || []"
      :key="opt"
      :label="opt"
      class="choice-pill"
    >
      {{ opt }}
    </el-checkbox>
  </el-checkbox-group>

  <el-input
    v-else
    v-model="innerValue"
    size="small"
    class="cell-input"
  />
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  field: { type: Object, required: true },
  modelValue: { default: null },
})

const emit = defineEmits(['update:modelValue'])

const innerValue = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const textareaRows = computed(() => {
  const minHeight = Number(props.field?.minHeightPx) || 96
  return Math.max(3, Math.round(minHeight / 36))
})

function clearRadio() {
  emit('update:modelValue', null)
}
</script>

<style scoped>
.cell-static {
  color: #5c6b80;
  font-size: 13px;
}

.cell-input {
  width: 100%;
}

.cell-radio-group,
.cell-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.cell-choice-wrap {
  display: grid;
  gap: 6px;
}

.choice-pill {
  margin-right: 0;
}

.choice-clear {
  justify-self: start;
  border: none;
  background: transparent;
  color: #4b5563;
  font: inherit;
  cursor: pointer;
  padding: 0;
}

:deep(.el-input__wrapper),
:deep(.el-textarea__inner),
:deep(.el-select__wrapper),
:deep(.el-input-number),
:deep(.el-date-editor.el-input),
:deep(.el-date-editor.el-input__wrapper) {
  width: 100%;
}

:deep(.el-input__wrapper),
:deep(.el-textarea__inner),
:deep(.el-select__wrapper) {
  box-shadow: none;
  border-radius: 8px;
  border: 1px solid #d4dceb;
  background: #fcfdff;
}

:deep(.el-input__wrapper.is-focus),
:deep(.el-select__wrapper.is-focused),
:deep(.el-textarea__inner:focus) {
  border-color: #2c5cc5;
  box-shadow: 0 0 0 2px rgba(44, 92, 197, 0.08);
}

:deep(.el-radio),
:deep(.el-checkbox) {
  margin-right: 0;
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid #d7deea;
  border-radius: 999px;
  background: #f9fbff;
}
</style>
