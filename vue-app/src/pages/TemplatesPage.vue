<template>
  <div class="page-wrap">
    <div class="page-card page-header">
      <div>
        <div class="kicker">Template Center</div>
        <h2>Word 模板上传与审核</h2>
        <p class="muted">先上传 Word，拿到 HTML 原型做人工审核，确认后再发布成正式录入页面。</p>
      </div>
      <div class="header-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索模板名称"
          class="search-box"
          @keyup.enter="loadTemplates"
        />
        <input ref="fileInput" type="file" class="hidden-input" accept=".doc,.docx" @change="handleFileChange" />
        <el-button :disabled="!canUpload" @click="fileInput?.click()">选择 Word</el-button>
        <el-button type="primary" :disabled="!canUpload" :loading="uploading" @click="uploadSelectedFile">上传并生成</el-button>
      </div>
    </div>

    <div v-if="parserStatus" class="page-card slim-card parser-status-card" :class="`status-${parserStatus.defaultMode}`">
      <strong>解析服务状态：</strong>
      <template v-if="parserStatus.defaultMode === 'openai'">
        当前使用 OpenAI，模型 `{{ parserStatus.model }}`，可以直接上传。
      </template>
      <template v-else-if="parserStatus.defaultMode === 'heuristic'">
        当前未配置 OpenAI Key，已显式开启本地启发式兜底，仅建议开发联调使用。
      </template>
      <template v-else>
        当前未配置 `OPENAI_API_KEY`，上传已禁用。请先在
        `word-parser-service` 中配置 Key 后重启解析服务。
      </template>
    </div>

    <div v-if="selectedFile" class="page-card slim-card">
      当前待上传：{{ selectedFile.name }}
    </div>

    <div v-if="loading" class="page-card state-card">加载模板列表...</div>
    <div v-else class="page-card">
      <el-table :data="templates" border>
        <el-table-column prop="templateName" label="模板名称" min-width="220" />
        <el-table-column prop="sourceFile" label="源文件" min-width="220" />
        <el-table-column prop="subFormCount" label="页面块数" width="100" />
        <el-table-column prop="storageTableCount" label="存储表数" width="100" />
        <el-table-column prop="analysisMode" label="分析模式" width="120" />
        <el-table-column label="处理进度" min-width="180">
          <template #default="{ row }">
            <div class="progress-meta">
              <strong>{{ statusLabel(row.status, row.processingStage) }}</strong>
              <span>{{ processingMeta(row) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="质量风险" min-width="180">
          <template #default="{ row }">
            <span v-if="row.qualityWarning" class="quality-warning">{{ row.qualityWarning }}</span>
            <span v-else class="quality-ok">正常</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ statusLabel(row.status, row.processingStage) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="260">
          <template #default="{ row }">
            <div class="table-actions">
              <RouterLink :to="`/templates/${row.templateId}/review`" class="inline-link">审核</RouterLink>
              <RouterLink
                v-if="row.status === 'active'"
                :to="`/templates/${row.templateId}/form`"
                class="inline-link"
              >
                填表
              </RouterLink>
              <el-button
                v-if="row.status === 'pending_review'"
                link
                type="primary"
                @click="publishTemplate(row.templateId)"
              >
                发布
              </el-button>
              <el-button
                v-if="row.status === 'failed'"
                link
                type="danger"
                @click="retryTemplate(row.templateId)"
              >
                重试
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onBeforeUnmount, onMounted } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiFetch } from '../api/client'

const router = useRouter()
const templates = ref([])
const loading = ref(true)
const uploading = ref(false)
const selectedFile = ref(null)
const fileInput = ref(null)
const keyword = ref('')
const parserStatus = ref(null)
const canUpload = computed(() => Boolean(parserStatus.value) && parserStatus.value.defaultMode !== 'unavailable')
let pollTimer = null
let clockTimer = null
const nowTick = ref(Date.now())

async function loadTemplates() {
  loading.value = true
  try {
    const data = await apiFetch(`/api/templates?page=1&size=50&keyword=${encodeURIComponent(keyword.value)}`)
    templates.value = data.list || []
    syncPolling()
  } catch (e) {
    ElMessage.error(`加载模板失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

async function loadParserStatus() {
  try {
    parserStatus.value = await apiFetch('/api/templates/parser-status')
  } catch (e) {
    parserStatus.value = {
      defaultMode: 'unavailable',
      model: 'unknown',
      openaiConfigured: false,
      heuristicFallbackAllowed: false,
    }
    ElMessage.error(`解析服务状态获取失败：${e.message}`)
  }
}

function handleFileChange(event) {
  selectedFile.value = event.target.files?.[0] || null
}

async function uploadSelectedFile() {
  if (!canUpload.value) {
    ElMessage.error('当前未配置 OPENAI_API_KEY，上传已禁用')
    return
  }
  if (!selectedFile.value) {
    ElMessage.warning('请先选择 Word 文件')
    return
  }
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const data = await apiFetch('/api/templates/upload', {
      method: 'POST',
      body: formData,
      headers: { 'X-User': 'admin' },
    })
    ElMessage.success('模板已提交，正在后台解析')
    selectedFile.value = null
    if (fileInput.value) {
      fileInput.value.value = ''
    }
    await loadTemplates()
    router.push(`/templates/${data.templateId}/review`)
  } catch (e) {
    ElMessage.error(`上传失败：${e.message}`)
  } finally {
    uploading.value = false
  }
}

async function retryTemplate(templateId) {
  try {
    await apiFetch(`/api/templates/${templateId}/retry`, { method: 'POST' })
    ElMessage.success('模板已重新提交解析')
    await loadTemplates()
  } catch (e) {
    ElMessage.error(`重试失败：${e.message}`)
  }
}

async function publishTemplate(templateId) {
  try {
    await apiFetch(`/api/templates/${templateId}/publish`, { method: 'POST' })
    ElMessage.success('模板已发布')
    await loadTemplates()
  } catch (e) {
    ElMessage.error(`发布失败：${e.message}`)
  }
}

function statusTagType(status) {
  if (status === 'active') return 'success'
  if (status === 'pending_review') return 'warning'
  if (status === 'processing') return 'info'
  if (status === 'failed') return 'danger'
  if (status === 'inactive') return 'info'
  return ''
}

function statusLabel(status, processingStage) {
  if (status !== 'processing') return status
  return {
    queued: '排队中',
    parsing_word: '解析 Word / AI分析中',
    building_schema: '生成 Schema / DDL 中',
  }[processingStage] || 'processing'
}

function processingMeta(row) {
  if (row.status === 'processing') {
    const createdAt = row.createdAt || row.created_at
    if (!createdAt) return '处理中'
    const seconds = Math.max(1, Math.round((nowTick.value - new Date(createdAt).getTime()) / 1000))
    return `已等待 ${formatSeconds(seconds)}`
  }
  const duration = row.processingDurationSeconds ?? row.processing_duration_seconds
  if (duration) {
    return `耗时 ${formatSeconds(duration)}`
  }
  return '已完成'
}

function formatSeconds(totalSeconds) {
  const seconds = Number(totalSeconds) || 0
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const remain = seconds % 60
  return remain ? `${minutes} 分 ${remain} 秒` : `${minutes} 分`
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
  const hasProcessing = templates.value.some((template) => template.status === 'processing')
  if (hasProcessing && !pollTimer) {
    pollTimer = window.setInterval(() => {
      loadTemplates()
    }, 5000)
    clockTimer = window.setInterval(() => {
      nowTick.value = Date.now()
    }, 1000)
  } else if (!hasProcessing) {
    stopPolling()
  }
}

onMounted(async () => {
  await Promise.all([loadTemplates(), loadParserStatus()])
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.parser-status-card {
  border-left: 4px solid #6b7280;
}

.status-openai {
  border-left-color: #16a34a;
}

.status-heuristic {
  border-left-color: #d97706;
}

.status-unavailable {
  border-left-color: #dc2626;
}

.quality-warning {
  color: #b45309;
  font-weight: 600;
}

.quality-ok {
  color: #15803d;
}

.progress-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-meta strong {
  font-size: 13px;
}

.progress-meta span {
  color: #64748b;
  font-size: 12px;
}
</style>
