# Pipeline Demo

一个最小可用的“单 URL 文本提取 + LLM 剧本清洗”原型。它只处理用户手动提供的单个公开网页 URL，不做批量抓取、不做站内遍历，也不会绕过登录、付费墙、Cloudflare 或人机验证。

## 功能概览

- CLI 必选：提取正文，清洗文本，生成广播剧脚本与 manifest
- FastAPI 可选：提供 `/extract` 和 `/script`
- AO3 单作品页 / 单章节页保守适配
- `heuristic` 与 `llm` 两种剧本生成模式
- 输出文件包括 `raw_text.txt`、`cleaned_text.txt`、`script.txt`、`script_manifest.json`、`meta.json`、`pipeline.log`

## 安装

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 环境变量

LLM 模式需要：

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://your-openai-compatible-endpoint/v1"
export OPENAI_MODEL="gpt-4o-mini"
```

如果只跑 `heuristic`，可以不设置这些环境变量。

## CLI 用法

只提取正文与清洗：

```bash
python -m app.cli extract --url "https://example.com/article" --outdir ./output
```

抓取并生成启发式剧本：

```bash
python -m app.cli script --url "https://example.com/article" --outdir ./output --mode heuristic
```

抓取并调用 LLM 生成剧本：

```bash
python -m app.cli script --url "https://example.com/article" --outdir ./output --mode llm
```

## FastAPI 启动

```bash
uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

接口示例：

```bash
curl -X POST http://127.0.0.1:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/article","outdir":"./output"}'
```

```bash
curl -X POST http://127.0.0.1:8000/script \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/article","outdir":"./output"}'
```

说明：当前 `/script` 默认使用 `heuristic` 模式，CLI 才支持显式切换模式。
如果需要，也可以在 JSON 中传 `mode`，例如 `{"url":"...","outdir":"./output","mode":"llm"}`。

## 输出文件

- `raw.html`：原始 HTML
- `raw_text.txt`：提取出的原始正文
- `cleaned_text.txt`：清洗后的正文
- `script.txt`：便于查看的纯文本脚本
- `script_manifest.json`：未来 TTS 可直接消费的结构化脚本
- `meta.json`：标题、来源、站点类型、模式、时间等元信息
- `pipeline.log`：运行日志

## 常见报错与排查

- `目标页面返回 403`：页面可能不公开，或站点不允许当前请求方式。请先在浏览器确认它无需登录即可访问。
- `目标页面返回 429`：请求过快或站点限流。稍后重试，不要并发请求。
- `请求超时`：站点响应过慢。请稍后重试，或检查网络。
- `未能提取到有效正文`：页面结构可能变化，或给的并不是正文页。
- `llm 模式需要设置 OPENAI_API_KEY 和 OPENAI_BASE_URL`：请先设置环境变量。
- `LLM 返回的 JSON 非法`：程序会自动尝试一次修复重试；若仍失败，请更换模型或降低输入复杂度。

## 测试

```bash
pytest
```

## 项目结构

```text
app/
  cleaners/
  extractors/
  llm/
  api.py
  cli.py
  exceptions.py
  schemas.py
  service.py
  utils.py
tests/
  fixtures/
  test_extractors.py
  test_script_adapter.py
requirements.txt
README.md
```
