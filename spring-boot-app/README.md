# Spring Boot App

本目录是可运行的后端工程，不再只是接口文档。

## 本地启动

先启动 parser：

```bash
cd ../word-parser-service
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
python3 -m uvicorn main:app --host 127.0.0.1 --port 8001
```

开发模式可直接启动：

```bash
mvn spring-boot:run
```

推荐的交付方式是本地 PostgreSQL：

```bash
./scripts/run_with_postgres.sh
```

默认地址：

- 后端 API：`http://127.0.0.1:8080`
- 解析服务：`http://127.0.0.1:8001`

## 已实现接口

- `POST /api/templates/upload`
- `POST /api/templates/{templateId}/retry`
- `GET /api/templates/parser-status`
- `POST /api/templates/{templateId}/publish`
- `GET /api/templates`
- `GET /api/templates/{templateId}`
- `GET /api/templates/{templateId}/schema`
- `DELETE /api/templates/{templateId}`
- `POST /api/forms/{templateId}/submissions`
- `GET /api/forms/{templateId}/submissions`
- `GET /api/forms/submissions/{submissionId}`
- `PUT /api/forms/submissions/{submissionId}`
- `DELETE /api/forms/submissions/{submissionId}`
- `POST /api/forms/submissions/{submissionId}/submit`
- `POST /api/forms/submissions/{submissionId}/approve`
- `POST /api/forms/submissions/{submissionId}/reject`

## 当前实现说明

- 交付目标数据库是 PostgreSQL，辅助脚本见：
  - [`scripts/start_local_postgres.sh`](scripts/start_local_postgres.sh)
  - [`scripts/run_with_postgres.sh`](scripts/run_with_postgres.sh)
- `mvn spring-boot:run` 仍可走 H2 开发兜底，但不建议作为交付运行方式
- PostgreSQL 本地默认连接：
  - `jdbc:postgresql://127.0.0.1:5432/zhongan_forms`
  - 用户名 `zhongan`
  - 密码 `zhongan_pw`
- 已启用 `spring.sql.init.mode=always`，确保 [`src/main/resources/schema.sql`](src/main/resources/schema.sql) 在运行库上自动建表
- 模板上传是异步解析：
  - 接口先返回 `processing`
  - 后台线程再调 parser
  - 成功后自动转为 `pending_review`
  - 失败后转为 `failed`
- 新增 `PUT /api/templates/{templateId}/schema`
  - 用于在审核阶段保存人工纠正后的 schema
  - 保存后模板仍保持 `pending_review`
  - 已发布模板默认不允许直接修改，避免正式表单和已建表结构漂移
- 会把上传的原始 Word 文件存到 `data/template-sources/<templateId>/`，便于重试和排查
- 即使 parser 返回的 `ddl` 为空，后端也会根据 `schema.subForms` 本地回填 DDL
- `GET /api/templates/parser-status` 可查看解析服务当前是否真的在使用 OpenAI
- 默认要求配置 `OPENAI_API_KEY`；未配置时上传会明确失败
- 模板上传结果会额外保存 `analysisMode`、`structureFingerprint`、`sourceSha256`
