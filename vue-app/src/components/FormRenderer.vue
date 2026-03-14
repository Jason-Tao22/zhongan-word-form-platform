<template>
  <div class="form-renderer">
    <div class="renderer-hero">
      <div>
        <div class="hero-eyebrow">ERP Form Workspace</div>
        <h1 class="hero-title">{{ schema.templateName }}</h1>
        <p class="hero-subtitle">
          保留 Word 段落与表格结构，同时提供正式录入控件。提交前仍建议走人工复核。
        </p>
      </div>
      <div v-if="showActions" class="hero-actions">
        <el-button @click="handleSaveDraft">保存草稿</el-button>
        <el-button type="primary" @click="handleSubmit">提交审核</el-button>
      </div>
    </div>

    <template v-if="hasDocumentBlocks">
      <section class="document-shell">
        <template v-for="(block, blockIndex) in schema.documentBlocks" :key="`doc-block-${blockIndex}`">
          <div
            v-if="block.kind === 'paragraph'"
            :data-review-id="paragraphSlotReviewId(blockIndex, null, null, 0)"
            :class="reviewTargetClasses(paragraphSlotReviewId(blockIndex, null, null, 0), paragraphClasses(block))"
            @click="emitReviewSelect(paragraphSlotReviewId(blockIndex, null, null, 0))"
            @mouseenter="emitReviewHover(paragraphSlotReviewId(blockIndex, null, null, 0))"
            @mouseleave="emitReviewHover('')"
          >
            <template v-for="(token, tokenIndex) in block.tokens || []" :key="`p-${blockIndex}-${tokenIndex}`">
              <span v-if="token.kind === 'text'">{{ token.text }}</span>
              <span
                v-else-if="token.kind === 'inline-choice'"
                :data-review-id="tokenReviewId(blockIndex, null, null, 0, tokenIndex)"
                :class="reviewTargetClasses(tokenReviewId(blockIndex, null, null, 0, tokenIndex), 'inline-choice-group')"
                @click.stop="emitReviewSelect(tokenReviewId(blockIndex, null, null, 0, tokenIndex))"
                @focusin="emitReviewSelect(tokenReviewId(blockIndex, null, null, 0, tokenIndex))"
                @mouseenter="emitReviewHover(tokenReviewId(blockIndex, null, null, 0, tokenIndex))"
                @mouseleave="emitReviewHover('')"
              >
                <label
                  v-for="option in token.options || []"
                  :key="`${token.key}-${option}`"
                  class="inline-choice-item"
                >
                  <input
                    :type="token.choiceType === 'checkbox_group' ? 'checkbox' : 'radio'"
                    :name="token.choiceType === 'checkbox_group' ? undefined : token.key"
                    :value="option"
                    :checked="isInlineChoiceSelected(token, option)"
                    @click="handleInlineChoiceClick(token, option, $event)"
                  >
                  <span>{{ option }}</span>
                </label>
                <button
                  v-if="canClearInlineChoice(token)"
                  type="button"
                  class="choice-clear"
                  @click="clearInlineChoice(token)"
                >
                  清空
                </button>
              </span>
              <input
                v-else
                :data-review-id="tokenReviewId(blockIndex, null, null, 0, tokenIndex)"
                :class="reviewTargetClasses(tokenReviewId(blockIndex, null, null, 0, tokenIndex), 'inline-fill')"
                type="text"
                :style="{ width: `${token.widthEm}em` }"
                :value="getTokenValue(token)"
                @input="setTokenValue(token, $event.target.value)"
                @focus="emitReviewSelect(tokenReviewId(blockIndex, null, null, 0, tokenIndex))"
                @click.stop="emitReviewSelect(tokenReviewId(blockIndex, null, null, 0, tokenIndex))"
                @mouseenter="emitReviewHover(tokenReviewId(blockIndex, null, null, 0, tokenIndex))"
                @mouseleave="emitReviewHover('')"
              >
            </template>
            <div v-if="block.control" class="paragraph-control-wrap">
              <FieldInput
                v-if="block.control.kind === 'schema'"
                :field="getControlField(block.control)"
                :model-value="getControlValue(block.control)"
                @update:model-value="setControlValue(block.control, $event)"
              />
              <FieldInput
                v-else-if="isStructuredAutoControl(block.control)"
                :field="getAutoControlField(block.control)"
                :model-value="getDocumentValue(block.control.key)"
                @update:model-value="setDocumentValue(block.control.key, $event)"
              />
              <textarea
                v-else-if="block.control.fieldType === 'textarea'"
                class="auto-textarea"
                :style="autoControlStyle(block.control)"
                :value="getDocumentValue(block.control.key)"
                @input="setDocumentValue(block.control.key, $event.target.value)"
              />
              <input
                v-else
                class="auto-input"
                type="text"
                :value="getDocumentValue(block.control.key)"
                @input="setDocumentValue(block.control.key, $event.target.value)"
              >
            </div>
          </div>

          <table v-else-if="block.kind === 'table'" class="word-table document-table">
            <tbody>
              <tr v-for="(row, rowIndex) in block.rows" :key="`t-${blockIndex}-${rowIndex}`">
                <td
                  v-for="(cell, cellIndex) in row"
                  :key="`c-${blockIndex}-${rowIndex}-${cellIndex}`"
                  :colspan="cell.colspan || 1"
                  :rowspan="cell.rowspan || 1"
                  :style="cellStyle(cell.style)"
                  :data-review-id="cellSlotReviewId(blockIndex, rowIndex, cellIndex)"
                  :class="reviewTargetClasses(cellSlotReviewId(blockIndex, rowIndex, cellIndex), documentCellClasses(cell))"
                  @click="emitReviewSelect(cellSlotReviewId(blockIndex, rowIndex, cellIndex))"
                  @mouseenter="emitReviewHover(cellSlotReviewId(blockIndex, rowIndex, cellIndex))"
                  @mouseleave="emitReviewHover('')"
                >
                  <template v-for="(paragraph, paragraphIndex) in cell.paragraphs || []" :key="`cp-${blockIndex}-${rowIndex}-${cellIndex}-${paragraphIndex}`">
                    <div
                      v-if="paragraph.kind === 'blank'"
                      :data-review-id="paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex)"
                      :class="reviewTargetClasses(paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex), ['document-paragraph-line', 'blank-line'])"
                      @click.stop="emitReviewSelect(paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex))"
                      @mouseenter="emitReviewHover(paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex))"
                      @mouseleave="emitReviewHover('')"
                    ></div>
                    <div
                      v-else
                      :data-review-id="paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex)"
                      :class="reviewTargetClasses(paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex), 'document-paragraph-line')"
                      @click.stop="emitReviewSelect(paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex))"
                      @mouseenter="emitReviewHover(paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex))"
                      @mouseleave="emitReviewHover('')"
                    >
                      <template v-for="(token, tokenIndex) in paragraph.tokens || []" :key="`ct-${blockIndex}-${rowIndex}-${cellIndex}-${paragraphIndex}-${tokenIndex}`">
                        <span v-if="token.kind === 'text'">{{ token.text }}</span>
                        <span
                          v-else-if="token.kind === 'inline-choice'"
                          :data-review-id="tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex)"
                          :class="reviewTargetClasses(tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex), 'inline-choice-group')"
                          @click.stop="emitReviewSelect(tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex))"
                          @focusin="emitReviewSelect(tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex))"
                          @mouseenter="emitReviewHover(tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex))"
                          @mouseleave="emitReviewHover('')"
                        >
                          <label
                            v-for="option in token.options || []"
                            :key="`${token.key}-${option}`"
                            class="inline-choice-item"
                          >
                            <input
                              :type="token.choiceType === 'checkbox_group' ? 'checkbox' : 'radio'"
                              :name="token.choiceType === 'checkbox_group' ? undefined : token.key"
                              :value="option"
                              :checked="isInlineChoiceSelected(token, option)"
                              @click="handleInlineChoiceClick(token, option, $event)"
                            >
                            <span>{{ option }}</span>
                          </label>
                          <button
                            v-if="canClearInlineChoice(token)"
                            type="button"
                            class="choice-clear"
                            @click="clearInlineChoice(token)"
                          >
                            清空
                          </button>
                        </span>
                        <input
                          v-else
                          :data-review-id="tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex)"
                          :class="reviewTargetClasses(tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex), 'inline-fill')"
                          type="text"
                          :style="{ width: `${token.widthEm}em` }"
                          :value="getTokenValue(token)"
                          @input="setTokenValue(token, $event.target.value)"
                          @focus="emitReviewSelect(tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex))"
                          @click.stop="emitReviewSelect(tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex))"
                          @mouseenter="emitReviewHover(tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex))"
                          @mouseleave="emitReviewHover('')"
                        >
                      </template>
                      <div v-if="paragraph.control" class="paragraph-control-wrap">
                        <FieldInput
                          v-if="paragraph.control.kind === 'schema'"
                          :field="getControlField(paragraph.control)"
                          :model-value="getControlValue(paragraph.control)"
                          @update:model-value="setControlValue(paragraph.control, $event)"
                        />
                        <FieldInput
                          v-else-if="isStructuredAutoControl(paragraph.control)"
                          :field="getAutoControlField(paragraph.control)"
                          :model-value="getDocumentValue(paragraph.control.key)"
                          @update:model-value="setDocumentValue(paragraph.control.key, $event)"
                        />
                        <textarea
                          v-else-if="paragraph.control.fieldType === 'textarea'"
                          class="auto-textarea"
                          :style="autoControlStyle(paragraph.control)"
                          :value="getDocumentValue(paragraph.control.key)"
                          @input="setDocumentValue(paragraph.control.key, $event.target.value)"
                        />
                        <input
                          v-else
                          class="auto-input"
                          type="text"
                          :value="getDocumentValue(paragraph.control.key)"
                          @input="setDocumentValue(paragraph.control.key, $event.target.value)"
                        >
                      </div>
                    </div>
                  </template>

                  <div v-if="cell.control" class="auto-control-wrap">
                    <template v-if="getControlField(cell.control).type === 'static'"></template>
                    <FieldInput
                      v-else-if="cell.control.kind === 'schema'"
                      :field="getControlField(cell.control)"
                      :model-value="getControlValue(cell.control)"
                      @update:model-value="setControlValue(cell.control, $event)"
                    />
                    <FieldInput
                      v-else-if="isStructuredAutoControl(cell.control)"
                      :field="getAutoControlField(cell.control)"
                      :model-value="getDocumentValue(cell.control.key)"
                      @update:model-value="setDocumentValue(cell.control.key, $event)"
                    />
                    <textarea
                      v-else-if="cell.control.fieldType === 'textarea'"
                      class="auto-textarea"
                      :style="autoControlStyle(cell.control)"
                      :value="getDocumentValue(cell.control.key)"
                      @input="setDocumentValue(cell.control.key, $event.target.value)"
                    />
                    <input
                      v-else
                      class="auto-input"
                      type="text"
                      :value="getDocumentValue(cell.control.key)"
                      @input="setDocumentValue(cell.control.key, $event.target.value)"
                    >
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </section>
    </template>

    <template v-else>
      <section
        v-for="subForm in schema.subForms"
        :key="subForm.id"
        class="sub-form-block"
      >
        <header class="sub-form-header">
          <div>
            <h2 class="sub-form-title">{{ subForm.name }}</h2>
            <p class="sub-form-meta">
              {{ subForm.layout.type }} / {{ subForm.recordType }} / {{ subForm.sqlTableName }}
            </p>
          </div>
        </header>

        <table v-if="subForm.layout.type === 'key-value'" class="word-table">
          <tbody>
            <tr v-for="(row, ri) in subForm.layout.rows" :key="ri">
              <template v-for="(cell, ci) in row" :key="`${ri}-${ci}`">
                <td
                  v-if="cell.kind === 'label'"
                  class="td-label"
                  :colspan="cell.colspan || 1"
                  :rowspan="cell.rowspan || 1"
                  :style="cellStyle(cell.style)"
                >
                  {{ cell.text }}
                </td>
                <td
                  v-else-if="cell.kind === 'input'"
                  class="td-input"
                  :colspan="cell.colspan || 1"
                  :rowspan="cell.rowspan || 1"
                  :style="cellStyle(cell.style)"
                >
                  <FieldInput
                    :field="getField(subForm, cell.fieldId)"
                    v-model="formData[subForm.id][cell.fieldId]"
                  />
                </td>
                <td
                  v-else
                  class="td-static"
                  :colspan="cell.colspan || 1"
                  :rowspan="cell.rowspan || 1"
                  :style="cellStyle(cell.style)"
                >
                  {{ cell.text }}
                </td>
              </template>
            </tr>
          </tbody>
        </table>

        <template v-else-if="subForm.layout.type === 'data-grid'">
          <table
            v-if="subForm.layout.prefixFields && subForm.layout.prefixFields.length"
            class="word-table prefix-table"
          >
            <tbody>
              <tr
                v-for="(row, rowIndex) in getPrefixRows(subForm)"
                :key="`prefix-${rowIndex}`"
              >
                <template v-for="field in row" :key="field.id">
                  <td class="td-label">{{ field.label }}</td>
                  <td class="td-input">
                    <FieldInput
                      :field="field"
                      v-model="formData[subForm.id]._prefix[field.id]"
                    />
                  </td>
                </template>
              </tr>
            </tbody>
          </table>

          <table class="word-table">
            <thead>
              <tr v-for="(headerRow, hi) in subForm.layout.headers" :key="`header-${hi}`">
                <th
                  v-for="(hCell, hci) in headerRow"
                  :key="`header-${hi}-${hci}`"
                  class="th-header"
                  :colspan="hCell.colspan || 1"
                  :rowspan="hCell.rowspan || 1"
                  :style="cellStyle(hCell.style)"
                >
                  {{ hCell.text }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(dataRow, ri) in formData[subForm.id]._rows"
                :key="`row-${ri}`"
              >
                <td
                  v-for="fieldId in gridColumns(subForm)"
                  :key="`${ri}-${fieldId}`"
                  class="td-input grid-cell"
                >
                  <FieldInput
                    :field="getField(subForm, fieldId)"
                    v-model="dataRow[fieldId]"
                  />
                </td>
              </tr>
            </tbody>
          </table>
          <div class="grid-actions">
            <el-button size="small" @click="addRow(subForm)">新增一行</el-button>
            <el-button size="small" @click="removeLastRow(subForm)">删除最后一行</el-button>
          </div>
        </template>

        <table v-else-if="subForm.layout.type === 'checklist'" class="word-table">
          <thead>
            <tr>
              <template v-if="hasChecklistSubItems(subForm)">
                <th class="th-header">{{ checklistHeader(subForm, 0) }}</th>
                <th class="th-header">{{ checklistHeader(subForm, 1) }}</th>
                <th class="th-header">子项</th>
                <th class="th-header">{{ checklistHeader(subForm, 2) }}</th>
                <th class="th-header">{{ checklistHeader(subForm, 3) }}</th>
              </template>
              <template v-else>
                <th
                  v-for="(col, colIndex) in subForm.layout.columns"
                  :key="`check-col-${colIndex}`"
                  class="th-header"
                >
                  {{ col }}
                </th>
              </template>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="(item, itemIndex) in subForm.layout.items"
              :key="`${itemIndex}-${item.fieldId || item.label}`"
            >
              <tr v-if="!item.subItems">
                <td class="td-label seq-col">{{ item.seq }}</td>
                <td
                  class="td-label align-left"
                  :colspan="hasChecklistSubItems(subForm) ? 2 : 1"
                >
                  {{ item.label }}
                </td>
                <td class="td-input">
                  <FieldInput
                    :field="getField(subForm, item.fieldId)"
                    v-model="formData[subForm.id][item.fieldId]"
                  />
                </td>
                <td class="td-input">
                  <FieldInput
                    v-if="item.remarkFieldId"
                    :field="getField(subForm, item.remarkFieldId)"
                    v-model="formData[subForm.id][item.remarkFieldId]"
                  />
                </td>
              </tr>

              <template v-else>
                <tr
                  v-for="(sub, si) in item.subItems"
                  :key="`${itemIndex}-${si}-${sub.fieldId || sub.label}`"
                >
                  <td
                    v-if="si === 0"
                    class="td-label seq-col"
                    :rowspan="item.subItems.length"
                  >
                    {{ item.seq }}
                  </td>
                  <td
                    v-if="si === 0"
                    class="td-label align-left"
                    :rowspan="item.subItems.length"
                  >
                    {{ item.label }}
                  </td>
                  <td class="td-label align-left sub-label">
                    {{ sub.label }}
                  </td>
                  <td class="td-input">
                    <FieldInput
                      :field="getField(subForm, sub.fieldId)"
                      v-model="formData[subForm.id][sub.fieldId]"
                    />
                  </td>
                  <td class="td-input">
                    <FieldInput
                      v-if="sub.remarkFieldId"
                      :field="getField(subForm, sub.remarkFieldId)"
                      v-model="formData[subForm.id][sub.remarkFieldId]"
                    />
                  </td>
                </tr>
              </template>
            </template>
          </tbody>
        </table>

        <table v-else-if="subForm.layout.type === 'section-group'" class="word-table">
          <tbody>
            <template
              v-for="(section, sectionIndex) in subForm.layout.sections"
              :key="`${sectionIndex}-${section.title}`"
            >
              <tr>
                <td
                  class="td-section-title"
                  :colspan="getSectionColspan(section)"
                  :style="cellStyle(section.titleStyle)"
                >
                  {{ section.title }}
                </td>
              </tr>
              <tr
                v-for="(row, ri) in section.rows"
                :key="`${sectionIndex}-${ri}`"
              >
                <template v-for="item in row" :key="item.fieldId">
                  <td
                    v-if="isStaticField(subForm, item.fieldId)"
                    class="td-static td-static-block"
                    :colspan="(item.labelColspan || 1) + (item.colspan || 1)"
                    :style="cellStyle(item.inputStyle || item.labelStyle)"
                  >
                    {{ item.label }}
                  </td>
                  <td
                    v-else
                    class="td-label"
                    :colspan="item.labelColspan || 1"
                    :style="cellStyle(item.labelStyle)"
                  >
                    {{ item.label }}
                  </td>
                  <td
                    v-if="!isStaticField(subForm, item.fieldId)"
                    class="td-input"
                    :colspan="item.colspan || 1"
                    :style="cellStyle(item.inputStyle)"
                  >
                    <FieldInput
                      :field="getField(subForm, item.fieldId)"
                      v-model="formData[subForm.id][item.fieldId]"
                    />
                  </td>
                </template>
              </tr>
            </template>
          </tbody>
        </table>
      </section>
    </template>

    <footer v-if="showActions" class="form-footer">
      <div class="footer-note">
        当前页面会同时保存结构化字段与原始文档补充填写内容，避免 Word 特殊空白位在正式页丢失。
      </div>
      <div class="hero-actions">
        <el-button @click="handleSaveDraft">保存草稿</el-button>
        <el-button type="primary" @click="handleSubmit">提交审核</el-button>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import FieldInput from './FieldInput.vue'

const props = defineProps({
  schema: { type: Object, required: true },
  showActions: { type: Boolean, default: true },
  activeReviewTargetId: { type: String, default: '' },
  hoverReviewTargetId: { type: String, default: '' },
})

const emit = defineEmits(['submit', 'save-draft', 'preview-select', 'preview-hover'])

const hasDocumentBlocks = computed(
  () => Array.isArray(props.schema.documentBlocks) && props.schema.documentBlocks.length > 0,
)

function initFormData(schema) {
  const data = {
    __document: {},
  }

  for (const subForm of schema.subForms) {
    data[subForm.id] = {}

    if (subForm.layout.type === 'data-grid') {
      data[subForm.id]._prefix = {}
      for (const field of subForm.fields.filter(field => field.isPrefix)) {
        data[subForm.id]._prefix[field.id] = field.type === 'checkbox_group' ? [] : null
      }
      data[subForm.id]._rows = makeEmptyRows(subForm, subForm.layout.defaultRowCount || 5)
      normalizeGridSequence(subForm, data[subForm.id]._rows)
    } else {
      for (const field of subForm.fields) {
        if (field.type !== 'static') {
          data[subForm.id][field.id] = field.type === 'checkbox_group' ? [] : null
        }
      }
    }
  }

  return data
}

function resolveFieldDefault(field) {
  return field?.type === 'checkbox_group' ? [] : null
}

function looksLikeSequenceField(field) {
  if (!field) return false
  return ['seq', 'serial_no', 'serial_number', 'row_no', 'no'].includes(field.id)
    || /序号|编号/.test(field.label || '')
}

function makeEmptyRow(subForm, rowIndex) {
  const row = {}
  for (const fieldId of gridColumns(subForm)) {
    const field = getField(subForm, fieldId)
    if (rowIndex >= 0 && looksLikeSequenceField(field)) {
      row[fieldId] = field.type === 'number' ? rowIndex + 1 : String(rowIndex + 1)
    } else {
      row[fieldId] = resolveFieldDefault(field)
    }
  }
  return row
}

function makeEmptyRows(subForm, count) {
  return Array.from({ length: count }, (_, index) => makeEmptyRow(subForm, index))
}

const formData = reactive(initFormData(props.schema))

watch(() => props.schema, (newSchema) => {
  const fresh = initFormData(newSchema)
  Object.keys(formData).forEach(key => delete formData[key])
  Object.assign(formData, fresh)
}, { deep: false })

function getField(subForm, fieldId) {
  return subForm.fields.find(field => field.id === fieldId)
    || { id: fieldId, label: fieldId, type: 'text' }
}

function getSubFormById(subFormId) {
  return props.schema.subForms.find(subForm => subForm.id === subFormId)
}

function isStaticField(subForm, fieldId) {
  return getField(subForm, fieldId)?.type === 'static'
}

function gridColumns(subForm) {
  return subForm.layout.dataColumns || []
}

function getPrefixRows(subForm) {
  const prefixFields = subForm.fields.filter(field => field.isPrefix)
  const rows = []
  for (let index = 0; index < prefixFields.length; index += 2) {
    rows.push(prefixFields.slice(index, index + 2))
  }
  return rows
}

function hasChecklistSubItems(subForm) {
  return subForm.layout.items?.some(item => item.subItems?.length) || false
}

function checklistHeader(subForm, index) {
  return subForm.layout.columns?.[index] || ''
}

function normalizeGridSequence(subForm, rows) {
  const firstFieldId = gridColumns(subForm)[0]
  const firstField = getField(subForm, firstFieldId)
  if (!looksLikeSequenceField(firstField)) {
    return
  }
  rows.forEach((row, index) => {
    row[firstFieldId] = firstField.type === 'number' ? index + 1 : String(index + 1)
  })
}

function addRow(subForm) {
  const rows = formData[subForm.id]._rows
  rows.push(makeEmptyRow(subForm, rows.length))
  normalizeGridSequence(subForm, rows)
}

function removeLastRow(subForm) {
  const rows = formData[subForm.id]._rows
  if (rows.length <= 1) return
  rows.pop()
  normalizeGridSequence(subForm, rows)
}

function getSectionColspan(section) {
  if (!section.rows || !section.rows[0]) return 4
  return section.rows[0].reduce(
    (sum, item) => sum + (item.colspan || 1) + (item.labelColspan || 1),
    0,
  )
}

function cellStyle(style) {
  if (!style) return undefined
  const result = {}
  if (style.widthPx) {
    result.width = `${style.widthPx}px`
    result.minWidth = `${Math.max(56, style.widthPx)}px`
  }
  if (style.textAlign) result.textAlign = style.textAlign
  if (style.verticalAlign) result.verticalAlign = style.verticalAlign
  if (style.backgroundColor) result.backgroundColor = style.backgroundColor
  if (style.fontWeight === 'bold') result.fontWeight = 700
  return result
}

function paragraphClasses(block) {
  return [
    'document-paragraph',
    `align-${block.align || 'left'}`,
    { 'is-bold': block.isBold, 'is-note': block.text?.startsWith?.('注：') },
  ]
}

function documentCellClasses(cell) {
  return [
    'doc-cell',
    { 'is-emphasis': cell.isEmphasis, 'is-empty': cell.isEmpty },
  ]
}

function tokenReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex, tokenIndex) {
  return `token-${blockIndex}-${rowIndex ?? 'p'}-${cellIndex ?? 'p'}-${paragraphIndex ?? 0}-${tokenIndex}`
}

function cellSlotReviewId(blockIndex, rowIndex, cellIndex) {
  return `cell-${blockIndex}-${rowIndex}-${cellIndex}`
}

function paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex) {
  return `paragraph-${blockIndex}-${rowIndex ?? 'p'}-${cellIndex ?? 'p'}-${paragraphIndex ?? 0}`
}

function reviewTargetClasses(id, baseClass) {
  return [
    ...(Array.isArray(baseClass) ? baseClass : [baseClass]),
    'review-target',
    {
      'is-review-active': props.activeReviewTargetId === id,
      'is-review-hovered': props.hoverReviewTargetId === id && props.activeReviewTargetId !== id,
    },
  ]
}

function emitReviewSelect(id) {
  if (!id) return
  emit('preview-select', { id })
}

function emitReviewHover(id) {
  emit('preview-hover', { id })
}

function getDocumentValue(key) {
  return formData.__document?.[key] ?? ''
}

function setDocumentValue(key, value) {
  formData.__document[key] = value
}

function getTokenFieldBinding(token) {
  if (!token?.fieldId || !token?.subFormId) {
    return null
  }

  const subForm = getSubFormById(token.subFormId)
  if (!subForm || !formData[subForm.id]) {
    return null
  }

  return {
    subForm,
    field: getField(subForm, token.fieldId),
    target: formData[subForm.id],
  }
}

function hasTokenValue(value) {
  if (Array.isArray(value)) {
    return value.length > 0
  }
  return value !== null && value !== undefined && value !== ''
}

function getTokenValue(token) {
  const binding = getTokenFieldBinding(token)
  if (!binding) {
    return getDocumentValue(token.key)
  }

  const structuredValue = binding.target[token.fieldId]
  if (hasTokenValue(structuredValue)) {
    return structuredValue
  }

  const documentValue = getDocumentValue(token.key)
  if (hasTokenValue(documentValue)) {
    return documentValue
  }

  return resolveFieldDefault(binding.field)
}

function setTokenValue(token, value) {
  const binding = getTokenFieldBinding(token)
  if (binding) {
    binding.target[token.fieldId] = value
  }
  setDocumentValue(token.key, value)
}

function isInlineChoiceSelected(token, option) {
  const value = getTokenValue(token)
  if (token.choiceType === 'checkbox_group') {
    return Array.isArray(value) && value.includes(option)
  }
  return value === option
}

function handleInlineChoiceClick(token, option, event) {
  event.preventDefault()
  if (token.choiceType === 'checkbox_group') {
    const currentValue = getTokenValue(token)
    const current = Array.isArray(currentValue)
      ? [...currentValue]
      : []
    const index = current.indexOf(option)
    if (index >= 0) {
      current.splice(index, 1)
    } else {
      current.push(option)
    }
    setDocumentValue(token.key, current)
    return
  }

  if (getTokenValue(token) === option) {
    setTokenValue(token, '')
    return
  }
  setTokenValue(token, option)
}

function canClearInlineChoice(token) {
  const value = getTokenValue(token)
  return token.choiceType === 'checkbox_group'
    ? Array.isArray(value) && value.length > 0
    : Boolean(value)
}

function clearInlineChoice(token) {
  setTokenValue(token, token.choiceType === 'checkbox_group' ? [] : '')
}

function getControlField(control) {
  const subForm = getSubFormById(control.subFormId)
  if (!subForm) {
    return {
      id: control.fieldId,
      label: control.label || control.fieldId,
      type: control.fieldType || 'text',
      options: control.options || [],
    }
  }
  return getField(subForm, control.fieldId)
}

function getAutoControlField(control) {
  return {
    id: control.key,
    label: control.label || control.key,
    type: control.fieldType || 'text',
    options: control.options || [],
  }
}

function isStructuredAutoControl(control) {
  return ['radio', 'checkbox_group', 'select', 'date', 'number'].includes(control.fieldType)
}

function autoControlStyle(control) {
  if (control.fieldType !== 'textarea' || !control.minHeightPx) {
    return undefined
  }
  return { minHeight: `${control.minHeightPx}px` }
}

function ensureControlTarget(control) {
  const subForm = getSubFormById(control.subFormId)
  if (!subForm) return null

  if (control.rowIndex !== null && control.rowIndex !== undefined) {
    if (!Array.isArray(formData[subForm.id]._rows)) {
      formData[subForm.id]._rows = []
    }
    while (formData[subForm.id]._rows.length <= control.rowIndex) {
      formData[subForm.id]._rows.push(makeEmptyRow(subForm, formData[subForm.id]._rows.length))
    }
    return formData[subForm.id]._rows[control.rowIndex]
  }

  return formData[subForm.id]
}

function getControlValue(control) {
  if (control.kind === 'auto') {
    return getDocumentValue(control.key)
  }

  const target = ensureControlTarget(control)
  if (!target) return null
  const field = getControlField(control)
  return target[control.fieldId] ?? resolveFieldDefault(field)
}

function setControlValue(control, value) {
  if (control.kind === 'auto') {
    setDocumentValue(control.key, value)
    return
  }

  const target = ensureControlTarget(control)
  if (!target) return
  target[control.fieldId] = value
}

function handleSubmit() {
  emit('submit', JSON.parse(JSON.stringify(formData)))
}

function handleSaveDraft() {
  emit('save-draft', JSON.parse(JSON.stringify(formData)))
}
</script>

<style scoped>
.form-renderer {
  display: grid;
  gap: 20px;
  color: #1f2937;
}

.renderer-hero,
.sub-form-block,
.form-footer,
.document-shell {
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%);
  border: 1px solid #d7deea;
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.05);
}

.renderer-hero {
  padding: 22px 24px;
  border-radius: 18px;
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}

.hero-eyebrow {
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #2c5cc5;
  margin-bottom: 8px;
}

.hero-title {
  margin: 0;
  font-size: 28px;
  line-height: 1.2;
  font-weight: 700;
}

.hero-subtitle,
.sub-form-meta,
.footer-note {
  margin: 6px 0 0;
  color: #607086;
  font-size: 13px;
  line-height: 1.6;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.document-shell {
  border-radius: 16px;
  padding: 18px 20px;
}

.document-paragraph {
  margin: 6px 0;
  line-height: 1.8;
  white-space: normal;
}

.document-paragraph.is-bold {
  font-weight: 700;
}

.document-paragraph.is-note {
  font-size: 12px;
}

.document-table + .document-paragraph,
.document-paragraph + .document-table,
.document-table + .document-table {
  margin-top: 8px;
}

.document-paragraph-line {
  line-height: 1.75;
}

.blank-line {
  min-height: 1.75em;
}

.inline-fill,
.auto-input,
.auto-textarea {
  border: 1px solid #cfd7e6;
  background: #ffffff;
  color: #1f2937;
  font: inherit;
}

.inline-fill {
  display: inline-block;
  vertical-align: baseline;
  min-width: 3.5em;
  border-top: none;
  border-left: none;
  border-right: none;
  padding: 0 2px 1px;
  line-height: 1.2;
  margin: 0 2px;
}

.review-target {
  transition: box-shadow 140ms ease, background-color 140ms ease, outline-color 140ms ease;
}

.review-target:hover {
  box-shadow: 0 0 0 1px rgba(44, 92, 197, 0.22);
}

.review-target.is-review-hovered {
  background: rgba(44, 92, 197, 0.04);
  box-shadow: 0 0 0 1px rgba(44, 92, 197, 0.24);
  border-radius: 6px;
}

.review-target.is-review-active {
  background: rgba(44, 92, 197, 0.08);
  box-shadow: 0 0 0 2px rgba(44, 92, 197, 0.38);
  border-radius: 6px;
}

.inline-choice-group {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin: 0 4px;
  vertical-align: baseline;
}

.inline-choice-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.choice-clear {
  border: none;
  background: transparent;
  color: #4b5563;
  font: inherit;
  cursor: pointer;
  padding: 0 0 0 4px;
}

.auto-input,
.auto-textarea {
  width: 100%;
  padding: 6px 8px;
}

.auto-textarea {
  min-height: 96px;
  resize: vertical;
}

.auto-control-wrap {
  margin-top: 6px;
}

.paragraph-control-wrap {
  margin-top: 6px;
}

.sub-form-block {
  border-radius: 16px;
  overflow: hidden;
}

.sub-form-header {
  padding: 18px 20px 12px;
  border-bottom: 1px solid #e4eaf2;
  background: linear-gradient(180deg, #f7faff 0%, #f3f7fd 100%);
}

.sub-form-title {
  margin: 0;
  font-size: 18px;
}

.word-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  background: #ffffff;
}

.word-table td,
.word-table th {
  border: 1px solid #cfd7e6;
  padding: 6px 8px;
  vertical-align: middle;
  word-break: break-word;
}

.doc-cell {
  background: #ffffff;
  vertical-align: top;
}

.doc-cell.is-emphasis {
  background: #fafcff;
}

.doc-cell.is-empty {
  background: #ffffff;
}

.td-label,
.th-header,
.td-section-title {
  background: #f5f8fc;
  color: #243043;
  font-weight: 600;
  text-align: center;
}

.td-input {
  background: #ffffff;
}

.td-static {
  background: #f9fbfd;
  color: #5b6b7f;
  white-space: pre-wrap;
}

.td-static-block {
  text-align: left;
  min-height: 84px;
  vertical-align: top;
  line-height: 1.7;
}

.td-section-title {
  background: linear-gradient(180deg, #edf4ff 0%, #e7eefc 100%);
}

.grid-actions {
  display: flex;
  gap: 10px;
  padding: 12px 16px 16px;
  border-top: 1px solid #e7edf6;
  background: #fafcff;
}

.seq-col {
  width: 68px;
}

.align-left {
  text-align: left;
}

.align-center {
  text-align: center;
}

.align-right {
  text-align: right;
}

.align-justify {
  text-align: justify;
}

.sub-label {
  padding-left: 14px;
  font-weight: 500;
}

.form-footer {
  padding: 16px 20px;
  border-radius: 16px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}

@media (max-width: 960px) {
  .renderer-hero,
  .form-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .word-table {
    table-layout: auto;
  }
}
</style>
