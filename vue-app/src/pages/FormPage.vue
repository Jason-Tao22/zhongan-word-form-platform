<template>
  <div class="page-wrap">
    <div v-if="loading" class="page-card state-card">加载中...</div>
    <div v-else-if="error" class="page-card state-card error">{{ error }}</div>
    <template v-else>
      <div class="page-card page-header">
        <div>
          <div class="kicker">Template Form</div>
          <h2>{{ schema.templateName }}</h2>
        </div>
        <RouterLink to="/" class="inline-link">返回模板列表</RouterLink>
      </div>
      <FormRenderer
        :schema="schema"
        @submit="onSubmit"
        @save-draft="onSaveDraft"
      />
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiFetch } from '../api/client'
import FormRenderer from '../components/FormRenderer.vue'

const route = useRoute()
const templateId = route.params.templateId

const schema = ref(null)
const loading = ref(true)
const error = ref(null)

onMounted(async () => {
  try {
    schema.value = await apiFetch(`/api/templates/${templateId}/schema`)
  } catch (e) {
    error.value = `加载模板失败：${e.message}`
  } finally {
    loading.value = false
  }
})

async function onSubmit(formData) {
  try {
    await apiFetch(`/api/forms/${templateId}/submissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'submitted', formData }),
    })
    ElMessage.success('提交成功')
  } catch (e) {
    ElMessage.error(`提交失败：${e.message}`)
  }
}

async function onSaveDraft(formData) {
  try {
    await apiFetch(`/api/forms/${templateId}/submissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'draft', formData }),
    })
    ElMessage.success('草稿已保存')
  } catch (e) {
    ElMessage.error(`保存失败：${e.message}`)
  }
}
</script>
