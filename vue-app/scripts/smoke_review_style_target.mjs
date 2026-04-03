import path from 'node:path'
import process from 'node:process'

import { chromium } from 'playwright'

const baseUrl = process.argv[2] || 'http://127.0.0.1:5173/'
const uploadPath = process.argv[3]

if (!uploadPath) {
  console.error('Usage: node smoke_review_style_target.mjs <baseUrl> <filePath>')
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
          text: (el.textContent || '').trim(),
        }))
        .filter(item => item.id && !controlIds.has(item.id))

      return (
        candidates.find(item => item.id.startsWith('paragraph-') && item.text.length >= 4)?.id
        || candidates.find(item => item.id.startsWith('cell-'))?.id
        || candidates[0]?.id
        || null
      )
    })

    if (!targetId) {
      throw new Error('No static review target found')
    }

    result.targetId = targetId
    await page.locator(`[data-review-id="${targetId}"]`).first().click()
    await page.locator('.style-adjust-panel').waitFor({ timeout: 30_000 })

    const fontFamilyInput = page.locator('[data-style-field="fontFamily"] input').first()
    await fontFamilyInput.fill('黑体')

    const fontSizeInput = page.locator('[data-style-field="fontSizePx"] input').first()
    await fontSizeInput.fill('26')
    await fontSizeInput.press('Tab')

    await page.getByRole('button', { name: '保存纠错' }).click()
    await page.locator('.el-message__content').filter({ hasText: '模板纠错已保存' }).first().waitFor({ timeout: 60_000 })

    await page.reload({ waitUntil: 'networkidle', timeout: 120_000 })
    await page.locator('.preview-body').waitFor({ timeout: 120_000 })
    await page.locator(`[data-review-id="${targetId}"]`).first().click()
    await page.locator('.style-adjust-panel').waitFor({ timeout: 30_000 })

    result.fontFamily = await page.locator('[data-style-field="fontFamily"] input').first().inputValue()
    result.fontSizePx = await page.locator('[data-style-field="fontSizePx"] input').first().inputValue()
    result.renderedStyle = await page.locator(`[data-review-id="${targetId}"]`).first().evaluate((node) => {
      const style = window.getComputedStyle(node)
      return {
        fontFamily: style.fontFamily,
        fontSize: style.fontSize,
      }
    })

    if (result.fontFamily !== '黑体') {
      throw new Error(`Expected saved fontFamily 黑体, got ${result.fontFamily}`)
    }
    if (result.fontSizePx !== '26') {
      throw new Error(`Expected saved fontSize 26, got ${result.fontSizePx}`)
    }
    if (!String(result.renderedStyle.fontFamily || '').includes('黑体')) {
      throw new Error(`Expected rendered fontFamily to include 黑体, got ${result.renderedStyle.fontFamily}`)
    }
    if (result.renderedStyle.fontSize !== '26px') {
      throw new Error(`Expected rendered fontSize 26px, got ${result.renderedStyle.fontSize}`)
    }

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
