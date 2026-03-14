# ZhongAn Word Form Platform

当前项目已经收敛成 3 个主服务和 1 组测试样本：

- `word-parser-service/`
  - Word 解析、OpenAI 语义分析、schema/documentBlocks/DDL 生成
- `spring-boot-app/`
  - 模板上传、审核保存、发布建表、表单提交
- `vue-app/`
  - 模板上传页、审核页、正式表单页
- `03报告/`
  - 真实 `.docx/.doc` 模板样本

## 当前工作流

1. 用户在前端上传 Word
2. Spring Boot 异步转发到 Python parser
3. parser 解析文档结构，并调用 OpenAI 补控件语义
4. Spring Boot 保存 `schema / prototype / ddl / qualityWarning`
5. 审核页人工纠错
   - 改已有控件类型
   - 给漏识别区域手工补控件
6. 审核通过后发布模板
7. 正式表单页录入并提交

## 当前项目结构

- `/Users/yifantao/Documents/ZhongAn/README.md`
  - 交付入口
- `/Users/yifantao/Documents/ZhongAn/DELIVERY_STATUS.md`
  - 当前验证结果、剩余边界
- `/Users/yifantao/Documents/ZhongAn/PROJECT_CONTEXT.md`
  - 历史上下文，保留给后续 AI / 排查参考
- `/Users/yifantao/Documents/ZhongAn/DEMO_GUIDE.md`
  - Demo 录制脚本、讲解提纲、演示顺序
- `/Users/yifantao/Documents/ZhongAn/spring-boot-api-docs.md`
  - 接口文档
- `/Users/yifantao/Documents/ZhongAn/schema-format.json`
  - schema 参考格式

## 快速启动

先启动 parser：

```bash
cd /Users/yifantao/Documents/ZhongAn/word-parser-service
cp .env.example .env
# 填写 OPENAI_API_KEY
python3 -m uvicorn main:app --host 127.0.0.1 --port 8001
```

再启动后端，交付目标优先用 PostgreSQL：

```bash
cd /Users/yifantao/Documents/ZhongAn/spring-boot-app
./scripts/run_with_postgres.sh
```

最后启动前端：

```bash
cd /Users/yifantao/Documents/ZhongAn/vue-app
npm install
npm run dev
```

默认地址：

- 前端：`http://127.0.0.1:5173/`
- 后端：`http://127.0.0.1:8080`
- parser：`http://127.0.0.1:8001/config-status`

## 当前建议验证

后端 / parser：

```bash
cd /Users/yifantao/Documents/ZhongAn/word-parser-service
python3 run_tests.py
```

```bash
cd /Users/yifantao/Documents/ZhongAn/spring-boot-app
mvn test -q
```

前端：

```bash
cd /Users/yifantao/Documents/ZhongAn/vue-app
npm run build
```

浏览器冒烟：

```bash
cd /Users/yifantao/Documents/ZhongAn/vue-app
node ./scripts/smoke_upload_publish.mjs \
  http://127.0.0.1:5173/ \
  '/Users/yifantao/Documents/ZhongAn/03报告/2 压力容器/20.05压力容器特种设备定期检验意见通知书（1）.docx' \
  http://127.0.0.1:8080
```

```bash
cd /Users/yifantao/Documents/ZhongAn/vue-app
node ./scripts/smoke_review_manual_add.mjs \
  http://127.0.0.1:5173/ \
  '/Users/yifantao/Documents/ZhongAn/03报告/4 电梯/03重庆电梯检测报告/30.03-CQ杂物电梯自行检测报告.docx'
```

## 已清理的旧内容

以下历史产物已从主路径移除：

- 旧的 `vue-components/` 散文件组件
- 旧的 `latest-delivery/` 样品交付目录
- 根目录临时预览 HTML
- 前端 `dist/`、后端 `target/`、旧 H2 数据文件
- parser 的旧缓存和旧样品输出

当前保留的是：

- 运行源码
- 真实样本
- 必要文档
- 当前 live 审计报告
