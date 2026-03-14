# Delivery Status

## 当前结论

项目已经具备可交付主链路：

- Word 上传
- OpenAI 解析
- 模板审核纠错
- 发布建表
- 正式表单录入与提交

## 已完成验证

- Python parser：
  - `python3 run_tests.py`
  - 当前 `41` 个测试通过
- Spring Boot：
  - `mvn test -q` 通过
- Vue：
  - `npm run build` 通过
- 真实浏览器冒烟：
  - `.docx` 上传 -> 审核 -> 发布 -> 正式表单
  - `.doc` 上传 -> 审核
  - 审核页“手工补控件” -> 保存纠错 -> 刷新后仍存在
- `.doc` 字段码清理：
  - `DOCVARIABLE`
  - `MERGEFORMAT`
  - `PAGE`
  - 已通过真实重新上传验证，不再出现在审核页、schema、content 接口中

## 当前主路径

- 解析服务只在 `OPENAI_API_KEY` 已配置时工作
- 默认不开启 heuristic fallback
- 审核页支持：
  - 左右联动定位
  - 控件类型纠错
  - 漏识别区域手工补控件

## 当前边界

- AI 识别不是 100% 完美，生产上仍应走审核发布流程
- 老 `.doc` 的结构恢复已明显改善，但复杂模板仍比 `.docx` 更容易碎块化
- PostgreSQL 是当前推荐交付库；H2 仅保留开发兜底路径

## 当前重要入口

- 前端：
  - `http://127.0.0.1:5173/`
- 后端：
  - `http://127.0.0.1:8080`
- parser：
  - `http://127.0.0.1:8001/config-status`

## 下一步如果继续收口

- 继续优化老 `.doc` 大模板的块合并
- 继续提升漏识别控件的自动命中率
- 把审核页的“手工补控件”再扩成支持删除/移动/改标签
