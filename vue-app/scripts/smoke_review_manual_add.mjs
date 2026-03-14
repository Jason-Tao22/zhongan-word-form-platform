import path from 'node:path'
import process from 'node:process'

import { chromium } from 'playwright'

const baseUrl = process.argv[2] || 'http://127.0.0.1:5173/'
const uploadPath = process.argv[3]

if (!uploadPath) {
  console.error('Usage: node smoke_review_manual_add.mjs <baseUrl> <filePath>')
  process.exit(1)
}

async function run() {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  const result = { baseUrl, uploadPath }

  try {
    await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 120_000 })
    await page.getByRole('heading', { name: 'Word 模板上传与审核' }).waitFor({ timeout: 30_000 })

    await page.locator('input[type="file"]').setInputFiles(uploadPath)
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
      { timeout: 600_000 },
    )

    await page.locator('.preview-body').waitFor({ timeout: 120_000 })

    const targetId = await page.evaluate(() => {
      const controlIds = new Set(
        [...document.querySelectorAll('[data-control-id]')]
          .map(el => el.getAttribute('data-control-id'))
          .filter(Boolean),
      )

      const candidates = [...document.querySelectorAll('[data-review-id]')]
        .map(el => ({
          id: el.getAttribute('data-review-id'),
          text: (el.innerText || '').trim(),
          className: String(el.className || ''),
        }))
        .filter(item => item.id && (item.id.startsWith('cell-') || item.id.startsWith('paragraph-')) && !controlIds.has(item.id))

      return (
        candidates.find(item => item.className.includes('blank-line'))?.id
        || candidates.find(item => !item.text)?.id
        || candidates.find(item => item.id.startsWith('paragraph-'))?.id
        || candidates[0]?.id
        || null
      )
    })

    if (!targetId) {
      throw new Error('No candidate empty slot found for manual control')
    }

    result.targetId = targetId
    await page.locator(`[data-review-id="${targetId}"]`).first().click()
    await page.locator('.manual-control-panel').waitFor({ timeout: 30_000 })

    await page.locator('.manual-control-panel input').first().fill('自动化补录测试')

    const typeSelect = page.locator('.manual-control-panel .el-select').first()
    await typeSelect.click()
    await page.locator('.el-select-dropdown:visible').last().getByText('多行文本', { exact: true }).click()

    await page.getByRole('button', { name: '补到这里' }).click()
    await page.locator('.el-message__content').filter({ hasText: '已补充控件' }).first().waitFor({ timeout: 60_000 })
    await page.locator(`[data-control-id="${targetId}"]`).waitFor({ timeout: 30_000 })

    result.addedControlText = await page.locator(`[data-control-id="${targetId}"]`).innerText()
    await page.getByRole('button', { name: '保存纠错' }).click()
    await page.locator('.el-message__content').filter({ hasText: '模板纠错已保存' }).first().waitFor({ timeout: 60_000 })

    await page.reload({ waitUntil: 'networkidle', timeout: 120_000 })
    await page.locator(`[data-control-id="${targetId}"]`).waitFor({ timeout: 120_000 })
    result.persistedControlText = await page.locator(`[data-control-id="${targetId}"]`).innerText()
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
