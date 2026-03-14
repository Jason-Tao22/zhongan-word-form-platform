import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

import { chromium } from 'playwright'

const baseUrl = process.argv[2] || 'http://127.0.0.1:5173/'
const uploadPath = process.argv[3]

if (!uploadPath) {
  console.error('Usage: node smoke_review_edit.mjs <baseUrl> <filePath>')
  process.exit(1)
}

const artifactDir = path.resolve(process.cwd(), 'output', 'playwright-smoke')

async function run() {
  await fs.mkdir(artifactDir, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  const result = { baseUrl, uploadPath }

  try {
    await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 60_000 })
    await page.getByRole('heading', { name: 'Word 模板上传与审核' }).waitFor({ timeout: 30_000 })

    const fileInput = page.locator('input[type="file"]')
    await fileInput.setInputFiles(uploadPath)
    result.selectedFile = path.basename(uploadPath)
    await page.getByRole('button', { name: '上传并生成' }).click()

    await page.waitForURL(/\/templates\/.+\/review$/, { timeout: 600_000 })
    result.reviewUrl = page.url()

    await page.waitForFunction(
      () => {
        const text = document.body.innerText || ''
        if (text.includes('解析失败：')) return 'failed'
        if (text.includes('模板正在后台解析中')) return false
        return text.includes('控件纠错') ? 'ready' : false
      },
      undefined,
      { timeout: 600_000 }
    )

    const firstControl = page.locator('.control-item').first()
    await firstControl.waitFor({ timeout: 60_000 })

    const selectTrigger = firstControl.locator('.el-select').first()
    await selectTrigger.click()
    const visibleDropdown = page.locator('.el-select-dropdown:visible').last()
    await visibleDropdown.getByText('多行文本', { exact: true }).click()

    const saveButton = page.getByRole('button', { name: '保存纠错' })
    await saveButton.click()

    await page.locator('.el-message__content').filter({ hasText: '模板纠错已保存' }).first().waitFor({ timeout: 60_000 })

    await page.reload({ waitUntil: 'networkidle', timeout: 60_000 })
    await page.locator('.control-item').first().waitFor({ timeout: 60_000 })
    const firstControlText = await page.locator('.control-item').first().innerText()
    result.firstControlText = firstControlText
    if (!firstControlText.includes('多行文本')) {
      throw new Error(`Expected first control to persist as 多行文本, got: ${firstControlText}`)
    }

    await page.screenshot({ path: path.join(artifactDir, 'review-edit.png') })
    result.status = 'ok'
  } finally {
    console.log(JSON.stringify(result, null, 2))
    await browser.close()
  }
}

run().catch((error) => {
  console.error(error)
  process.exit(1)
})
