<template>
  <div class="page-wrap">
    <div v-if="loading" class="page-card state-card">加载模板基础信息...</div>
    <div v-else-if="error" class="page-card state-card error">{{ error }}</div>
    <template v-else>
      <div class="page-card review-header">
        <div>
          <div class="kicker">Review Workspace</div>
          <h2>{{ template.name }}</h2>
          <p class="muted">{{ template.sourceFile || template.source_file }} / {{ template.status }}</p>
        </div>
        <div class="review-actions">
          <RouterLink to="/" class="inline-link">返回模板列表</RouterLink>
          <el-button
            v-if="canEditSchema"
            :disabled="!schemaDirty || savingSchema"
            @click="resetSchemaEdits"
          >
            重置修改
          </el-button>
          <el-button
            v-if="canEditSchema"
            type="primary"
            :loading="savingSchema"
            :disabled="!schemaDirty"
            @click="saveSchemaAdjustments"
          >
            保存纠错
          </el-button>
          <el-button
            v-if="template.status === 'pending_review'"
            type="success"
            @click="publishTemplate"
          >
            确认发布
          </el-button>
          <el-button
            v-if="template.status === 'failed'"
            type="danger"
            plain
            @click="retryTemplate"
          >
            重新解析
          </el-button>
          <RouterLink
            v-if="template.status === 'active'"
            :to="`/templates/${template.id}/form`"
            class="inline-link"
          >
            打开正式表单
          </RouterLink>
        </div>
      </div>

      <div class="review-grid">
        <div class="review-main">
          <div class="page-card preview-card">
            <div class="card-title">正式渲染预览</div>
            <div v-if="template.status === 'processing'" class="state-card">
              模板正在后台解析中（{{ processingStageLabel }}），页面会自动刷新。{{ processingMeta }}
            </div>
            <div v-else-if="template.status === 'failed' && !hasSchema" class="state-card error">
              解析失败：{{ template.errorMessage || template.error_message || '未返回具体错误' }}
            </div>
            <div v-else-if="schemaLoading" class="state-card">
              模板基础信息已加载，正在后台拉取 schema 和预览内容。大模板第一次打开会更慢一些。
            </div>
            <div v-else-if="schemaError" class="state-card error">
              {{ schemaError }}
            </div>
            <div v-else-if="reviewSchema && shouldDeferHeavyPanels && !rendererReady" class="state-card">
              当前模板块数较多，正式渲染预览已延后加载，避免审核页卡顿。你可以先纠错或直接发布；需要时再手动加载完整预览。
              <div class="deferred-actions">
                <el-button type="primary" plain @click="rendererReady = true">加载正式预览</el-button>
              </div>
            </div>
            <div v-else-if="reviewSchema" class="preview-body">
              <FormRenderer
                :schema="reviewSchema"
                :show-actions="false"
                :active-review-target-id="activeControlId"
                :hover-review-target-id="hoveredControlId"
                @submit="noop"
                @save-draft="noop"
                @preview-select="handlePreviewSelect"
                @preview-hover="handlePreviewHover"
              />
            </div>
            <div v-else class="state-card">当前模板没有可预览的 schema。</div>
          </div>

          <details
            v-if="hasPrototypeSection"
            class="page-card prototype-card"
            @toggle="togglePrototype($event)"
          >
            <summary>原始 HTML 原型</summary>
            <div v-if="contentLoading" class="prototype-placeholder">
              正在加载原始 HTML 原型...
            </div>
            <div v-else-if="contentError" class="prototype-placeholder prototype-error">
              {{ contentError }}
            </div>
            <div v-else-if="!prototypeReady" class="prototype-placeholder">
              原始 HTML 原型按需加载，避免大模板审核页卡顿。
            </div>
            <iframe
              v-else
              :srcdoc="prototypeHtml"
              class="preview-frame"
            />
          </details>
        </div>

        <div class="review-side">
          <div class="page-card detail-card">
            <div class="card-title">控件纠错</div>
            <p class="panel-note">
              这里改的是模板渲染语义，不是随便改文案。优先修正 `text / textarea / radio / checkbox_group / date / number / select`
              的误判，保存后正式表单页会直接吃这份 schema。
            </p>
            <p class="panel-note" v-if="schemaDirty">当前有未保存修改。</p>
            <p class="panel-note" v-else-if="canEditSchema">当前没有未保存修改。</p>
            <p class="panel-note" v-else>当前状态只读；如需纠错，请在 `pending_review` 或 `failed` 阶段处理。</p>
            <div v-if="selectedControl" class="active-control-banner">
              <div>
                <strong>当前定位：</strong>{{ selectedControl.label }}
                <span class="active-control-meta">{{ selectedControl.location }}</span>
              </div>
              <div class="active-control-actions">
                <el-button text @click="scrollPreviewIntoView(selectedControl.id)">定位左侧预览</el-button>
                <el-button text @click="focusControlEditor(selectedControl.id)">聚焦右侧编辑</el-button>
              </div>
            </div>
            <div v-if="selectedStyleItem" class="style-adjust-panel">
              <div class="manual-panel-title">样式微调</div>
              <p class="panel-note">
                这里改的是当前选中区域的视觉样式。无论是自动识别出来的控件，还是静态标题、段落、单元格，保存后左侧正式渲染预览都会立刻同步。
              </p>
              <div class="style-grid">
                <div class="style-field" data-style-field="fontFamily">
                  <span class="style-field-label">字体</span>
                  <el-input
                    :model-value="selectedStyle.fontFamily"
                    class="control-input"
                    :disabled="!canEditSchema"
                    placeholder="如：宋体 / 黑体 / 仿宋"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'fontFamily', $event)"
                  />
                </div>

                <div class="style-field" data-style-field="fontSizePx">
                  <span class="style-field-label">字号</span>
                  <el-input-number
                    :model-value="selectedStyle.fontSizePx ?? undefined"
                    class="control-input"
                    :min="10"
                    :max="48"
                    :step="1"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'fontSizePx', $event)"
                  />
                </div>

                <div v-if="selectedStyleSupportsCellLayout" class="style-field" data-style-field="widthPx">
                  <span class="style-field-label">列宽</span>
                  <el-input-number
                    :model-value="selectedStyle.widthPx ?? undefined"
                    class="control-input"
                    :min="40"
                    :max="1600"
                    :step="10"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'widthPx', $event)"
                  />
                </div>

                <div class="style-field" data-style-field="minHeightPx">
                  <span class="style-field-label">最小高度</span>
                  <el-input-number
                    :model-value="selectedStyle.minHeightPx ?? undefined"
                    class="control-input"
                    :min="24"
                    :max="1200"
                    :step="10"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'minHeightPx', $event)"
                  />
                </div>

                <div class="style-field" data-style-field="lineHeight">
                  <span class="style-field-label">行高</span>
                  <el-input-number
                    :model-value="selectedStyle.lineHeight ?? undefined"
                    class="control-input"
                    :min="1"
                    :max="3"
                    :step="0.1"
                    :precision="1"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'lineHeight', $event)"
                  />
                </div>

                <div class="style-field" data-style-field="marginTopPx">
                  <span class="style-field-label">段前距</span>
                  <el-input-number
                    :model-value="selectedStyle.marginTopPx ?? undefined"
                    class="control-input"
                    :min="0"
                    :max="120"
                    :step="2"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'marginTopPx', $event)"
                  />
                </div>

                <div class="style-field" data-style-field="marginBottomPx">
                  <span class="style-field-label">段后距</span>
                  <el-input-number
                    :model-value="selectedStyle.marginBottomPx ?? undefined"
                    class="control-input"
                    :min="0"
                    :max="120"
                    :step="2"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'marginBottomPx', $event)"
                  />
                </div>

                <div
                  v-if="selectedStyleSupportsParagraphIndent"
                  class="style-field"
                  data-style-field="marginLeftPx"
                >
                  <span class="style-field-label">左缩进</span>
                  <el-input-number
                    :model-value="selectedStyle.marginLeftPx ?? undefined"
                    class="control-input"
                    :min="0"
                    :max="240"
                    :step="2"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'marginLeftPx', $event)"
                  />
                </div>

                <div
                  v-if="selectedStyleSupportsParagraphIndent"
                  class="style-field"
                  data-style-field="marginRightPx"
                >
                  <span class="style-field-label">右缩进</span>
                  <el-input-number
                    :model-value="selectedStyle.marginRightPx ?? undefined"
                    class="control-input"
                    :min="0"
                    :max="240"
                    :step="2"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'marginRightPx', $event)"
                  />
                </div>

                <div
                  v-if="selectedStyleSupportsParagraphIndent"
                  class="style-field"
                  data-style-field="textIndentPx"
                >
                  <span class="style-field-label">首行缩进</span>
                  <el-input-number
                    :model-value="selectedStyle.textIndentPx ?? undefined"
                    class="control-input"
                    :min="-120"
                    :max="240"
                    :step="2"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'textIndentPx', $event)"
                  />
                </div>

                <div class="style-field" data-style-field="textAlign">
                  <span class="style-field-label">水平对齐</span>
                  <el-select
                    :model-value="selectedStyle.textAlign || ''"
                    class="control-input"
                    :disabled="!canEditSchema"
                    placeholder="文字对齐"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'textAlign', $event)"
                  >
                    <el-option
                      v-for="option in ALIGN_OPTIONS"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </div>

                <div class="style-field style-field-switch" data-style-field="fontWeight">
                  <span class="style-field-label">字重</span>
                  <el-switch
                    :model-value="selectedStyle.fontWeight === 'bold'"
                    :disabled="!canEditSchema"
                    inline-prompt
                    active-text="加粗"
                    inactive-text="常规"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'fontWeight', $event ? 'bold' : 'normal')"
                  />
                </div>

                <div v-if="selectedStyleSupportsCellLayout" class="style-field" data-style-field="verticalAlign">
                  <span class="style-field-label">垂直对齐</span>
                  <el-select
                    :model-value="selectedStyle.verticalAlign || ''"
                    class="control-input"
                    :disabled="!canEditSchema"
                    placeholder="垂直对齐"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'verticalAlign', $event)"
                  >
                    <el-option
                      v-for="option in VERTICAL_ALIGN_OPTIONS"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                </div>

                <div v-if="selectedStyleSupportsCellLayout" class="style-field" data-style-field="backgroundColor">
                  <span class="style-field-label">底色</span>
                  <el-input
                    :model-value="selectedStyle.backgroundColor || ''"
                    class="control-input"
                    :disabled="!canEditSchema"
                    placeholder="如：#fff7e6"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'backgroundColor', $event)"
                  />
                </div>

                <div v-if="selectedStyleSupportsCellLayout" class="style-field" data-style-field="borderBox">
                  <span class="style-field-label">统一边框</span>
                  <el-input
                    :model-value="selectedStyle.borderBox || ''"
                    class="control-input"
                    :disabled="!canEditSchema"
                    placeholder="如：1px solid #000000"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'borderBox', $event)"
                  />
                </div>

                <div v-if="selectedStyleSupportsCellLayout" class="style-field" data-style-field="paddingPx">
                  <span class="style-field-label">内边距</span>
                  <el-input-number
                    :model-value="selectedStyle.paddingPx ?? undefined"
                    class="control-input"
                    :min="0"
                    :max="48"
                    :step="1"
                    :disabled="!canEditSchema"
                    @update:model-value="updateItemStyle(selectedStyleItem, 'paddingPx', $event)"
                  />
                </div>
              </div>
            </div>
            <div v-else-if="selectedTarget" class="active-control-banner">
              <div>
                <strong>当前定位：</strong>{{ selectedTarget.label }}
                <span class="active-control-meta">{{ selectedTarget.location }}</span>
              </div>
              <div class="active-control-actions">
                <el-button text @click="scrollPreviewIntoView(selectedTarget.id)">定位左侧预览</el-button>
                <el-button text @click="focusControlEditor(selectedTarget.id)">聚焦右侧补录</el-button>
              </div>
            </div>

            <div
              v-if="canCreateManualControl"
              :data-control-id="selectedTarget.id"
              class="manual-control-panel"
            >
              <div class="manual-panel-title">手工补控件</div>
              <p class="panel-note">
                这块区域当前没有被自动识别成控件。你可以在这里补一个正式字段，保存后左侧预览会立即回显，发布后的正式表单页也会直接使用它。
              </p>

              <el-input
                v-model="manualControlDraft.label"
                class="control-input"
                :disabled="!canEditSchema"
                placeholder="控件名称，如：问题和意见 / 使用单位代表 / 日期"
              />

              <el-select
                v-model="manualControlDraft.type"
                class="control-input"
                :disabled="!canEditSchema"
              >
                <el-option
                  v-for="option in manualControlTypeOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>

              <el-input
                v-if="manualDraftSupportsOptions"
                v-model="manualControlDraft.optionsText"
                class="control-input"
                :disabled="!canEditSchema"
                placeholder="选项用逗号分隔，如：合格,整改,不合格"
              />

              <el-input-number
                v-if="manualDraftSupportsMinHeight"
                v-model="manualControlDraft.minHeightPx"
                class="control-input"
                :min="80"
                :max="1200"
                :step="20"
                :disabled="!canEditSchema"
              />

              <div class="manual-panel-actions">
                <el-button
                  type="primary"
                  :disabled="!canEditSchema || !manualControlDraft.label.trim()"
                  @click="addManualControl"
                >
                  补到这里
                </el-button>
                <el-button text @click="resetManualControlDraft">恢复推荐</el-button>
              </div>
            </div>
            <div v-else-if="selectedTarget && !selectedControl" class="state-card">
              当前已定位到一个未识别区域，但当前模板状态只读，不能手工补控件。
            </div>

            <div v-if="editableControls.length" class="control-list">
              <div
                v-for="item in editableControls"
                :key="item.id"
                :data-control-id="item.id"
                :class="['control-item', { 'is-active': item.id === activeControlId, 'is-hovered': item.id === hoveredControlId }]"
                @click="handleControlItemClick(item)"
                @mouseenter="handleControlHover(item.id)"
                @mouseleave="handleControlHover('')"
              >
                <div class="control-head">
                  <strong>{{ item.label }}</strong>
                  <span>{{ item.location }}</span>
                </div>
                <div class="control-meta">
                  <span v-if="item.fieldId">字段ID：{{ item.fieldId }}</span>
                  <span v-if="item.sqlColumn">SQL列：{{ item.sqlColumn }}</span>
                  <span v-if="item.placeholder">占位符：{{ item.placeholder }}</span>
                </div>

                <el-select
                  :model-value="item.type"
                  size="small"
                  class="control-input"
                  :disabled="!canEditSchema"
                  @update:model-value="updateControlType(item, $event)"
                >
                  <el-option
                    v-for="option in item.typeOptions"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>

                <el-input
                  v-if="item.supportsOptions"
                  :model-value="item.optionsText"
                  size="small"
                  class="control-input"
                  :disabled="!canEditSchema"
                  placeholder="选项用逗号分隔，如：合格,整改,不合格"
                  @update:model-value="updateControlOptions(item, $event)"
                />

                <el-input-number
                  v-if="item.supportsMinHeight"
                  :model-value="item.minHeightPx"
                  size="small"
                  class="control-input"
                  :min="80"
                  :max="1200"
                  :step="20"
                  :disabled="!canEditSchema"
                  @update:model-value="updateControlMinHeight(item, $event)"
                />
              </div>
            </div>
            <div v-else-if="!selectedTarget" class="state-card">
              当前模板没有可直接纠错的控件项；如果模板仍有问题，优先检查 parser 是否还在 `processing`。
            </div>
          </div>

          <div class="page-card detail-card">
            <div class="card-title">模板摘要</div>
            <ul class="meta-list">
              <li>模板 ID：{{ template.id }}</li>
              <li>创建人：{{ template.createdBy || template.created_by || 'admin' }}</li>
              <li>子表数量：{{ template.subFormCount || template.sub_form_count }}</li>
              <li>存储表数量：{{ template.storageTableCount || template.storage_table_count }}</li>
              <li>分析模式：{{ template.analysisMode || template.analysis_mode }}</li>
              <li>处理阶段：{{ processingStageLabel }}</li>
              <li>处理耗时：{{ resolvedProcessingDuration }}</li>
              <li v-if="template.qualityWarning || template.quality_warning">质量风险：{{ template.qualityWarning || template.quality_warning }}</li>
              <li>结构指纹：{{ template.structureFingerprint || template.structure_fingerprint }}</li>
              <li>状态：{{ template.status }}</li>
              <li v-if="template.errorMessage || template.error_message">错误信息：{{ template.errorMessage || template.error_message }}</li>
            </ul>
            <div class="card-title">DDL</div>
            <div v-if="contentLoading" class="state-card">正在加载 DDL...</div>
            <div v-else-if="contentError" class="state-card error">{{ contentError }}</div>
            <pre v-else-if="displayedDdl" class="code-block">{{ displayedDdl }}</pre>
            <div v-else class="state-card">当前模板没有可展示的 DDL。</div>
            <el-button
              v-if="isDdlTruncated"
              class="ddl-toggle"
              text
              @click="ddlExpanded = !ddlExpanded"
            >
              {{ ddlExpanded ? '收起 DDL' : '展开完整 DDL' }}
            </el-button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiFetch } from '../api/client'
import FormRenderer from '../components/FormRenderer.vue'

const route = useRoute()
const router = useRouter()

const template = ref(null)
const reviewSchema = ref(null)
const baselineSchemaJson = ref('')
const loading = ref(true)
const schemaLoading = ref(false)
const schemaError = ref(null)
const contentLoading = ref(false)
const contentError = ref(null)
const error = ref(null)
const savingSchema = ref(false)
const rendererReady = ref(true)
const prototypeReady = ref(false)
const ddlExpanded = ref(false)
const prototypeHtml = ref('')
const ddlSql = ref('')
const activeControlId = ref('')
const hoveredControlId = ref('')
const manualControlDraft = reactive({
  label: '',
  type: 'text',
  optionsText: '',
  minHeightPx: 180,
})
let pollTimer = null
let clockTimer = null
const nowTick = ref(Date.now())

const FIELD_TYPE_OPTIONS = [
  { value: 'static', label: '静态文本' },
  { value: 'text', label: '单行输入' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
  { value: 'date', label: '日期' },
  { value: 'radio', label: '单选组' },
  { value: 'checkbox_group', label: '多选组' },
  { value: 'select', label: '下拉选择' },
]

const TOKEN_TYPE_OPTIONS = [
  { value: 'text', label: '行内输入' },
  { value: 'radio', label: '行内单选' },
  { value: 'checkbox_group', label: '行内多选' },
]
const ALIGN_OPTIONS = [
  { value: 'left', label: '左对齐' },
  { value: 'center', label: '居中' },
  { value: 'right', label: '右对齐' },
  { value: 'justify', label: '两端对齐' },
]
const VERTICAL_ALIGN_OPTIONS = [
  { value: 'top', label: '顶部' },
  { value: 'middle', label: '居中' },
  { value: 'bottom', label: '底部' },
]
const manualControlTypeOptions = FIELD_TYPE_OPTIONS.filter(option => option.value !== 'static')

const canEditSchema = computed(() => ['pending_review', 'failed'].includes(template.value?.status))
const hasSchema = computed(() => Array.isArray(reviewSchema.value?.subForms))
const schemaDirty = computed(() => {
  if (!reviewSchema.value || !baselineSchemaJson.value) return false
  return JSON.stringify(reviewSchema.value) !== baselineSchemaJson.value
})
const processingStageLabel = computed(() => ({
  queued: '排队中',
  parsing_word: '解析 Word / AI分析中',
  building_schema: '生成 Schema / DDL 中',
  review_ready: '待审核',
  active: '已发布',
  failed: '失败',
  inactive: '已停用',
}[template.value?.processingStage || template.value?.processing_stage || template.value?.status] || '未知'))
const resolvedProcessingDuration = computed(() => {
  const duration = template.value?.processingDurationSeconds ?? template.value?.processing_duration_seconds
  if (duration) return formatSeconds(duration)
  if (template.value?.status === 'processing') {
    const createdAt = template.value?.createdAt || template.value?.created_at
    if (createdAt) {
      const seconds = Math.max(1, Math.round((nowTick.value - new Date(createdAt).getTime()) / 1000))
      return `已等待 ${formatSeconds(seconds)}`
    }
  }
  return '未记录'
})
const processingMeta = computed(() => {
  const risk = template.value?.qualityWarning || template.value?.quality_warning
  const base = `当前阶段：${processingStageLabel.value}，${resolvedProcessingDuration.value}。复杂老 .doc 可能需要更久。`
  return risk ? `${base} 当前风险提示：${risk}` : base
})
const hasPrototypeSection = computed(() => contentLoading.value || Boolean(prototypeHtml.value))
const shouldDeferHeavyPanels = computed(() => {
  const subFormCount = Number(template.value?.subFormCount ?? template.value?.sub_form_count ?? 0)
  const storageTableCount = Number(template.value?.storageTableCount ?? template.value?.storage_table_count ?? 0)
  return Boolean(template.value?.qualityWarning || template.value?.quality_warning || subFormCount > 24 || storageTableCount > 8)
})
const rawDdl = computed(() => String(ddlSql.value || ''))
const isDdlTruncated = computed(() => rawDdl.value.length > 5000)
const displayedDdl = computed(() => {
  if (!isDdlTruncated.value || ddlExpanded.value) return rawDdl.value
  return `${rawDdl.value.slice(0, 5000)}\n\n... 已截断 ${rawDdl.value.length - 5000} 个字符，点击“展开完整 DDL”查看全文 ...`
})

const editableControls = computed(() => collectEditableControls(reviewSchema.value))
const selectedControl = computed(() => editableControls.value.find(item => item.id === activeControlId.value) || null)
const selectedTarget = computed(() => resolveReviewTarget(reviewSchema.value, activeControlId.value))
const selectedStyleItem = computed(() => selectedControl.value || selectedTarget.value || null)
const selectedStyleSupportsCellLayout = computed(() => ['cell-control', 'cell-slot'].includes(selectedStyleItem.value?.scope))
const selectedStyleSupportsParagraphIndent = computed(() => ['paragraph-control', 'paragraph-slot'].includes(selectedStyleItem.value?.scope))
const selectedStyle = computed(() => {
  const style = getStyleForItem(reviewSchema.value, selectedStyleItem.value) || {}
  return {
    fontFamily: style.fontFamily || '',
    fontSizePx: style.fontSizePx ?? null,
    widthPx: style.widthPx ?? null,
    minHeightPx: style.minHeightPx ?? null,
    paddingPx: style.paddingPx ?? null,
    lineHeight: style.lineHeight ?? null,
    marginTopPx: style.marginTopPx ?? null,
    marginBottomPx: style.marginBottomPx ?? null,
    marginLeftPx: style.marginLeftPx ?? null,
    marginRightPx: style.marginRightPx ?? null,
    textIndentPx: style.textIndentPx ?? null,
    borderBox: resolveUniformBorder(style),
    textAlign: style.textAlign || '',
    fontWeight: style.fontWeight || '',
    verticalAlign: style.verticalAlign || '',
    backgroundColor: style.backgroundColor || '',
  }
})
const canCreateManualControl = computed(() => Boolean(
  canEditSchema.value
  && selectedTarget.value
  && !selectedControl.value
  && ['cell-slot', 'paragraph-slot'].includes(selectedTarget.value.scope),
))
const manualDraftSupportsOptions = computed(() => ['radio', 'checkbox_group', 'select'].includes(manualControlDraft.type))
const manualDraftSupportsMinHeight = computed(() => manualControlDraft.type === 'textarea')

function noop() {}

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

watch(
  () => [selectedTarget.value?.id, selectedControl.value?.id],
  () => {
    syncManualControlDraft(selectedTarget.value)
  },
  { immediate: true },
)

async function loadReviewData() {
  try {
    const detail = await apiFetch(`/api/templates/${route.params.templateId}?includeContent=false`)
    template.value = detail
    prototypeReady.value = false
    ddlExpanded.value = false
    if (detail.status === 'processing') {
      reviewSchema.value = null
      baselineSchemaJson.value = ''
      rendererReady.value = false
      schemaLoading.value = false
      schemaError.value = null
      contentLoading.value = false
      contentError.value = null
      prototypeHtml.value = ''
      ddlSql.value = ''
    } else {
      void loadSchema()
      void loadContent()
    }
  } catch (e) {
    error.value = `加载模板详情失败：${e.message}`
  } finally {
    loading.value = false
    syncPolling()
  }
}

async function loadSchema() {
  schemaLoading.value = true
  schemaError.value = null
  try {
    const schema = await apiFetch(`/api/templates/${route.params.templateId}/schema`)
    reviewSchema.value = clone(schema)
    baselineSchemaJson.value = JSON.stringify(reviewSchema.value)
    rendererReady.value = !shouldDeferHeavyPanels.value
    if (
      activeControlId.value
      && !collectEditableControls(reviewSchema.value).some(item => item.id === activeControlId.value)
      && !resolveReviewTarget(reviewSchema.value, activeControlId.value)
    ) {
      activeControlId.value = ''
    }
  } catch (e) {
    reviewSchema.value = null
    baselineSchemaJson.value = ''
    schemaError.value = `加载模板 schema 失败：${e.message}`
  } finally {
    schemaLoading.value = false
  }
}

async function loadContent() {
  contentLoading.value = true
  contentError.value = null
  try {
    const content = await apiFetch(`/api/templates/${route.params.templateId}/content`)
    prototypeHtml.value = String(content.prototypeHtml || content.prototype_html || '')
    ddlSql.value = String(content.ddlSql || content.ddl_sql || '')
  } catch (e) {
    prototypeHtml.value = ''
    ddlSql.value = ''
    contentError.value = `加载模板内容失败：${e.message}`
  } finally {
    contentLoading.value = false
  }
}

async function publishTemplate() {
  if (schemaDirty.value) {
    ElMessage.warning('请先保存纠错，再发布模板')
    return
  }
  try {
    template.value = await apiFetch(`/api/templates/${route.params.templateId}/publish`, {
      method: 'POST',
    })
    ElMessage.success('模板已发布')
    router.push(`/templates/${route.params.templateId}/form`)
  } catch (e) {
    ElMessage.error(`发布失败：${e.message}`)
  }
}

async function retryTemplate() {
  if (schemaDirty.value) {
    ElMessage.warning('请先保存或重置当前修改，再重新解析')
    return
  }
  try {
    template.value = await apiFetch(`/api/templates/${route.params.templateId}/retry`, {
      method: 'POST',
    })
    reviewSchema.value = null
    baselineSchemaJson.value = ''
    ElMessage.success('模板已重新提交后台解析')
    syncPolling()
  } catch (e) {
    ElMessage.error(`重新解析失败：${e.message}`)
  }
}

async function saveSchemaAdjustments() {
  if (!reviewSchema.value) return
  savingSchema.value = true
  try {
    template.value = await apiFetch(`/api/templates/${route.params.templateId}/schema`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(reviewSchema.value),
    })
    reviewSchema.value = await apiFetch(`/api/templates/${route.params.templateId}/schema`)
    reviewSchema.value = clone(reviewSchema.value)
    baselineSchemaJson.value = JSON.stringify(reviewSchema.value)
    ElMessage.success('模板纠错已保存')
  } catch (e) {
    ElMessage.error(`保存纠错失败：${e.message}`)
  } finally {
    savingSchema.value = false
  }
}

function resetSchemaEdits() {
  if (!baselineSchemaJson.value) return
  reviewSchema.value = JSON.parse(baselineSchemaJson.value)
}

function togglePrototype(event) {
  if (event.target?.open) {
    prototypeReady.value = true
  }
}

async function handlePreviewSelect(payload) {
  const id = typeof payload === 'string' ? payload : payload?.id
  if (!id) return
  activeControlId.value = id
  await nextTick()
  scrollControlIntoView(id)
  focusControlEditor(id)
}

function handlePreviewHover(payload) {
  hoveredControlId.value = typeof payload === 'string' ? payload : payload?.id || ''
}

async function handleControlItemClick(item) {
  activeControlId.value = item.id
  if (shouldDeferHeavyPanels.value && !rendererReady.value) {
    rendererReady.value = true
    await nextTick()
  }
  requestAnimationFrame(() => {
    scrollPreviewIntoView(item.id)
  })
}

function handleControlHover(id) {
  hoveredControlId.value = id || ''
}

function scrollControlIntoView(id) {
  const target = document.querySelector(`[data-control-id="${id}"]`)
  target?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}

function scrollPreviewIntoView(id) {
  const target = document.querySelector(`[data-review-id="${id}"]`)
  target?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

function focusControlEditor(id) {
  requestAnimationFrame(() => {
    const container = document.querySelector(`[data-control-id="${id}"]`)
    if (!container) return
    const target = container.querySelector(
      'input:not([type="hidden"]):not([disabled]), textarea:not([disabled]), .el-select input:not([disabled])',
    )
    target?.focus?.()
  })
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
  if (clockTimer) {
    window.clearInterval(clockTimer)
    clockTimer = null
  }
}

function syncPolling() {
  if (template.value?.status === 'processing' && !pollTimer) {
    pollTimer = window.setInterval(() => {
      loadReviewData()
    }, 5000)
    clockTimer = window.setInterval(() => {
      nowTick.value = Date.now()
    }, 1000)
    return
  }
  if (template.value?.status !== 'processing') {
    stopPolling()
  }
}

function formatSeconds(totalSeconds) {
  const seconds = Number(totalSeconds) || 0
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const remain = seconds % 60
  return remain ? `${minutes} 分 ${remain} 秒` : `${minutes} 分`
}

function cellSlotReviewId(blockIndex, rowIndex, cellIndex) {
  return `cell-${blockIndex}-${rowIndex}-${cellIndex}`
}

function paragraphSlotReviewId(blockIndex, rowIndex, cellIndex, paragraphIndex) {
  return `paragraph-${blockIndex}-${rowIndex ?? 'p'}-${cellIndex ?? 'p'}-${paragraphIndex ?? 0}`
}

function plainTextFromTokens(tokens) {
  return (tokens || [])
    .filter(token => token?.kind === 'text')
    .map(token => String(token.text || ''))
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function plainTextFromParagraphs(paragraphs) {
  return (paragraphs || [])
    .map(paragraph => plainTextFromTokens(paragraph?.tokens || []))
    .filter(Boolean)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function sanitizeSuggestedLabel(raw, fallback = '补充填写项') {
  const cleaned = String(raw || '')
    .replace(/[：:]+$/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return cleaned || fallback
}

function inferManualType(label, context = {}) {
  const source = [label, context.text, context.neighborText].filter(Boolean).join(' ')
  if (/问题|意见|说明|备注|情况|结论|描述|记录|内容/.test(source)) {
    return 'textarea'
  }
  if (/是否|合格|整改|不合格|符合|通过|同意|不同意/.test(source)) {
    return 'radio'
  }
  if (context.blankParagraphs >= 2 || context.verticalAlign === 'top') {
    return 'textarea'
  }
  return 'text'
}

function inferManualMinHeight(preferredType, context = {}) {
  if (preferredType !== 'textarea') {
    return 180
  }
  if (context.blankParagraphs >= 4) {
    return 260
  }
  if (context.blankParagraphs >= 2) {
    return 220
  }
  return 180
}

function guessCellTargetLabel(schema, blockIndex, rowIndex, cellIndex, cell) {
  const row = schema.documentBlocks?.[blockIndex]?.rows?.[rowIndex] || []
  const leftText = [...row]
    .slice(0, cellIndex)
    .reverse()
    .map(item => plainTextFromParagraphs(item?.paragraphs || []))
    .find(Boolean)
  const ownText = plainTextFromParagraphs(cell?.paragraphs || [])
  return sanitizeSuggestedLabel(ownText || leftText, `补充字段 ${rowIndex + 1}-${cellIndex + 1}`)
}

function guessParagraphTargetLabel(schema, target) {
  if (!target) return '补充填写项'
  if (target.topLevel) {
    return sanitizeSuggestedLabel(target.text, `段落补充 ${target.blockIndex + 1}`)
  }

  const block = schema.documentBlocks?.[target.blockIndex]
  const row = block?.rows?.[target.rowIndex] || []
  const cell = row?.[target.cellIndex]
  const paragraphs = cell?.paragraphs || []
  const currentText = plainTextFromTokens(paragraphs?.[target.paragraphIndex]?.tokens || [])
  if (currentText) {
    return sanitizeSuggestedLabel(currentText, target.location)
  }

  const neighborText = [
    plainTextFromTokens(paragraphs?.[target.paragraphIndex - 1]?.tokens || []),
    plainTextFromTokens(paragraphs?.[target.paragraphIndex + 1]?.tokens || []),
    guessCellTargetLabel(schema, target.blockIndex, target.rowIndex, target.cellIndex, cell),
  ].find(Boolean)
  return sanitizeSuggestedLabel(neighborText, target.location)
}

function resolveReviewTarget(schema, id) {
  if (!schema || !id) return null

  const cellMatch = /^cell-(\d+)-(\d+)-(\d+)$/.exec(id)
  if (cellMatch) {
    const [, blockText, rowText, cellText] = cellMatch
    const blockIndex = Number(blockText)
    const rowIndex = Number(rowText)
    const cellIndex = Number(cellText)
    const cell = schema.documentBlocks?.[blockIndex]?.rows?.[rowIndex]?.[cellIndex]
    if (!cell) return null
    const suggestedLabel = guessCellTargetLabel(schema, blockIndex, rowIndex, cellIndex, cell)
    const preferredType = inferManualType(suggestedLabel, {
      text: plainTextFromParagraphs(cell.paragraphs || []),
      blankParagraphs: (cell.paragraphs || []).filter(item => item?.kind === 'blank').length,
      verticalAlign: cell.style?.verticalAlign,
    })
    return {
      id,
      scope: 'cell-slot',
      blockIndex,
      rowIndex,
      cellIndex,
      path: { blockIndex, rowIndex, cellIndex },
      label: suggestedLabel,
      suggestedLabel,
      preferredType,
      recommendedMinHeightPx: inferManualMinHeight(preferredType, {
        blankParagraphs: (cell.paragraphs || []).filter(item => item?.kind === 'blank').length,
      }),
      location: `表 ${blockIndex + 1} / 行 ${rowIndex + 1} / 列 ${cellIndex + 1}`,
      cell,
    }
  }

  const paragraphMatch = /^paragraph-(\d+)-(p|\d+)-(p|\d+)-(\d+)$/.exec(id)
  if (!paragraphMatch) return null
  const [, blockText, rowText, cellText, paragraphText] = paragraphMatch
  const blockIndex = Number(blockText)
  const paragraphIndex = Number(paragraphText)
  const block = schema.documentBlocks?.[blockIndex]
  if (!block) return null

  if (rowText === 'p' && cellText === 'p') {
    if (block.kind !== 'paragraph') return null
    const suggestedLabel = sanitizeSuggestedLabel(block.text, `段落补充 ${blockIndex + 1}`)
    const preferredType = inferManualType(suggestedLabel, { text: block.text })
    return {
      id,
      scope: 'paragraph-slot',
      topLevel: true,
      blockIndex,
      rowIndex: null,
      cellIndex: null,
      paragraphIndex,
      path: { blockIndex, rowIndex: null, cellIndex: null, paragraphIndex },
      label: suggestedLabel,
      suggestedLabel,
      preferredType,
      recommendedMinHeightPx: inferManualMinHeight(preferredType),
      location: `段落 ${blockIndex + 1}`,
      text: block.text,
      paragraph: block,
    }
  }

  const rowIndex = Number(rowText)
  const cellIndex = Number(cellText)
  const cell = block.rows?.[rowIndex]?.[cellIndex]
  const paragraph = cell?.paragraphs?.[paragraphIndex]
  if (!paragraph) return null
  const suggestedLabel = guessParagraphTargetLabel(schema, {
    blockIndex,
    rowIndex,
    cellIndex,
    paragraphIndex,
    topLevel: false,
    location: `表 ${blockIndex + 1} / 行 ${rowIndex + 1} / 列 ${cellIndex + 1} / 段落 ${paragraphIndex + 1}`,
  })
  const preferredType = inferManualType(suggestedLabel, {
    text: plainTextFromTokens(paragraph.tokens || []),
    neighborText: plainTextFromParagraphs(cell.paragraphs || []),
    blankParagraphs: paragraph.kind === 'blank' ? 1 : 0,
    verticalAlign: cell.style?.verticalAlign,
  })
  return {
    id,
    scope: 'paragraph-slot',
    topLevel: false,
    blockIndex,
    rowIndex,
    cellIndex,
    paragraphIndex,
    path: { blockIndex, rowIndex, cellIndex, paragraphIndex },
    label: suggestedLabel,
    suggestedLabel,
    preferredType,
    recommendedMinHeightPx: inferManualMinHeight(preferredType, {
      blankParagraphs: (cell.paragraphs || []).filter(item => item?.kind === 'blank').length,
    }),
    location: `表 ${blockIndex + 1} / 行 ${rowIndex + 1} / 列 ${cellIndex + 1} / 段落 ${paragraphIndex + 1}`,
    paragraph,
    cell,
  }
}

function collectEditableControls(schema) {
  if (!schema || !Array.isArray(schema.documentBlocks)) {
    return []
  }

  const items = []
  for (const [blockIndex, block] of schema.documentBlocks.entries()) {
    if (block.kind === 'paragraph') {
      if (block.control) {
        items.push(buildParagraphControlItem(schema, block.control, {
          blockIndex,
          rowIndex: null,
          cellIndex: null,
          paragraphIndex: 0,
          location: `段落 ${blockIndex + 1}`,
          topLevel: true,
        }))
      }
      collectTokens(items, schema, block.tokens || [], { blockIndex, location: `段落 ${blockIndex + 1}` })
      continue
    }

    if (block.kind !== 'table') continue
    for (const [rowIndex, row] of (block.rows || []).entries()) {
      for (const [cellIndex, cell] of (row || []).entries()) {
        if (cell.control) {
          items.push(buildCellControlItem(schema, cell.control, {
            blockIndex,
            rowIndex,
            cellIndex,
            location: `表 ${blockIndex + 1} / 行 ${rowIndex + 1} / 列 ${cellIndex + 1}`,
          }))
        }
        for (const [paragraphIndex, paragraph] of (cell.paragraphs || []).entries()) {
          if (paragraph.control) {
            items.push(buildParagraphControlItem(schema, paragraph.control, {
              blockIndex,
              rowIndex,
              cellIndex,
              paragraphIndex,
              location: `表 ${blockIndex + 1} / 行 ${rowIndex + 1} / 列 ${cellIndex + 1} / 段落 ${paragraphIndex + 1}`,
              topLevel: false,
            }))
          }
          collectTokens(items, schema, paragraph.tokens || [], {
            blockIndex,
            rowIndex,
            cellIndex,
            paragraphIndex,
            location: `表 ${blockIndex + 1} / 行 ${rowIndex + 1} / 列 ${cellIndex + 1}`,
          })
        }
      }
    }
  }

  return items
}

function collectTokens(target, schema, tokens, context) {
  for (const [tokenIndex, token] of tokens.entries()) {
    if (!['inline-input', 'inline-choice'].includes(token.kind)) {
      continue
    }
    target.push(buildTokenItem(schema, tokens, token, tokenIndex, context))
  }
}

function buildCellControlItem(schema, control, context) {
  const field = control.kind === 'schema'
    ? findField(schema, control.subFormId, control.fieldId)
    : null
  const style = getStyleForItem(schema, { scope: 'cell-control', path: context })
  const type = field?.type || control.fieldType || 'text'
  const options = field?.options || control.options || []
  return {
    id: cellSlotReviewId(context.blockIndex, context.rowIndex, context.cellIndex),
    scope: 'cell-control',
    label: field?.label || control.label || `控件 ${context.rowIndex + 1}-${context.cellIndex + 1}`,
    location: context.location,
    type,
    optionsText: Array.isArray(options) ? options.join(', ') : '',
    supportsOptions: ['radio', 'checkbox_group', 'select'].includes(type),
    supportsMinHeight: type === 'textarea',
    minHeightPx: control.minHeightPx || field?.minHeightPx || 120,
    fieldId: field?.id || control.fieldId || '',
    sqlColumn: field?.sqlColumn || field?.storageColumn || '',
    placeholder: field?.placeholder || control.placeholder || '',
    fontFamily: style?.fontFamily || '',
    fontSizePx: style?.fontSizePx ?? null,
    textAlign: style?.textAlign || '',
    fontWeight: style?.fontWeight || '',
    typeOptions: FIELD_TYPE_OPTIONS,
    path: context,
  }
}

function buildParagraphControlItem(schema, control, context) {
  const field = control.kind === 'schema'
    ? findField(schema, control.subFormId, control.fieldId)
    : null
  const style = getStyleForItem(schema, { scope: 'paragraph-control', path: context })
  const type = field?.type || control.fieldType || 'text'
  const options = field?.options || control.options || []
  return {
    id: paragraphSlotReviewId(context.blockIndex, context.rowIndex, context.cellIndex, context.paragraphIndex),
    scope: 'paragraph-control',
    label: field?.label || control.label || '段落控件',
    location: context.location,
    type,
    optionsText: Array.isArray(options) ? options.join(', ') : '',
    supportsOptions: ['radio', 'checkbox_group', 'select'].includes(type),
    supportsMinHeight: type === 'textarea',
    minHeightPx: control.minHeightPx || field?.minHeightPx || 120,
    fieldId: field?.id || control.fieldId || '',
    sqlColumn: field?.sqlColumn || field?.storageColumn || '',
    placeholder: field?.placeholder || control.placeholder || '',
    fontFamily: style?.fontFamily || '',
    fontSizePx: style?.fontSizePx ?? null,
    textAlign: style?.textAlign || '',
    fontWeight: style?.fontWeight || '',
    typeOptions: FIELD_TYPE_OPTIONS,
    path: context,
  }
}

function buildTokenItem(schema, tokens, token, tokenIndex, context) {
  const type = token.kind === 'inline-choice'
    ? (token.choiceType === 'checkbox_group' ? 'checkbox_group' : 'radio')
    : 'text'
  const field = token.fieldId && token.subFormId ? findField(schema, token.subFormId, token.fieldId) : null
  return {
    id: `token-${context.blockIndex}-${context.rowIndex ?? 'p'}-${context.cellIndex ?? 'p'}-${context.paragraphIndex ?? 0}-${tokenIndex}`,
    scope: 'token',
    label: guessTokenLabel(tokens, tokenIndex, context.location),
    location: context.location,
    type,
    optionsText: Array.isArray(token.options) ? token.options.join(', ') : '',
    supportsOptions: type !== 'text',
    supportsMinHeight: false,
    minHeightPx: null,
    fieldId: token.fieldId || '',
    sqlColumn: field?.sqlColumn || field?.storageColumn || '',
    placeholder: field?.placeholder || (type === 'text' ? '填写' : '请选择'),
    typeOptions: TOKEN_TYPE_OPTIONS,
    path: { ...context, tokenIndex },
  }
}

function guessTokenLabel(tokens, tokenIndex, fallback) {
  const prevText = [...tokens]
    .slice(0, tokenIndex)
    .reverse()
    .find(token => token.kind === 'text' && String(token.text || '').trim())
  const nextText = tokens
    .slice(tokenIndex + 1)
    .find(token => token.kind === 'text' && String(token.text || '').trim())
  const left = String(prevText?.text || '').trim()
  const right = String(nextText?.text || '').trim()
  const label = [left, right].filter(Boolean).join(' ')
  return label || fallback
}

function findField(schema, subFormId, fieldId) {
  const subForm = (schema.subForms || []).find(item => item.id === subFormId)
  return subForm?.fields?.find(field => field.id === fieldId)
}

function getCellControl(schema, item) {
  return schema.documentBlocks?.[item.path.blockIndex]?.rows?.[item.path.rowIndex]?.[item.path.cellIndex]?.control || null
}

function getParagraphControl(schema, item) {
  const block = schema.documentBlocks?.[item.path.blockIndex]
  if (!block) return null
  if (item.path.rowIndex === null || item.path.rowIndex === undefined) {
    return block.control || null
  }
  return block.rows?.[item.path.rowIndex]?.[item.path.cellIndex]?.paragraphs?.[item.path.paragraphIndex]?.control || null
}

function getToken(schema, item) {
  const block = schema.documentBlocks?.[item.path.blockIndex]
  if (!block) return null
  if (block.kind === 'paragraph') {
    return block.tokens?.[item.path.tokenIndex] || null
  }
  return block.rows?.[item.path.rowIndex]?.[item.path.cellIndex]?.paragraphs?.[item.path.paragraphIndex]?.tokens?.[item.path.tokenIndex] || null
}

function getStyleContainer(schema, item) {
  if (!schema || !item) return null
  if (item.scope === 'cell-control' || item.scope === 'cell-slot') {
    return schema.documentBlocks?.[item.path.blockIndex]?.rows?.[item.path.rowIndex]?.[item.path.cellIndex] || null
  }
  if (item.scope === 'paragraph-control' || item.scope === 'paragraph-slot') {
    if (item.path.rowIndex === null || item.path.rowIndex === undefined) {
      return schema.documentBlocks?.[item.path.blockIndex] || null
    }
    return schema.documentBlocks?.[item.path.blockIndex]?.rows?.[item.path.rowIndex]?.[item.path.cellIndex]?.paragraphs?.[item.path.paragraphIndex] || null
  }
  return null
}

function getStyleForItem(schema, item) {
  return getStyleContainer(schema, item)?.style || null
}

function resolveUniformBorder(style) {
  if (!style) return ''
  const borders = [style.borderTop, style.borderRight, style.borderBottom, style.borderLeft]
    .map(value => String(value || '').trim())
    .filter(Boolean)
  if (!borders.length) return ''
  return borders.every(value => value === borders[0]) ? borders[0] : ''
}

function updateItemStyle(item, key, value) {
  if (!reviewSchema.value || !item) return
  const container = getStyleContainer(reviewSchema.value, item)
  if (!container) return
  container.style = container.style && typeof container.style === 'object' ? container.style : {}
  if (
    key === 'widthPx'
    || key === 'minHeightPx'
    || key === 'paddingPx'
    || key === 'marginTopPx'
    || key === 'marginBottomPx'
    || key === 'marginLeftPx'
    || key === 'marginRightPx'
    || key === 'textIndentPx'
  ) {
    const numeric = Number(value)
    const allowsNegative = key === 'textIndentPx'
    const allowsZero = ['paddingPx', 'marginTopPx', 'marginBottomPx', 'marginLeftPx', 'marginRightPx'].includes(key)
    if (!Number.isFinite(numeric) || (allowsNegative ? false : (allowsZero ? numeric < 0 : numeric <= 0))) {
      delete container.style[key]
    } else {
      const bounds = key === 'widthPx'
        ? [40, 1600]
        : key === 'paddingPx'
          ? [0, 48]
          : key === 'marginTopPx' || key === 'marginBottomPx'
            ? [0, 120]
            : key === 'marginLeftPx' || key === 'marginRightPx'
              ? [0, 240]
              : key === 'textIndentPx'
                ? [-120, 240]
          : [24, 1200]
      container.style[key] = Math.max(bounds[0], Math.min(bounds[1], Math.round(numeric)))
    }
    return
  }
  if (key === 'lineHeight') {
    const numeric = Number(value)
    if (!Number.isFinite(numeric) || numeric <= 0) {
      delete container.style[key]
    } else {
      container.style[key] = Math.max(1, Math.min(3, Math.round(numeric * 10) / 10))
    }
    return
  }
  if (key === 'fontSizePx') {
    const numeric = Number(value)
    if (!Number.isFinite(numeric) || numeric <= 0) {
      delete container.style[key]
    } else {
      container.style[key] = Math.max(10, Math.min(48, Math.round(numeric)))
    }
    return
  }
  if (key === 'fontFamily') {
    const trimmed = String(value || '').trim()
    if (!trimmed) delete container.style[key]
    else container.style[key] = trimmed
    return
  }
  if (key === 'textAlign') {
    if (!value) delete container.style[key]
    else container.style[key] = value
    return
  }
  if (key === 'verticalAlign') {
    if (!value) delete container.style[key]
    else container.style[key] = value
    return
  }
  if (key === 'backgroundColor') {
    const trimmed = String(value || '').trim()
    if (!trimmed) delete container.style[key]
    else container.style[key] = trimmed
    return
  }
  if (key === 'borderBox') {
    const trimmed = String(value || '').trim()
    for (const borderKey of ['borderTop', 'borderRight', 'borderBottom', 'borderLeft']) {
      if (!trimmed) delete container.style[borderKey]
      else container.style[borderKey] = trimmed
    }
    return
  }
  if (key === 'fontWeight') {
    if (!value) delete container.style[key]
    else container.style[key] = value
  }
}

function parseOptions(raw) {
  return String(raw || '')
    .split(/[\n,，]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function buildFieldPlaceholder(label, type) {
  const cleanedLabel = String(label || '').replace(/[：:]+$/g, '').trim()
  switch (type) {
    case 'date':
      return cleanedLabel ? `请选择${cleanedLabel}` : '请选择日期'
    case 'select':
    case 'radio':
    case 'checkbox_group':
      return cleanedLabel ? `请选择${cleanedLabel}` : '请选择'
    case 'textarea':
      return cleanedLabel ? `请输入${cleanedLabel}` : '请输入内容'
    case 'number':
      return cleanedLabel ? `请输入${cleanedLabel}` : '请输入数字'
    default:
      return cleanedLabel ? `请输入${cleanedLabel}` : '请输入'
  }
}

function resolveSqlType(type) {
  switch (type) {
    case 'number':
      return 'NUMERIC(10,2)'
    case 'date':
      return 'DATE'
    case 'textarea':
    case 'checkbox_group':
      return 'TEXT'
    case 'radio':
    case 'select':
      return 'VARCHAR(100)'
    default:
      return 'VARCHAR(200)'
  }
}

function nextManualFieldId(schema) {
  const existing = new Set(
    (schema.subForms || [])
      .flatMap(subForm => subForm.fields || [])
      .map(field => field.id),
  )
  let index = 1
  while (existing.has(`manual_field_${index}`)) {
    index += 1
  }
  return `manual_field_${index}`
}

function ensureManualSupplementSubForm(schema) {
  const existing = (schema.subForms || []).find(subForm => subForm.id === 'manual_review_patch')
  if (existing) {
    existing.fields = Array.isArray(existing.fields) ? existing.fields : []
    existing.layout = existing.layout?.type === 'key-value' ? existing.layout : { type: 'key-value', rows: [] }
    existing.layout.rows = Array.isArray(existing.layout.rows) ? existing.layout.rows : []
    return existing
  }

  const firstSingle = (schema.subForms || []).find(subForm => subForm.recordType !== 'multi')
  const tableName = firstSingle?.storageTableName || firstSingle?.sqlTableName || 't_manual_review_patch'
  const subForm = {
    id: 'manual_review_patch',
    name: '审核补录控件',
    sqlTableName: tableName,
    storageTableName: tableName,
    recordType: 'single',
    layout: {
      type: 'key-value',
      rows: [],
    },
    fields: [],
  }
  schema.subForms = Array.isArray(schema.subForms) ? schema.subForms : []
  schema.subForms.push(subForm)
  return subForm
}

function createManualField(schema, config) {
  const subForm = ensureManualSupplementSubForm(schema)
  const fieldId = nextManualFieldId(schema)
  const options = ['radio', 'checkbox_group', 'select'].includes(config.type)
    ? (config.options?.length ? config.options : ['选项1', '选项2'])
    : null
  const field = {
    id: fieldId,
    label: config.label,
    type: config.type,
    placeholder: buildFieldPlaceholder(config.label, config.type),
    sqlColumn: fieldId,
    storageColumn: fieldId,
    sqlType: resolveSqlType(config.type),
    required: false,
    options,
    isPrefix: false,
  }
  if (config.type === 'textarea') {
    field.minHeightPx = Math.max(80, Number(config.minHeightPx) || 180)
  }
  subForm.fields.push(field)
  subForm.layout.rows.push([
    { kind: 'label', text: config.label, colspan: 1, rowspan: 1 },
    { kind: 'input', fieldId, colspan: 1, rowspan: 1 },
  ])
  return { ...field, subFormId: subForm.id }
}

function attachManualControl(target, control) {
  if (!reviewSchema.value || !target) return
  if (target.scope === 'cell-slot') {
    const cell = reviewSchema.value.documentBlocks?.[target.blockIndex]?.rows?.[target.rowIndex]?.[target.cellIndex]
    if (!cell) return
    cell.control = control
    return
  }

  if (target.topLevel) {
    const block = reviewSchema.value.documentBlocks?.[target.blockIndex]
    if (block) {
      block.control = control
    }
    return
  }

  const paragraph = reviewSchema.value.documentBlocks?.[target.blockIndex]?.rows?.[target.rowIndex]?.[target.cellIndex]?.paragraphs?.[target.paragraphIndex]
  if (paragraph) {
    paragraph.control = control
  }
}

function syncManualControlDraft(target) {
  if (!target || selectedControl.value) {
    return
  }
  manualControlDraft.label = target.suggestedLabel || target.label || ''
  manualControlDraft.type = target.preferredType || 'text'
  manualControlDraft.optionsText = ''
  manualControlDraft.minHeightPx = target.recommendedMinHeightPx || 180
}

function resetManualControlDraft() {
  syncManualControlDraft(selectedTarget.value)
}

async function addManualControl() {
  if (!reviewSchema.value || !selectedTarget.value || !canCreateManualControl.value) {
    return
  }

  const label = sanitizeSuggestedLabel(
    manualControlDraft.label,
    selectedTarget.value.suggestedLabel || selectedTarget.value.label || '补充填写项',
  )
  if (!label) {
    ElMessage.warning('请先填写控件名称')
    return
  }

  const type = manualControlDraft.type || 'text'
  const options = ['radio', 'checkbox_group', 'select'].includes(type)
    ? parseOptions(manualControlDraft.optionsText)
    : []
  const field = createManualField(reviewSchema.value, {
    label,
    type,
    options,
    minHeightPx: manualControlDraft.minHeightPx,
  })

  attachManualControl(selectedTarget.value, {
    kind: 'schema',
    subFormId: field.subFormId,
    fieldId: field.id,
    fieldType: field.type,
    label: field.label,
    options: field.options || [],
    minHeightPx: field.minHeightPx,
    rowIndex: null,
  })

  activeControlId.value = selectedTarget.value.id
  await nextTick()
  scrollControlIntoView(selectedTarget.value.id)
  focusControlEditor(selectedTarget.value.id)
  ElMessage.success('已补充控件，请继续检查并保存纠错')
}

function updateControlType(item, nextType) {
  if (!reviewSchema.value) return

  if (item.scope === 'cell-control' || item.scope === 'paragraph-control') {
    const control = item.scope === 'cell-control'
      ? getCellControl(reviewSchema.value, item)
      : getParagraphControl(reviewSchema.value, item)
    if (!control) return
    control.fieldType = nextType
    if (nextType === 'textarea') {
      control.minHeightPx = control.minHeightPx || 120
    } else {
      delete control.minHeightPx
    }
    if (['radio', 'checkbox_group', 'select'].includes(nextType)) {
      control.options = control.options?.length ? control.options : ['选项1', '选项2']
    } else {
      control.options = []
    }

    if (control.kind === 'schema') {
      const field = findField(reviewSchema.value, control.subFormId, control.fieldId)
      if (field) {
        field.type = nextType
        field.options = control.options
        if (nextType === 'textarea') {
          field.minHeightPx = control.minHeightPx || field.minHeightPx || 120
        } else {
          delete field.minHeightPx
        }
      }
    }
    return
  }

  const token = getToken(reviewSchema.value, item)
  if (!token) return
  if (nextType === 'text') {
    token.kind = 'inline-input'
    token.widthEm = token.widthEm || 7.2
    delete token.choiceType
    delete token.options
    return
  }
  token.kind = 'inline-choice'
  token.choiceType = nextType === 'checkbox_group' ? 'checkbox_group' : 'radio'
  token.options = token.options?.length ? token.options : ['选项1', '选项2']
  delete token.widthEm
}

function updateControlOptions(item, raw) {
  if (!reviewSchema.value) return
  const options = parseOptions(raw)

  if (item.scope === 'cell-control' || item.scope === 'paragraph-control') {
    const control = item.scope === 'cell-control'
      ? getCellControl(reviewSchema.value, item)
      : getParagraphControl(reviewSchema.value, item)
    if (!control) return
    control.options = options
    if (control.kind === 'schema') {
      const field = findField(reviewSchema.value, control.subFormId, control.fieldId)
      if (field) {
        field.options = options
      }
    }
    return
  }

  const token = getToken(reviewSchema.value, item)
  if (!token) return
  token.options = options
}

function updateControlMinHeight(item, nextHeight) {
  if (!reviewSchema.value || !['cell-control', 'paragraph-control'].includes(item.scope)) return
  const control = item.scope === 'cell-control'
    ? getCellControl(reviewSchema.value, item)
    : getParagraphControl(reviewSchema.value, item)
  if (!control) return
  control.minHeightPx = Math.max(80, Number(nextHeight) || 120)
  if (control.kind === 'schema') {
    const field = findField(reviewSchema.value, control.subFormId, control.fieldId)
    if (field) {
      field.minHeightPx = control.minHeightPx
    }
  }
}

onMounted(loadReviewData)

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.review-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.75fr) minmax(320px, 0.95fr);
  gap: 18px;
}

.review-main,
.review-side {
  display: grid;
  gap: 18px;
  align-content: start;
  min-width: 0;
}

.preview-card,
.detail-card,
.prototype-card {
  overflow: hidden;
}

.deferred-actions {
  margin-top: 12px;
}

.preview-body {
  padding: 18px;
  max-height: calc(100vh - 220px);
  overflow: auto;
  min-width: 0;
}

.prototype-card {
  padding: 0;
}

.prototype-card summary {
  padding: 14px 18px;
  cursor: pointer;
  font-weight: 600;
}

.preview-frame {
  width: 100%;
  min-height: 620px;
  border: none;
  border-top: 1px solid #e3e9f2;
  background: #fff;
}

.prototype-placeholder {
  padding: 0 18px 18px;
  color: #607086;
  font-size: 13px;
}

.panel-note {
  margin: 0 0 10px;
  color: #607086;
  font-size: 13px;
  line-height: 1.6;
}

.active-control-banner {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 12px;
  margin: 0 0 12px;
  border-radius: 12px;
  background: #eef4ff;
  border: 1px solid #cddbf8;
  color: #223047;
}

.active-control-meta {
  margin-left: 8px;
  color: #5d6f89;
  font-size: 12px;
}

.active-control-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.style-adjust-panel {
  display: grid;
  gap: 10px;
  padding: 14px;
  margin: 0 0 12px;
  border-radius: 14px;
  background: #f8fbff;
  border: 1px solid #d5e2fb;
}

.style-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  align-items: center;
}

.style-field {
  display: grid;
  gap: 6px;
}

.style-field-label {
  color: #4f6078;
  font-size: 12px;
  font-weight: 600;
}

.style-field-switch {
  align-content: end;
}

.control-list {
  display: grid;
  gap: 12px;
  max-height: calc(100vh - 320px);
  overflow: auto;
  padding-right: 4px;
}

.control-item {
  border: 1px solid #dbe3f0;
  border-radius: 12px;
  padding: 12px;
  background: #fbfdff;
  display: grid;
  gap: 10px;
  cursor: pointer;
  transition: border-color 140ms ease, box-shadow 140ms ease, background-color 140ms ease;
}

.control-item:hover {
  border-color: #b8c9ea;
  box-shadow: 0 8px 18px rgba(44, 92, 197, 0.08);
}

.control-item.is-active {
  border-color: #2c5cc5;
  background: #f4f8ff;
  box-shadow: 0 0 0 2px rgba(44, 92, 197, 0.14);
}

.control-item.is-hovered:not(.is-active) {
  border-color: #8fb0f2;
  background: #f8fbff;
}

.control-head {
  display: grid;
  gap: 4px;
}

.control-head strong {
  color: #223047;
  font-size: 14px;
}

.control-head span {
  color: #6b7b92;
  font-size: 12px;
}

.control-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.control-meta span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: #edf4ff;
  color: #35558c;
  font-size: 11px;
  line-height: 1;
}

.control-input {
  width: 100%;
}

.manual-control-panel {
  display: grid;
  gap: 10px;
  padding: 14px;
  margin: 0 0 12px;
  border-radius: 14px;
  background: #f8fbff;
  border: 1px dashed #9fb8ee;
}

.manual-panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #223047;
}

.manual-panel-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.ddl-toggle {
  margin-top: 8px;
}

@media (max-width: 1200px) {
  .review-grid {
    grid-template-columns: 1fr;
  }

  .preview-body,
  .control-list {
    max-height: none;
  }

  .active-control-banner {
    flex-direction: column;
  }

  .style-grid {
    grid-template-columns: 1fr;
  }
}
</style>
