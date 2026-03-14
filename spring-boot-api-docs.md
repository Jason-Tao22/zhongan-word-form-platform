# Spring Boot 接口文档

Word → 表单系统后端接口规范
版本：v1.0 | 数据库：PostgreSQL | 前端：Vue 3 + Element Plus

---

## 概述

### 整体架构

```
Vue 前端
  ↕ HTTP
Spring Boot 后端          ← 本文档描述的接口
  ↕ HTTP (内网)
Python 微服务（/parse-word）
```

### 需要维护的固定表（手动建，不是动态生成的）

```sql
-- 模板元数据表
CREATE TABLE t_form_template (
    id              VARCHAR(64)   PRIMARY KEY,        -- UUID
    name            VARCHAR(200)  NOT NULL,
    source_file     VARCHAR(500),
    schema_json     JSONB         NOT NULL,           -- 完整 JSON Schema
    ddl_sql         TEXT          NOT NULL,           -- 生成的 DDL（留档）
    created_by      VARCHAR(100),
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    status          VARCHAR(20)   NOT NULL DEFAULT 'active'
);

-- 提交主记录表（由 DDL 生成，此处仅供参考）
CREATE TABLE t_form_submission (
    id              BIGSERIAL     PRIMARY KEY,
    template_id     VARCHAR(64)   NOT NULL REFERENCES t_form_template(id),
    template_name   VARCHAR(200),
    submitted_by    VARCHAR(100),
    submitted_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    status          VARCHAR(20)   NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'approved', 'rejected'))
);
```

---

## 一、模板管理

### 1.1 上传 Word 文档，生成模板

```
POST /api/templates/upload
Content-Type: multipart/form-data
```

**Request**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| file | File | ✅ | .docx 文件 |

**Spring Boot 处理逻辑**

```
1. 接收 .docx 文件
2. 转发给 Python 微服务：
   POST http://{PYTHON_SERVICE_HOST}/parse-word
   Body: multipart/form-data (同样的文件)
3. 拿到 Python 返回的 { schema, ddl }
4. 执行 ddl（在 PostgreSQL 里动态建表）
   注意：用事务包裹，失败则回滚
5. 将 schema_json 存入 t_form_template
6. 返回 templateId 给前端
```

**Response 200**

```json
{
  "code": 0,
  "data": {
    "templateId": "550e8400-e29b-41d4-a716-446655440000",
    "templateName": "工业管道年度检查报告",
    "subFormCount": 14,
    "createdAt": "2026-03-02T10:00:00Z"
  }
}
```

**Response 错误**

```json
{ "code": 400, "msg": "只支持 .docx 格式" }
{ "code": 502, "msg": "AI 解析服务异常，请稍后重试" }
{ "code": 500, "msg": "数据库建表失败：duplicate column name xxx" }
```

---

### 1.2 获取模板列表

```
GET /api/templates?page=1&size=20&keyword=管道
```

**Query 参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| page | int | 1 | 页码 |
| size | int | 20 | 每页条数 |
| keyword | string | — | 按模板名称模糊搜索 |

**Response 200**

```json
{
  "code": 0,
  "data": {
    "total": 5,
    "list": [
      {
        "templateId": "550e8400-...",
        "templateName": "工业管道年度检查报告",
        "sourceFile": "80.02工业管道年度检查报告.docx",
        "subFormCount": 14,
        "createdBy": "admin",
        "createdAt": "2026-03-02T10:00:00Z",
        "status": "active"
      }
    ]
  }
}
```

---

### 1.3 获取模板 JSON Schema（Vue FormRenderer 专用）

```
GET /api/templates/{templateId}/schema
```

**Response 200**

直接返回完整 JSON Schema（存在 `t_form_template.schema_json` 里的那个），Vue FormRenderer 直接消费。

```json
{
  "schemaVersion": "1.0",
  "templateId": "550e8400-...",
  "templateName": "工业管道年度检查报告",
  "subForms": [
    {
      "id": "cover_info",
      "name": "封面信息",
      "sqlTableName": "t_insp_cover_info",
      "recordType": "single",
      "layout": { "type": "key-value", "rows": [...] },
      "fields": [...]
    }
  ]
}
```

---

### 1.4 删除模板

```
DELETE /api/templates/{templateId}
```

**Spring Boot 处理逻辑**

```
1. 检查是否有关联的 submission 记录，有则拒绝删除（返回 409）
2. 将 t_form_template.status 置为 'inactive'（软删除，不删动态表）
```

**Response 200**

```json
{ "code": 0, "msg": "删除成功" }
```

---

## 二、表单提交

### 2.1 提交表单（或保存草稿）

```
POST /api/forms/{templateId}/submissions
Content-Type: application/json
```

**Request Body**

```json
{
  "status": "submitted",
  "formData": {
    "cover_info": {
      "device_name": "XX 装置",
      "use_unit_name": "XX 公司",
      "inspection_date": "2026-03-01"
    },
    "conclusion_report_appendix": {
      "_rows": [
        {
          "seq_no": 1,
          "pipe_code": "P-001",
          "pipe_name": "主蒸汽管道",
          "inspection_conclusion": "符合要求",
          "pressure": 10.5,
          "temperature": 350.0,
          "medium": "蒸汽",
          "problems_and_handling": "无",
          "remark": ""
        }
      ]
    }
  }
}
```

**字段说明**

| 字段 | 类型 | 说明 |
|---|---|---|
| status | string | `draft`（草稿）或 `submitted`（正式提交） |
| formData | object | key 是 subForm.id，value 是该子表的填写数据 |
| formData.xxx | object | `recordType=single` 的子表：直接是字段键值对 |
| formData.xxx._rows | array | `recordType=multi` 的子表：每个元素是一行数据 |

**Spring Boot 处理逻辑**

```
1. 查 t_form_template 拿到 schema_json
2. 开启事务：
   a. INSERT INTO t_form_submission → 得到 submissionId
   b. 遍历 schema.subForms：
      - 从 formData[subForm.id] 取数据
      - single 类型：INSERT INTO {sqlTableName} (submission_id, col1, col2...)
                     VALUES (submissionId, val1, val2...)
      - multi 类型：遍历 _rows，每行 INSERT 一条记录
   c. 所有子表插入成功 → commit
3. 返回 submissionId
```

⚠️ **重要**：动态 SQL 必须使用参数化查询，禁止字符串拼接列值，防止 SQL 注入。列名从 schema 里取（可信），值用 `?` 或命名参数。

**Response 200**

```json
{
  "code": 0,
  "data": {
    "submissionId": 1001,
    "status": "submitted",
    "submittedAt": "2026-03-02T10:30:00Z"
  }
}
```

---

### 2.2 获取提交列表

```
GET /api/forms/{templateId}/submissions?page=1&size=20&status=submitted
```

**Query 参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| page | int | 页码 |
| size | int | 每页条数 |
| status | string | 过滤状态：draft / submitted / approved / rejected |

**Response 200**

```json
{
  "code": 0,
  "data": {
    "total": 3,
    "list": [
      {
        "submissionId": 1001,
        "templateName": "工业管道年度检查报告",
        "submittedBy": "张三",
        "submittedAt": "2026-03-02T10:30:00Z",
        "status": "submitted"
      }
    ]
  }
}
```

---

### 2.3 获取单条提交详情（含填写数据，用于回显）

```
GET /api/forms/submissions/{submissionId}
```

**Spring Boot 处理逻辑**

```
1. 查 t_form_submission 得到 templateId
2. 查 t_form_template 得到 schema_json
3. 遍历 schema.subForms：
   - single：SELECT * FROM {sqlTableName} WHERE submission_id = ?
   - multi：SELECT * FROM {sqlTableName} WHERE submission_id = ? ORDER BY id
4. 组装成与提交时相同格式的 formData 返回
```

**Response 200**

```json
{
  "code": 0,
  "data": {
    "submissionId": 1001,
    "templateId": "550e8400-...",
    "status": "submitted",
    "submittedBy": "张三",
    "submittedAt": "2026-03-02T10:30:00Z",
    "formData": {
      "cover_info": {
        "device_name": "XX 装置",
        "use_unit_name": "XX 公司",
        "inspection_date": "2026-03-01"
      },
      "conclusion_report_appendix": {
        "_rows": [...]
      }
    }
  }
}
```

---

### 2.4 更新草稿

```
PUT /api/forms/submissions/{submissionId}
Content-Type: application/json
```

**Request Body** 同 2.1，status 只允许 `draft`（正式提交后不可修改）

**Spring Boot 处理逻辑**

```
1. 检查当前 status，若非 draft → 返回 403
2. 开启事务：
   a. 遍历 schema.subForms，DELETE WHERE submission_id = ?
   b. 重新 INSERT（同 2.1 步骤）
   c. 更新 t_form_submission.updated_at
```

---

### 2.5 删除提交

```
DELETE /api/forms/submissions/{submissionId}
```

仅允许删除 `draft` 状态，正式提交需走审批流程撤回。

---

## 三、审批流程（可选，一期如不需要可跳过）

### 3.1 提交审核

```
POST /api/forms/submissions/{submissionId}/submit
```

将 status 从 `draft` 改为 `submitted`。

### 3.2 审批通过

```
POST /api/forms/submissions/{submissionId}/approve
```

```json
{ "comment": "审核意见" }
```

### 3.3 审批驳回

```
POST /api/forms/submissions/{submissionId}/reject
```

```json
{ "comment": "驳回原因" }
```

---

## 四、统一响应格式

```json
{
  "code": 0,        // 0=成功，非0=失败
  "msg": "success", // 错误时有描述
  "data": {}        // 业务数据
}
```

| code | 含义 |
|---|---|
| 0 | 成功 |
| 400 | 请求参数错误 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 状态冲突（如删除有数据的模板）|
| 500 | 服务器内部错误 |
| 502 | Python 微服务调用失败 |

---

## 五、Python 微服务调用配置

Spring Boot 配置（`application.yml`）：

```yaml
word-parser:
  base-url: http://localhost:8001   # Python 微服务地址
  timeout: 120000                   # 超时 120 秒（AI 调用较慢）
```

调用示例（Spring Boot RestTemplate / WebClient）：

```java
// 转发上传文件给 Python 服务
MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
body.add("file", new MultipartInputStreamFileResource(inputStream, filename));

ResponseEntity<ParseResult> resp = restTemplate.postForEntity(
    pythonBaseUrl + "/parse-word",
    new HttpEntity<>(body, headers),
    ParseResult.class
);
```

---

## 六、动态 SQL 参考实现（Spring Boot）

```java
// 动态 INSERT（单条记录）
public void insertSingleRecord(String tableName, Long submissionId,
                                Map<String, Object> data, List<FieldDef> fields) {
    // 从 schema fields 取可写列名（type != static && sqlColumn != null）
    List<String> columns = fields.stream()
        .filter(f -> !"static".equals(f.getType()) && f.getSqlColumn() != null)
        .map(FieldDef::getSqlColumn)
        .collect(toList());

    String colPart = String.join(", ", columns);
    String valPart = columns.stream().map(c -> "?").collect(joining(", "));

    String sql = "INSERT INTO " + tableName  // 表名来自 schema，可信
               + " (submission_id, " + colPart + ") VALUES (?, " + valPart + ")";

    Object[] params = Stream.concat(
        Stream.of(submissionId),
        columns.stream().map(col -> data.getOrDefault(col, null))
    ).toArray();

    jdbcTemplate.update(sql, params);  // 值用参数化，安全
}
```

---

## 七、接口路由汇总

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/templates/upload` | 上传 Word，生成模板 |
| GET | `/api/templates` | 模板列表 |
| GET | `/api/templates/{id}/schema` | 获取 JSON Schema（Vue 用）|
| DELETE | `/api/templates/{id}` | 删除模板 |
| POST | `/api/forms/{templateId}/submissions` | 提交/保存草稿 |
| GET | `/api/forms/{templateId}/submissions` | 提交列表 |
| GET | `/api/forms/submissions/{id}` | 提交详情（含数据回显）|
| PUT | `/api/forms/submissions/{id}` | 更新草稿 |
| DELETE | `/api/forms/submissions/{id}` | 删除草稿 |
| POST | `/api/forms/submissions/{id}/submit` | 提交审核 |
| POST | `/api/forms/submissions/{id}/approve` | 审批通过 |
| POST | `/api/forms/submissions/{id}/reject` | 审批驳回 |
