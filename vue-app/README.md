# Vue App

本目录是可运行的前端工程，基于 `Vite + Vue 3 + Element Plus`。

## 本地启动

先启动：

- `../word-parser-service`
- `../spring-boot-app`

然后运行：

```bash
npm install
npm run dev -- --host 127.0.0.1
```

默认地址：

- 前端页面：`http://127.0.0.1:5173`

## 页面

- `/` 模板上传与审核页
- `/templates/:templateId/review` 原型审核页
- `/templates/:templateId/form` 正式录入页

## 当前状态

- 已接入后端真实接口，旧的 `vue-components/` 散文件组件已移除
- 已支持模板上传、审核发布、正式填表
- 模板上传是异步的；复杂 `.doc/.docx` 会先显示 `processing`
- 审核页支持自动轮询和失败重试
- 审核页使用正式渲染器实时预览，不再只看静态 HTML iframe
- 审核页右侧提供控件纠错面板，可直接把误识别控件改成 `text / textarea / radio / checkbox_group / date / number / select`
- 审核页支持给空白区域“手工补控件”，补完后会直接写回 schema
- 左右两侧支持定位联动，方便在大模板里找到对应控件
- 上传页会显示解析服务状态；未配置 `OPENAI_API_KEY` 时会直接禁用上传
- `.doc` 模板优先吃 parser 的 `legacy html` 结构恢复链路，不再默认走纯文本兜底

## 浏览器冒烟

```bash
node ./scripts/smoke_upload_publish.mjs \
  http://127.0.0.1:5173/ \
  ../samples/public-demo-template.docx \
  http://127.0.0.1:8080
```

脚本会真实执行：

- 上传模板
- 等待审核页完成解析
- 确认审核页已出现控件纠错能力
- 发布模板
- 打开正式表单
- 保存草稿

## 手工补控件冒烟

```bash
node ./scripts/smoke_review_manual_add.mjs \
  http://127.0.0.1:5173/ \
  ../samples/public-demo-template.docx
```
