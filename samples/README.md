# Public Samples

这个目录只保留可公开分发的演示样本。

当前包含：

- `public-demo-template.docx`
  - 用于上传、审核、发布、填写的公开演示模板
  - 设计目标是覆盖：
    - 普通输入框
    - 大块文本域
    - 行内日期
    - 行内单选 / 复选
    - 审核页手工补控件

不包含：

- 客户私有模板
- `03报告/` 原始样本

如需重新生成公开样本：

```bash
python3 generate_public_samples.py
```
