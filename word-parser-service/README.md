# Word Parser Service

本目录是 Word 解析与模板抽取微服务，负责：

- 接收 `.docx/.doc`
- 解析表格与段落结构
- 调用 OpenAI 生成 `subForms`
- 后处理成统一 `schema`
- 生成 `DDL` 与 `prototypeHtml`

## 本地启动

先安装依赖：

```bash
cd /Users/yifantao/Documents/ZhongAn/word-parser-service
pip3 install -r requirements.txt
```

复制环境变量模板：

```bash
cd /Users/yifantao/Documents/ZhongAn/word-parser-service
cp .env.example .env
```

把 `.env` 里的 `OPENAI_API_KEY` 改成你的真实 Key，然后启动：

```bash
cd /Users/yifantao/Documents/ZhongAn/word-parser-service
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

## 当前解析策略

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

## 当前策略

- 默认是 `OpenAI-only`
- 没有 `OPENAI_API_KEY` 时，不再静默走本地兜底，而是明确返回错误
- 只有显式设置 `ALLOW_HEURISTIC_FALLBACK=true` 时，才允许启发式兜底

## 验证

```bash
cd /Users/yifantao/Documents/ZhongAn/word-parser-service
python3 run_tests.py
```

## 批量审计

直接对 live parser 做整目录审计：

```bash
cd /Users/yifantao/Documents/ZhongAn/word-parser-service
python3 service_batch_audit.py '/Users/yifantao/Documents/ZhongAn/03报告' \
  --parser-url http://127.0.0.1:8001 \
  --output-dir output/service-audit \
  --include-prototype
```

输出：

- `output/service-audit/service-audit.json`
- `output/service-audit/service-audit.md`

说明：

- `output/` 和 `data/parse-cache/` 都属于运行期生成目录，不是交付源码的一部分。
- 如需避免命中旧缓存，可清空 `data/parse-cache/` 后重跑。
