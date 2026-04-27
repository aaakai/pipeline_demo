# Demo TTS Data Factory

一个本地文件为中心的“带环境音/动作音的 TTS 造数 demo pipeline”。它不是训练框架，也不是论文复现，而是用 `纯文本 + 场景模板 + 事件规划 + 素材检索 + 动态混音` 快速生成可试听、可检查、可复用的 demo 数据。

## 为什么拆成这些模块

- `Scene Template`: 先限定场景能用哪些事件、事件密度、背景氛围和情绪偏好，避免 enhancer 自由发挥。
- `Event Planner`: 把候选事件转成受模板约束的结构化 plan，而不是只生成括号文本。
- `Dynamic Acoustic Mixer`: 根据时间轴放置 foreground/background 音效，做 gain、fade、ducking、normalize。
- `Style Controller`: 为同一条样本生成 `keyword_style`、`brief_style` 和可读 `script.txt`，方便人工检查和未来监督信号复用。
- `Event Merging`: 合并过近的同类轻事件，避免混音过碎、过密。

## 安装依赖

建议 Python 3.11+：

```bash
cd demo_tts_data_factory
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果你复用项目根目录已有虚拟环境，也可以：

```bash
../.venv/bin/python -m src.main run --config configs/demo.yaml
```

## ffmpeg 依赖

`pydub` 读取某些格式时需要系统安装 `ffmpeg`。当前 mock 素材都是 wav，通常可以直接跑；后续接入 mp3/flac 素材时建议安装：

```bash
brew install ffmpeg
```

## 素材库

素材清单在：

```text
assets/sfx/manifest.json
```

最小记录示例：

```json
{
  "asset_id": "cup_hit_mock_001",
  "path": "cup_hit/cup_hit_mock_001.wav",
  "event_type": "cup_hit",
  "duration_ms": 350,
  "tags": ["indoor", "impact", "foreground"],
  "intensity": 0.7,
  "sample_rate": 24000
}
```

`path` 相对 `assets/sfx/manifest.json` 所在目录。没有匹配素材时不会中断，会记录到 `skipped_events`。

### 自动扫描素材

把素材放到 `assets/sfx/<event_type>/` 后，可以自动重建 manifest：

```bash
python -m src.main scan-assets --config configs/demo.yaml
```

扫描器会读取音频时长、采样率、声道数、RMS、峰值和静音比例，并估算 `intensity`。估算值只是初始值，适合快速造数；如果某条素材听感强弱和估算不一致，可以后续用 `assets/sfx/manifest_overrides.yaml` 做人工覆盖。

## 场景模板

场景模板在：

```text
configs/scene_templates.yaml
```

当前内置：

- `indoor_argument`
- `office_talk`
- `indoor_room_chat`
- `restaurant_chat`
- `rainy_street_chat`
- `sunny_street_chat`
- `cafe_chat`
- `library_study_chat`
- `factory_workshop_chat`
- `after_exercise_chat`

每个模板定义 foreground/background 事件、默认背景、事件数量上限、强事件上限、overlap policy、emotion bias 和 density level。

## 运行单条 demo

默认使用 rule-based enhancer 和 mock TTS：

```bash
python -m src.main run --config configs/demo.yaml
```

如果配置里开启了：

```yaml
variants:
  enabled: true
  names: [subtle, balanced, cinematic]
```

同一条文本会生成三个版本：

```text
output/{case_id}_subtle/
output/{case_id}_balanced/
output/{case_id}_cinematic/
```

`subtle` 更干净，`balanced` 是默认推荐，`cinematic` 会使用更密的背景调度和更明显的动作音。

输出：

```text
output/{case_id}/
  clean_speech.wav
  final_mix.wav
  script.txt
  metadata.json
```

## 运行批量 demo

批量输入在：

```text
examples/demo_inputs.jsonl
```

运行：

```bash
python -m src.main run --config configs/batch_demo.yaml
```

每行至少支持：

```json
{"case_id":"case_argument_001","text":"你为什么这么做，你到底想怎么样","scene":"indoor_argument","emotion":"angry"}
```

## 给已有对话音频加环境音

如果你已经有一段纯对话或人声分离后的音频，可以放到：

```text
input/
```

然后运行：

```bash
python -m src.main mix-dialogue --config configs/dialogue_audio.yaml
```

默认会批量处理 `input/` 下所有受支持的音频文件。
当前 `configs/dialogue_audio.yaml` 默认使用 `dialogue_audio.scene_mode: all_templates`。
因此每条输入音频都会对 `configs/scene_templates.yaml` 中的每个场景模板各产出一组结果。
如果有 3 条音频、10 个场景模板、3 个 variants，就会生成 `3 x 10 x 3 = 90` 个输出目录。

也可以显式指定音频：

```bash
python -m src.main mix-dialogue --config configs/dialogue_audio.yaml --audio input/your_dialogue.mp3
```

这条链路不会重新生成 TTS，而是：

- 用 OpenAI ASR 把音频识别成文本和片段
- 用 LLM 根据台词、停顿、能量峰推断 `scene`、`emotion` 和环境音事件计划
- 从 `assets/sfx/manifest.json` 检索匹配素材
- 把背景音、动作音和原始对话混成 `final_mix.wav`

需要设置：

```bash
export OPENAI_API_KEY="你的 key"
```

输出会生成 `subtle`、`balanced`、`cinematic` 三个版本。缺失素材不会让任务失败，会写入每个 case 的 `metadata.json -> skipped_events`。

## 输出说明

`metadata.json` 会保存：

- `plain_text`
- `keyword_style`
- `brief_style`
- `script_text`
- `scene`
- `emotion`
- `scene_template`
- `original_events`
- `merged_events`
- `background_schedule`
- `selected_assets`
- `asset_selection_trace`
- `skipped_events`
- `event_timeline`
- `mix_params`
- `output_files`

`script.txt` 是给人看的：

```text
Scene: rainy_street_chat
Emotion: angry
Text: ...
Brief: ...
Keywords: ...
Events:
- evt_001: footsteps_fast @ 往前逼近 (around_anchor, strength=0.60)
```

## 替换成真实 LLM enhancer

当前默认只用 `rule_based`。`src/enhancer/llm_stub.py` 保留了接口，但不会调用外部 API。后续可以实现真实 enhancer，只要返回 `EnhancementResult`：

```python
class RealLLMEnhancer(ScriptEnhancer):
    def enhance(self, plain_text, scene, emotion, allowed_events):
        return EnhancementResult(...)
```

建议真实 LLM 只生成 `candidate_events`，再交给本地 `EventPlanner` 按 scene template 做约束，这样批量生成更稳定。

## 替换成真实 TTS

当前默认 `mock` TTS：

- 如果 `clean_voice_path` 有值，复制/转换该音频为 `clean_speech.wav`
- 否则读取 `assets/mock_voice/sample_clean_voice.wav`

后续接真实 TTS 时实现：

```python
class RealTTSProvider(TTSProvider):
    def synthesize(self, text, out_path):
        ...
```

只要最终写出 `clean_speech.wav`，后面的 anchor、素材检索和混音都不需要改。

## 接入 WhisperX / forced alignment

当前 anchor 定位是近似策略：

```text
anchor_text 在纯文本中的字符位置 / 文本长度 * clean speech 总时长
```

后续可以替换 `src/planner/anchor_mapper.py`，让它接收 WhisperX 或 forced alignment 的词级 timestamp。

## 当前局限性

- mock TTS 不会朗读文本，只是占位 clean speech。
- 字符比例 anchor 只能粗略定位，短音频时事件会比较密。
- 已有对话音频链路目前依赖 ASR 片段、停顿和能量峰做粗粒度规划，还没有做精确词级对齐。
- mock SFX 只是程序生成的占位素材，不代表真实音效质量。
- rule-based enhancer 只覆盖少量关键词和场景，真实批量生产建议接 LLM，但仍保留 scene template 和本地 planner 约束。
