# ZhongAn Word Form Platform

一个面向 ERP 的 Word 模板平台：

- 用户上传 `.docx/.doc`
- Python 解析文档结构并调用 OpenAI 判断控件语义
- Spring Boot 保存模板、审核结果和发布后的动态表结构
- Vue 提供审核页和正式录入页

## 公开仓库说明

这个公开仓库不再包含客户私有样本目录 `03报告/`。

仓库中保留了一个可公开分发的演示样本：

- [`samples/public-demo-template.docx`](samples/public-demo-template.docx)

如果你要验证旧版 `.doc` 兼容能力，请使用你自己的 `.doc` 文件上传测试。

## 仓库结构

- [`word-parser-service/`](word-parser-service/)
  - Word 解析、OpenAI 语义分析、schema/documentBlocks/DDL 生成
- [`spring-boot-app/`](spring-boot-app/)
  - 模板上传、审核保存、发布建表、表单提交
- [`vue-app/`](vue-app/)
  - 模板上传页、审核页、正式表单页
- [`samples/`](samples/)
  - 公开演示样本和说明
- [`DELIVERY_STATUS.md`](DELIVERY_STATUS.md)
  - 当前验证结果与已知边界
- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md)
  - 当前架构、交付背景、排查入口
- [`DEMO_GUIDE.md`](DEMO_GUIDE.md)
  - Demo 录制顺序和讲解提纲
- [`spring-boot-api-docs.md`](spring-boot-api-docs.md)
  - 接口说明
- [`schema-format.json`](schema-format.json)
  - schema 参考格式

## 工作流

1. 用户上传 Word
2. Spring Boot 异步转发到 Python parser
3. parser 提取表格、段落、合并单元格等确定性结构
4. OpenAI 判断歧义块更像输入框、文本域、单选还是复选
5. Spring Boot 保存 `schema / prototype / ddl / qualityWarning`
6. 审核页人工纠错
   - 改已有控件类型
   - 给漏识别区域手工补控件
7. 审核通过后发布模板
8. 正式表单页录入并提交

## 快速启动

先启动 parser：

```bash
cd word-parser-service
pip3 install -r requirements.txt
cp .env.example .env
# 填写 OPENAI_API_KEY
python3 -m uvicorn main:app --host 127.0.0.1 --port 8001
```

再启动后端，推荐直接用 PostgreSQL：

```bash
cd spring-boot-app
./scripts/run_with_postgres.sh
```

最后启动前端：

```bash
cd vue-app
npm install
npm run dev -- --host 127.0.0.1
```

默认地址：

- 前端：`http://127.0.0.1:5173/`
- 后端：`http://127.0.0.1:8080`
- parser：`http://127.0.0.1:8001/config-status`

## 建议验证

后端 / parser：

```bash
cd word-parser-service
python3 run_tests.py
```

```bash
cd spring-boot-app
mvn test -q
```

前端：

```bash
cd vue-app
npm run build
```

浏览器冒烟：

```bash
cd vue-app
node ./scripts/smoke_upload_publish.mjs \
  http://127.0.0.1:5173/ \
  ../samples/public-demo-template.docx \
  http://127.0.0.1:8080
```

```bash
cd vue-app
node ./scripts/smoke_review_manual_add.mjs \
  http://127.0.0.1:5173/ \
  ../samples/public-demo-template.docx
```

## 交付边界

- 生产主链路是 `OpenAI-only`，默认不再静默回退到启发式兜底
- `.docx` 保真度高于 `.doc`
- `.doc` 兼容已接入 `textutil -> HTML -> 结构恢复`，但仍建议审核页人工确认
- 审核页支持手工补控件，所以系统定位是“半自动模板工坊”，不是“零审核魔法转换器”
