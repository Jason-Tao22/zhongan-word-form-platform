# Word Parser Service

本目录是 Word 解析与模板抽取微服务，负责：

- 接收 `.docx/.doc`
- 解析表格与段落结构
- 调用 OpenAI 生成 `subForms`
- 后处理成统一 `schema`
- 生成 `DDL` 与 `prototypeHtml`

## 本地启动

安装依赖：

```bash
pip3 install -r requirements.txt
```

复制环境变量模板：

```bash
cp .env.example .env
```

填写 `.env` 里的 `OPENAI_API_KEY` 后启动：

```bash
python3 -m uvicorn main:app --host 127.0.0.1 --port 8001
```

## 关键环境变量

- `OPENAI_API_KEY`: 必填，未配置时默认拒绝上传
- `OPENAI_MODEL`: 默认 `gpt-5`
- `ALLOW_HEURISTIC_FALLBACK`: 默认 `false`，仅开发联调时可手动开启

## 接口

- `GET /health`
- `GET /config-status`
- `POST /parse-word?include_prototype=true`

## 解析策略

- `.docx`：优先走原生 Word XML 表格解析
- `.doc`：优先走 `textutil -> HTML -> 真实表格块`
- 如果旧 `.doc` 连 HTML 里也提不出表格，再降级到文本兜底 `pseudo table`
- 规则层负责稳定提取结构，OpenAI 负责子表语义与歧义块控件分类
- 启发式只作为显式开启时的开发兜底，不再默认参与生产链路

`GET /config-status` 会明确返回当前服务是不是在真正使用 OpenAI，例如：

```json
{
  "status": "ok",
  "provider": "openai",
  "model": "gpt-5",
  "openaiConfigured": true,
  "heuristicFallbackAllowed": false,
  "defaultMode": "openai"
}
```

## 验证

```bash
python3 run_tests.py
```

## 批量审计

对一个本地样本目录做整目录审计：

```bash
python3 service_batch_audit.py ../samples \
  --parser-url http://127.0.0.1:8001 \
  --output-dir output/service-audit \
  --include-prototype
```

输出：

- `output/service-audit/service-audit.json`
- `output/service-audit/service-audit.md`

说明：

- `output/` 和 `data/parse-cache/` 都属于运行期生成目录，不是交付源码的一部分
- 如需避免命中旧缓存，可清空 `data/parse-cache/` 后重跑
- 公开仓库只保留了可公开演示的 `samples/` 目录；客户私有模板不再随仓库分发
