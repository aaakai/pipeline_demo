"""Dataclasses shared across the demo pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EventPosition = Literal[
    "before_anchor",
    "after_anchor",
    "around_anchor",
    "sentence_start",
    "sentence_end",
]
LayerType = Literal["foreground", "background"]


@dataclass(frozen=True)
class EventTaxonomyItem:
    event_type: str
    category: str
    foreground: bool
    can_overlap_speech: bool
    default_duration_ms: int
    gain_db_range: tuple[float, float]
    mergeable: bool
    tags: list[str]

    @property
    def layer(self) -> LayerType:
        return "foreground" if self.foreground else "background"


@dataclass
class CandidateEvent:
    event_type: str
    anchor_text: str
    position: EventPosition
    strength: float
    reason: str = ""
    optional_duration_ms: int | None = None


@dataclass
class EnhancementResult:
    plain_text: str
    scene: str
    emotion: str
    candidate_events: list[CandidateEvent] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class PlannedEvent:
    event_id: str
    event_type: str
    anchor_text: str
    position: EventPosition
    strength: float
    foreground: bool
    optional_duration_ms: int | None = None
    source: str = "planner"


@dataclass
class ScriptEvent:
    type: str
    anchor_text: str
    position: EventPosition
    strength: float


@dataclass
class EnhancedScript:
    plain_text: str
    script_text: str
    scene: str
    emotion: str
    events: list[ScriptEvent] = field(default_factory=list)


@dataclass
class SfxAsset:
    asset_id: str
    path: str
    event_type: str
    duration_ms: int
    tags: list[str]
    intensity: float
    sample_rate: int
    channels: int | None = None
    analysis: dict[str, float] | None = None


@dataclass
class TimelineEvent:
    event_id: str
    event_type: str
    anchor_text: str
    position: EventPosition
    foreground: bool
    start_ms: int
    end_ms: int
    gain_db: float
    ducking_db: float
    asset_id: str | None
    asset_path: str | None
    skipped_reason: str | None = None
    source_event_ids: list[str] = field(default_factory=list)
    selection_score: float | None = None
    selection_reason: str | None = None
    gain_trace: dict[str, float] = field(default_factory=dict)


@dataclass
class CaseInput:
    case_id: str
    text: str
    scene: str
    emotion: str


@dataclass
class MixConfig:
    speech_gain_db: float = 0.0
    default_ducking_db: float = -4.0
    fade_ms: int = 15
    background_gain_db: float = -18.0


@dataclass
class MergeConfig:
    enabled: bool = True
    same_event_gap_ms: int = 350
    cloth_rustle_merge_gap_ms: int = 700


@dataclass
class StyleConfig:
    enable_keyword_style: bool = True
    enable_brief_style: bool = True


@dataclass
class AssetScanConfig:
    audio_extensions: list[str] = field(default_factory=lambda: [".wav", ".mp3", ".flac"])
    auto_intensity: bool = True
    preserve_manual_overrides: bool = True


@dataclass
class AssetSelectionConfig:
    strategy: str = "weighted_top_k"
    top_k: int = 3
    avoid_recent: bool = True
    recent_window: int = 6
    scene_tag_weight: float = 0.08


@dataclass
class BackgroundSchedulerConfig:
    enabled: bool = True
    max_background_layers: int = 4
    max_accent_events: int = 5
    min_gap_ms: int = 3000
    random_offset_ms: int = 1200


@dataclass
class LoudnessConfig:
    enabled: bool = True
    target_speech_peak_dbfs: float = -3.0
    max_mix_peak_dbfs: float = -1.0
    background_headroom_db: float = 14.0
    max_loudness_compensation_db: float = 6.0


@dataclass
class VariantsConfig:
    enabled: bool = False
    names: list[str] = field(default_factory=lambda: ["balanced"])


@dataclass
class SceneTemplate:
    name: str
    allowed_foreground_events: list[str]
    allowed_background_events: list[str]
    default_background_events: list[str]
    max_foreground_events: int
    max_total_events: int
    overlap_policy: dict[str, bool]
    emotion_bias: dict[str, dict[str, float]]
    event_density_level: str
    max_strong_events: int = 2


@dataclass
class StyleViews:
    keyword_style: str
    brief_style: str
    script_text: str


@dataclass
class OpenAITTSConfig:
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini-tts"
    voice: str = "coral"
    instructions: str | None = None
    response_format: str = "wav"
    speed: float = 1.0


@dataclass
class LLMEnhancerConfig:
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    timeout_seconds: int = 60


@dataclass
class OpenAIASRConfig:
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    model: str = "whisper-1"
    language: str | None = "zh"
    timeout_seconds: int = 180


@dataclass
class DialoguePlannerConfig:
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    timeout_seconds: int = 90


@dataclass
class DialogueAudioConfig:
    input_dir: str = "input"
    audio_path: str | None = None
    allowed_audio_extensions: list[str] = field(
        default_factory=lambda: [".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"]
    )
    scene_mode: str = "auto"
    emotion_mode: str = "auto"
    anchor_method: str = "asr_segments_plus_pause"
    asr: OpenAIASRConfig = field(default_factory=OpenAIASRConfig)
    planner: DialoguePlannerConfig = field(default_factory=DialoguePlannerConfig)


@dataclass
class AppConfig:
    input_mode: Literal["single", "batch"]
    text: str
    scene: str
    emotion: str
    allowed_events: list[str]
    clean_voice_path: str | None
    sfx_manifest_path: str
    sample_rate: int
    channels: int
    output_dir: str
    batch_input_path: str
    scene_templates_path: str
    enhancer: str
    llm_enhancer: LLMEnhancerConfig
    tts_provider: str
    openai_tts: OpenAITTSConfig
    dialogue_audio: DialogueAudioConfig
    mix: MixConfig
    merge: MergeConfig
    style: StyleConfig
    asset_scan: AssetScanConfig
    asset_selection: AssetSelectionConfig
    background_scheduler: BackgroundSchedulerConfig
    loudness: LoudnessConfig
    variants: VariantsConfig
    random_seed: int | None = None


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value
