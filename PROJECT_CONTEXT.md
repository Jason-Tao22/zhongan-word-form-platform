# 项目上下文文档

给下一个 AI 看的：这个文件记录了我们目前做的所有事情，请从头理解，然后继续。

当前交付入口已切换到：

- [README.md](/Users/yifantao/Documents/ZhongAn/README.md)
- [DELIVERY_STATUS.md](/Users/yifantao/Documents/ZhongAn/DELIVERY_STATUS.md)

注意：

- 下面很多章节保留了历史演进信息。
- 旧的 `vue-components/`、`latest-delivery/`、根目录原型 HTML 已经移除。
- 若历史章节与当前 README / DELIVERY_STATUS 冲突，以当前文档为准。

---

## 0、最新状态（2026-03-08）

这一节优先级最高。本文档下面较早的章节仍保留了历史方案，若与本节冲突，以这里和根目录 README 为准。

- 当前真实运行路径只有三个目录：
  - [word-parser-service](/Users/yifantao/Documents/ZhongAn/word-parser-service)
  - [spring-boot-app](/Users/yifantao/Documents/ZhongAn/spring-boot-app)
  - [vue-app](/Users/yifantao/Documents/ZhongAn/vue-app)
- 解析链路当前是 `OpenAI 主路径`：
  - `OPENAI_API_KEY` 必填
  - `ALLOW_HEURISTIC_FALLBACK` 默认关闭
  - parser 状态接口：`GET /config-status`
  - Spring 透传状态：`GET /api/templates/parser-status`
- 后端当前主链路：
  - 上传异步解析
  - 审核阶段允许保存 schema 纠错
  - 发布时按 schema 建 PostgreSQL 表
  - 正式表单可创建、保存、提交
- 审核页当前能力：
  - 左右联动定位
  - 已识别控件改类型
  - 对漏识别区域手工补控件
  - 保存后立即回写 schema
- `.doc` 当前策略：
  - 优先 `textutil -> HTML -> 真实表格块`
  - 仅在 HTML 结构无法恢复时才降到文本兜底
  - `DOCVARIABLE / MERGEFORMAT / PAGE` 已做清理，并通过真实重新上传验证
- 交付数据库目标已切到 PostgreSQL：
  - 推荐通过 `spring-boot-app/scripts/run_with_postgres.sh` 启动
  - H2 只保留开发兜底路径，不再作为交付主库
- 当前主要验证结论：
  - parser `41` 个测试通过
  - `mvn test -q` 通过
  - `npm run build` 通过
  - 真实浏览器已跑通：
    - 上传 -> 审核 -> 发布 -> 正式表单
    - 审核页手工补控件 -> 保存纠错 -> 刷新后仍存在
- 项目结构已做一次清理：
  - 旧的 `vue-components/` 已删除
  - 旧的 `latest-delivery/` 已删除
  - 根目录临时原型 HTML 已删除
  - 前端 `dist/`、后端 `target/`、旧 H2 文件、旧 parser 缓存已清理
  - 自动 `textarea` 高度跟随 Word 空白区域
- 已在真实样本上验证：
  - `20.05压力容器特种设备定期检验意见通知书（1）.docx`：`问题和意见` 区为 `textarea(minHeightPx=236)`，尾部 `使用单位代表 / 日期` 已变成可填 token
  - `80.02工业管道年度检查报告.docx`：块级 AI 分类产出 `11` 个行内选项组 hint
- 当前本地验证栈：
  - parser: `http://127.0.0.1:8001`
  - spring boot: `http://127.0.0.1:8080`
  - vue dev: `http://127.0.0.1:5173`

---

## 一、需求背景

客户是一个 ERP 系统团队，需要做一个功能：

> 用户上传带表格的 Word 文档（.docx），系统自动：
> 1. 将 Word 表格转换成可填写的 Vue 网页表单
> 2. 表格中的字段自动在 PostgreSQL 里建表
> 3. 用户在网页上填写数据，数据存入数据库
> 4. 生成的网页视觉上要跟原 Word 表格基本一致（有边框、合并单元格）

**关键约束：**
- Word 文档没有固定格式，由用户随时上传不同类型的报告
- 必须有人工审核步骤，AI 生成的结果不能直接写入生产环境
- 前端：Vue 3 + Element Plus
- 后端：Spring Boot 3 + PostgreSQL
- AI：Claude API（已有 API Key，已充值）

---

## 二、技术方案

### 核心架构

```
用户上传 .docx
  → Python 微服务（FastAPI）
      → 解析 Word XML（获取表格、合并单元格）
      → 调用 Claude API 做语义分析（字段类型识别）
      → 后处理（补全 sqlColumn/sqlType、重建 layout 结构）
      → 输出：JSON Schema + PostgreSQL DDL
  → Spring Boot 后端
      → 执行 DDL 动态建表
      → 存储 JSON Schema 到 t_form_template 表
  → Vue 前端
      → 通用 FormRenderer 组件读取 JSON Schema
      → 动态渲染出 Word 风格表格表单
      → 用户填写后提交到 Spring Boot
      → 数据存入动态建的 PostgreSQL 表
```

### 为什么不生成 .vue 文件

Vue 项目运行时无法动态加载新 .vue 文件（需要重新编译）。所以用 JSON Schema + 通用渲染器，这是低代码平台的标准方案。

### 为什么用 Python 微服务而不是 Java

- python-docx + lxml 解析 Word XML 更方便（直接拿到 colspan/rowspan）
- Java 的 Apache POI 可以但更繁琐
- 这个服务调用频率极低（只在上传时调用），独立部署成本低
- Spring Boot 只需一个 HTTP 调用

---

## 三、JSON Schema 格式

这是整个系统的核心契约，Python 输出、Spring Boot 存储、Vue 消费。

### 顶层结构

```json
{
  "schemaVersion": "1.0",
  "templateId": "uuid",
  "templateName": "工业管道年度检查报告",
  "sourceFile": "xxx.docx",
  "createdAt": "2026-03-02T00:00:00Z",
  "sqlDatabase": "postgresql",
  "subForms": [...]
}
```

### subForm（每张子表 = 一张 SQL 表）

```json
{
  "id": "cover_info",
  "name": "封面信息",
  "sqlTableName": "t_insp_cover_info",
  "recordType": "single",   // single=整表一条记录, multi=每行一条记录
  "layout": { ... },        // 布局结构（见下）
  "fields": [ ... ]         // 字段定义（见下）
}
```

### layout.type 四种类型

| 类型 | 适用场景 | 示例 |
|---|---|---|
| `key-value` | 左列标签、右列输入框 | 封面信息、基本信息 |
| `data-grid` | 带表头的多行数据录入 | 管道一览表、测厚数据 |
| `checklist` | 逐条检查项列表 | 年度检查记录、外观检验 |
| `section-group` | 多个分块各有标题 | 安全附件检查 |

### key-value layout

```json
{
  "type": "key-value",
  "rows": [
    [
      { "kind": "label", "text": "装置名称", "colspan": 1, "rowspan": 1 },
      { "kind": "input", "fieldId": "device_name", "colspan": 1, "rowspan": 1 }
    ]
  ]
}
```

### data-grid layout

```json
{
  "type": "data-grid",
  "headers": [
    [
      { "text": "序号", "rowspan": 2, "colspan": 1 },
      { "text": "允许工作条件", "rowspan": 1, "colspan": 3 }
    ],
    [
      { "text": "压力MPa" }, { "text": "温度℃" }, { "text": "介质" }
    ]
  ],
  "dataColumns": ["seq_no", "pipe_code", "inspection_conclusion", ...],
  "defaultRowCount": 12
}
```

### checklist layout

```json
{
  "type": "checklist",
  "columns": ["序号", "检查项目", "检查结果", "备注"],
  "items": [
    { "seq": "1", "label": "安全管理情况", "fieldId": "safety_mgmt", "remarkFieldId": "safety_mgmt_remark" },
    {
      "seq": "3",
      "label": "安全附件检查",
      "subItems": [
        { "label": "安全阀", "fieldId": "safety_valve" },
        { "label": "爆破片", "fieldId": "rupture_disc" }
      ]
    }
  ]
}
```

### section-group layout

```json
{
  "type": "section-group",
  "sections": [
    {
      "title": "安全阀检查",
      "rows": [
        [
          { "label": "型号是否符合设计", "fieldId": "sv_model_meets", "colspan": 1 }
        ]
      ]
    }
  ]
}
```

### field 定义

```json
{
  "id": "inspection_conclusion",
  "label": "检查结论",
  "type": "radio",                              // text/number/textarea/date/radio/select/checkbox_group/static
  "options": ["符合要求", "基本符合要求", "不符合要求"],  // radio/select 专用
  "sqlColumn": "inspection_conclusion",
  "sqlType": "VARCHAR(50)",
  "required": false,
  "isPrefix": false                             // data-grid 中的前置字段（表头信息）
}
```

---

## 四、已完成的代码文件

### Python 微服务（`/word-parser-service/`）

| 文件 | 作用 |
|---|---|
| `main.py` | FastAPI 入口，`POST /parse-word` |
| `word_parser.py` | 解析 docx XML，提取表格和合并单元格（已测试通过） |
| `ai_analyzer.py` | 调用 Claude API，分批处理（每批 4 张表），返回 subForms list |
| `post_processor.py` | 补全 AI 输出：sqlColumn/sqlType、重建 layout.rows/headers/items/sections |
| `ddl_generator.py` | 从 subForms list[dict] 生成 PostgreSQL DDL |
| `models.py` | Pydantic 数据模型定义 |
| `requirements.txt` | 依赖：fastapi, uvicorn, python-docx, lxml, anthropic, pydantic |

### Vue 组件（`/vue-components/`）

| 文件 | 作用 |
|---|---|
| `FieldInput.vue` | 单字段渲染（el-input/el-date-picker/el-radio-group/el-select 等） |
| `FormRenderer.vue` | 核心：读 JSON Schema，用 `<table>` 渲染 Word 风格表单（有边框、合并单元格） |
| `FormPage.vue` | 路由页面示例，拉取 Schema，调提交接口 |

### 接口文档（`/spring-boot-api-docs.md`）

完整的 Spring Boot 接口规范，包含所有接口的路径、请求格式、响应格式、处理逻辑、动态 SQL 安全注意事项。

### 其他

| 文件 | 作用 |
|---|---|
| `schema-format.json` | JSON Schema 格式规范示例（手写的，基于真实 Word 文档） |
| `test_output.json` | AI 分析的原始输出 |
| `test_output_processed.json` | 后处理后的完整 Schema（14 个 subForm） |
| `test_output.ddl.sql` | 生成的 PostgreSQL DDL（15 张表） |
| `word-parser-service/prototype_builder.py` | 直接复用 Word 表格结构生成高保真 HTML 原型，支持本地草稿和导出 JSON |
| `word-parser-service/prototype_renderer.py` | CLI 原型生成器，支持 `.docx/.doc` 输入，可选加载 schema 生成交互原型 |
| `word-parser-service/doc_converter.py` | `.doc -> .docx` 转换封装，依赖 LibreOffice/soffice |
| `word-parser-service/batch_generate_prototypes.py` | 批量把目录中的 Word 模板生成 HTML 原型 |
| `word-parser-service/regression_check.py` | 一键跑 `Word -> post_process -> schema -> DDL -> 原型 HTML` 的本地回归脚本 |
| `word-parser-service/tests/test_regression.py` | 基于样本模板的自动化回归测试 |
| `word-parser-service/run_tests.py` | 运行回归测试的入口脚本 |
| `word-parser-service/publish_delivery.py` | 重新生成 latest-delivery 样本交付，并写入 manifest |
| `word-parser-service/verify_delivery.py` | 校验 latest-delivery 下文件与 manifest 的 hash/大小是否一致 |

---

## 四点五、最近新增进展（2026-03-07）

这一部分是 Claude 写文档之后，Codex 继续做的内容。

### 1. Python 微服务主链路已修正

之前 `main.py` 有两个实际问题：
- 没有调用 `post_process`
- DDL 生成时把 `FormSchema` 对象直接传给了 `generate_ddl`

现在已修复为：
- AI 输出先走 `post_process`
- 再组装 `FormSchema`
- DDL 基于 `schema_obj.model_dump()["subForms"]` 生成

另外 `POST /parse-word` 已新增：
- 支持 `.docx` 和 `.doc`
- `include_prototype=true` 时可在响应里附带 HTML 原型字符串

### 2. word_parser 已增强，提取更多视觉信息

除了原有的：
- 文本
- colspan
- rowspan

现在还能提取：
- 单元格宽度（width_twips）
- 水平对齐（align）
- 垂直对齐（v_align）
- 底纹颜色（shading）
- 是否加粗（is_bold）
- 段落文本（paragraphs）

这些信息已经在后处理阶段进入 schema 的 layout.style 中，供正式 Vue 页面使用。

### 3. schema 现在支持样式元数据

`models.py` 新增了 `CellStyle`，以下 layout 节点都可带样式：
- key-value 的 label/input/static cell
- data-grid 的 header cell
- section-group 的 title / label / input

样式字段包括：
- `widthPx`
- `textAlign`
- `verticalAlign`
- `backgroundColor`
- `fontWeight`

### 4. post_processor 做了一轮脏数据兼容

当前 AI 原始输出里存在的几个问题已经做了兼容：
- 96 个字段使用 `name` 而不是 `label`
- 个别字段 `type` 被错误输出为 `data-grid`
- `section-group` 的 `sections` 只有 `fieldIds`，没有 `rows`
- 最后一张图示表没有对应的 Word table，也没有可直接渲染的 layout

现在 `post_processor.py` 已能把这些脏数据收敛成可通过 `FormSchema` 校验的结构。

### 5. 高保真 HTML 原型链路已补齐

新方向不是只走 `JSON Schema -> Vue`，而是保留两条线：

1. **高保真原型线**
   - Word 直接转 HTML 原型
   - 适合演示、比对“像不像”、人工审核

2. **ERP 正式表单线**
   - `JSON Schema + Vue FormRenderer`
   - 适合正式接入 ERP

这样做的原因是：
- 纯 schema 抽象会丢失一部分版式信息
- 原型线可以先证明“高保真网页可行”

### 6. Vue 组件已往 ERP 正式页面方向重写

`vue-components/FormRenderer.vue` 和 `FieldInput.vue` 已重写一轮：
- 页面风格从“演示页”收敛到更像 ERP 后台
- 可读取后处理后写进 schema 的样式元数据
- `data-grid` 的行操作放到表格外，避免破坏原表格结构
- `checklist` 的子项列结构做了兼容
- `section-group` 里的静态图示/说明字段不再重复渲染

`FormPage.vue` 也已改成和接口文档一致的提交路径：
- `POST /api/forms/{templateId}/submissions`

### 7. 本地验证结果（Codex 新增）

#### 样本回归

对 `03报告/3压力管道/80.02工业管道年度检查报告.docx` 已跑通：

`Word -> post_process -> FormSchema 校验 -> DDL -> 交互原型 HTML`

生成文件在：
- `word-parser-service/output/regression/80.02工业管道年度检查报告.schema.checked.json`
- `word-parser-service/output/regression/80.02工业管道年度检查报告.ddl.sql`
- `word-parser-service/output/regression/80.02工业管道年度检查报告.interactive.html`

并额外复制到更短路径：
- `latest-delivery/sample.schema.checked.json`
- `latest-delivery/sample.ddl.sql`
- `latest-delivery/sample.interactive.html`

#### 自动化测试

已新增自动化回归测试：

- `cd word-parser-service`
- `PYTHONDONTWRITEBYTECODE=1 python3 run_tests.py`

当前结果：
- `5` 个测试全部通过
- 覆盖 schema 校验、style 透传、section-group 兜底 layout、DDL 生成、交互原型 HTML 控件存在性

#### 交付发布与校验

已新增两个脚本用于把当前样本固化成可校验交付：

- `cd word-parser-service`
- `PYTHONDONTWRITEBYTECODE=1 python3 publish_delivery.py`
- `PYTHONDONTWRITEBYTECODE=1 python3 verify_delivery.py`

效果：
- 重新生成 `latest-delivery/sample.*`
- 自动写入 `latest-delivery/manifest.json`
- 校验文件大小和 sha256，避免“目录里有文件但不确定是不是最新的”

#### 批量原型

`03报告` 目录下：
- 30 个 `.docx` 模板全部能生成 HTML 原型
- 25 个 `.doc` 因当前环境未安装 `soffice`，被明确跳过，不是脚本崩溃

### 8. 当前结论

目前最稳妥的产品路线是：

1. 上传 Word
2. Python 微服务解析并输出：
   - 可审核的高保真 HTML 原型
   - 可落库的 JSON Schema
   - DDL
3. 管理员先看 HTML 原型确认“长得像不像”
4. 再发布到 ERP 正式 Vue 页面

也就是说：
- **HTML 原型** 负责“高保真预览/审核”
- **Vue FormRenderer** 负责“正式录入/提交”

---

## 五、端到端测试结果

用的 Word 文件：`80.02工业管道年度检查报告.docx`（14 张子表）

**测试通过情况：**

| 步骤 | 结果 |
|---|---|
| Word 解析（14 张表，含合并单元格） | ✅ 全部正确 |
| AI 分析（分 4 批调用 Claude） | ✅ 返回 14 个 subForm |
| 字段类型识别（radio/select/date/number） | ✅ 准确 |
| □ 格式识别为 radio | ✅ |
| A.B.C. 格式识别为 select（含完整 options） | ✅ |
| 后处理补全 sqlColumn/sqlType | ✅ 全部 |
| 重建 layout.rows（key-value） | ✅ |
| 重建 layout.headers（data-grid，含多级表头） | ✅ |
| 重建 layout.items（checklist） | ✅ |
| DDL 生成（15 张表，含外键、索引） | ✅ |

**已知问题/待优化：**
- AI 有时用 `name` 代替 `label`（post_processor 已兼容处理）
- AI 有时输出无效 field type（post_processor 已降级为 text）
- section-group 的 sections 结构 AI 有时格式不对（post_processor 从 word_parser 重建）
- 壁厚测定（Table 14）是图示说明，没有实际字段，生成的表只有 2 列（正常）

---

## 六、Spring Boot 接口汇总

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/templates/upload` | 上传 Word，调 Python，建表，存 Schema |
| GET | `/api/templates` | 模板列表 |
| GET | `/api/templates/{id}/schema` | 获取 JSON Schema（Vue 用）|
| DELETE | `/api/templates/{id}` | 软删除模板 |
| POST | `/api/forms/{templateId}/submissions` | 提交表单或保存草稿 |
| GET | `/api/forms/{templateId}/submissions` | 提交列表 |
| GET | `/api/forms/submissions/{id}` | 详情（含数据回显）|
| PUT | `/api/forms/submissions/{id}` | 更新草稿 |
| DELETE | `/api/forms/submissions/{id}` | 删除草稿 |
| POST | `/api/forms/submissions/{id}/submit` | 提交审核 |
| POST | `/api/forms/submissions/{id}/approve` | 审批通过 |
| POST | `/api/forms/submissions/{id}/reject` | 审批驳回 |

---

## 七、下一步

1. **把 Vue 组件接入真实前端工程**：当前 `vue-components/` 只是组件文件，还没有接到完整可运行的 Vue 项目里
2. **做一轮真实浏览器验收**：目前已完成 Python 侧和产物侧验证，但还缺完整前端工程中的实际渲染验收
3. **Spring Boot 实现**：按接口文档实现动态建表、草稿、提交流程
4. **人工审核页面**：优先展示 HTML 原型 + schema 摘要，管理员确认后再发布
5. **`.doc` 转换部署策略**：服务器若没有 `soffice`，则要明确为“只收 `.docx`”或单独部署转换能力
6. **更多模板测试**：继续验证压力容器、电梯、起重机械等模板在正式 Vue 页中的表现

---

## 八、环境信息

- Anthropic API Key：已有（不在本文档里存，从环境变量 `ANTHROPIC_API_KEY` 读）
- Python 版本：3.9（系统自带）
- 依赖安装：`pip3 install -r word-parser-service/requirements.txt`
- 启动微服务：`cd word-parser-service && ANTHROPIC_API_KEY=xxx uvicorn main:app --reload --port 8001`
- 测试：`curl -X POST http://localhost:8001/parse-word -F "file=@../80.02工业管道年度检查报告.docx"`
