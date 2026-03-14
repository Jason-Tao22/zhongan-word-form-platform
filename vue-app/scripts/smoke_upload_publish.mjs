import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

import { chromium } from 'playwright'

const baseUrl = process.argv[2] || 'http://127.0.0.1:5173/'
const uploadPath = process.argv[3]
const apiBaseUrl = process.argv[4] || 'http://127.0.0.1:8080'

if (!uploadPath) {
  console.error('Usage: node smoke_upload_publish.mjs <baseUrl> <filePath>')
  process.exit(1)
}

const artifactDir = path.resolve(process.cwd(), 'output', 'playwright-smoke')

async function run() {
  await fs.mkdir(artifactDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  const result = { baseUrl, uploadPath }

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 60_000 })
    await page.getByRole('heading', { name: 'Word 模板上传与审核' }).waitFor({ timeout: 30_000 })

    const fileInput = page.locator('input[type="file"]')
    await fileInput.setInputFiles(uploadPath)
    result.selectedFile = path.basename(uploadPath)

    await page.getByRole('button', { name: '上传并生成' }).click()

    const reviewLoaded = page.waitForURL(/\/templates\/.+\/review$/, { timeout: 600_000 })
    const uploadFailed = page.locator('.el-message__content').filter({ hasText: '上传失败' }).first().waitFor({ timeout: 600_000 })
    const winner = await Promise.race([
      reviewLoaded.then(() => 'review'),
      uploadFailed.then(() => 'error'),
    ])

    if (winner === 'error') {
      result.error = await page.locator('.el-message__content').first().textContent()
      await page.screenshot({ path: path.join(artifactDir, 'upload-error.png'), fullPage: true })
      throw new Error(result.error)
    }

    result.reviewUrl = page.url()
    await page.waitForFunction(
      () => {
        const text = document.body.innerText || ''
        if (text.includes('解析失败：')) {
          return 'failed'
        }
        if (text.includes('模板正在后台解析中')) {
          return false
        }
        const hasAction = Array.from(document.querySelectorAll('button,a')).some((node) => {
          const text = (node.textContent || '').trim()
          return text === '确认发布' || text === '打开正式表单'
        })
        const hasLegacyPreview = Boolean(document.querySelector('iframe.preview-frame'))
        const hasRendererPreview = Boolean(document.querySelector('.preview-body'))
        const hasEditor = text.includes('控件纠错')
        return hasAction || hasLegacyPreview || hasRendererPreview || hasEditor ? 'ready' : false
      },
      undefined,
      { timeout: 600_000 }
    )

    const reviewText = await page.locator('body').innerText()
    if (reviewText.includes('解析失败：')) {
      result.error = reviewText
      await page.screenshot({ path: path.join(artifactDir, 'review-error.png'), fullPage: true })
      throw new Error('Template parsing failed during review stage')
    }
    result.reviewHasEditor = reviewText.includes('控件纠错')

    const publishButton = page.getByRole('button', { name: '确认发布' })
    if (await publishButton.count()) {
      await publishButton.waitFor({ state: 'visible', timeout: 120_000 })
      await publishButton.scrollIntoViewIfNeeded()
      try {
        await publishButton.click({ timeout: 30_000, force: true })
      } catch (error) {
        await page.evaluate(() => {
          const button = Array.from(document.querySelectorAll('button'))
            .find((node) => (node.textContent || '').trim() === '确认发布')
          if (!button) {
            throw new Error('确认发布按钮不存在')
          }
          button.click()
        })
      }
      await page.waitForURL(/\/templates\/.+\/form$/, { timeout: 120_000 })
    } else {
      await page.getByText('打开正式表单').click()
      await page.waitForURL(/\/templates\/.+\/form$/, { timeout: 120_000 })
    }

    result.formUrl = page.url()
    const templateId = page.url().match(/\/templates\/([^/]+)\/form$/)?.[1]
    await page.getByRole('heading').nth(0).waitFor({ timeout: 30_000 })

    const inlineFill = page.locator('input.inline-fill').first()
    if (await inlineFill.count()) {
      await inlineFill.fill('smoke')
    }

    const autoInput = page.locator('input.auto-input').first()
    if (await autoInput.count()) {
      await autoInput.fill('smoke')
    }

    const autoTextarea = page.locator('textarea.auto-textarea').first()
    if (await autoTextarea.count()) {
      await autoTextarea.fill('smoke textarea')
    }

    if (!templateId) {
      throw new Error(`Cannot infer templateId from form url: ${page.url()}`)
    }

    const saveDraftButton = page.getByRole('button', { name: '保存草稿' }).first()
    await saveDraftButton.click()
    await waitForDraftSubmission(templateId)

    await page.screenshot({ path: path.join(artifactDir, 'form-page.png') })
    result.status = 'ok'
  } finally {
    console.log(JSON.stringify(result, null, 2))
    await browser.close()
  }
}

async function waitForDraftSubmission(templateId) {
  const deadline = Date.now() + 120_000
  while (Date.now() < deadline) {
    const response = await fetch(`${apiBaseUrl}/api/forms/${templateId}/submissions?page=1&size=5`)
    if (response.ok) {
      const payload = await response.json()
      const total = payload?.data?.total ?? 0
      const firstStatus = payload?.data?.list?.[0]?.status
      if (total > 0 && firstStatus === 'draft') {
        return
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }
  throw new Error(`Timed out waiting for draft submission for template ${templateId}`)
}

run().catch((error) => {
  console.error(error)
  process.exit(1)
})
