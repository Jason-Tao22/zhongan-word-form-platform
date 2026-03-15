# Project Context

这个文件保留当前项目的工程背景和交付上下文，供后续开发、排查或二次接手时快速理解系统。

## 当前结论

- 项目已经收敛成 3 个主服务：
  - [`word-parser-service/`](word-parser-service/)
  - [`spring-boot-app/`](spring-boot-app/)
  - [`vue-app/`](vue-app/)
- 主链路使用 `OpenAI`，不是 Claude，也不是默认启发式兜底
- 审核页支持：
  - 控件纠错
  - 左右定位联动
  - 手工补控件
- 正式表单页支持：
  - 保存草稿
  - 提交
  - PostgreSQL 持久化

## 架构

### 1. Python parser

职责：

- 解析 `.docx/.doc`
- 提取表格、段落、合并单元格、段落顺序
- 调用 OpenAI 判断歧义块控件语义
- 生成：
  - `schema`
  - `documentBlocks`
  - `prototypeHtml`
  - `ddl`
  - `qualityWarning`

设计原则：

- 确定性结构靠代码提取
- 控件语义靠 OpenAI 判断
- 不假设 AI 一次全对

### 2. Spring Boot

职责：

- 接收前端上传
- 异步转发给 parser
- 保存模板定义和审核状态
- 发布时建表
- 接收正式表单提交

关键状态：

- `processing`
- `pending_review`
- `active`
- `failed`

### 3. Vue

职责：

- 模板上传页
- 审核页
- 正式录入页

审核页重点：

- 左侧看正式渲染效果
- 右侧改控件
- 支持给漏识别区域补控件

## 公开仓库策略

客户私有样本目录 `03报告/` 已从公开仓库移除。

公开仓库只保留：

- 一个可公开分发的演示样本 [`samples/public-demo-template.docx`](samples/public-demo-template.docx)
- 运行源码
- 文档
- 测试

如果需要验证旧版 `.doc` 兼容，使用你自己的 `.doc` 文件上传即可。

## 为什么不是直接 Word -> Vue 文件

项目没有按“每上传一个 Word 就生成一个新的 `.vue` 文件”设计，而是按“模板平台”设计：

`Word -> schema/layout -> 通用渲染器`

这样做的好处是：

- 新模板不需要新增前端组件
- 审核页可以直接修模板定义
- 正式表单页和审核页共享一套渲染逻辑

## 已知边界

- `.docx` 的保真度通常高于 `.doc`
- `.doc` 已走 `textutil -> HTML -> 结构恢复`，但仍建议人工审核
- AI 识别率不会是 100%，所以审核页必须保留人工纠错和手工补控件
- 审核页定位是“模板校对台”，不是最终用户的正式录入页

## 推荐排查顺序

1. 先看 parser 状态：
   - `http://127.0.0.1:8001/config-status`
2. 再看后端 parser 透传状态：
   - `http://127.0.0.1:8080/api/templates/parser-status`
3. 再看模板列表里的：
   - `processingStage`
   - `qualityWarning`
   - `storageTableCount`

## 当前主入口

- 项目总入口：[`README.md`](README.md)
- 当前验证结果：[`DELIVERY_STATUS.md`](DELIVERY_STATUS.md)
- Demo 录制说明：[`DEMO_GUIDE.md`](DEMO_GUIDE.md)
