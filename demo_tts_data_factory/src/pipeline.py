"""End-to-end demo TTS data generation pipeline."""

from __future__ import annotations

import json
import random
from pathlib import Path

from src.config import load_config
from src.enhancer.llm_stub import LLMEnhancerStub
from src.enhancer.rule_based import RuleBasedEnhancer
from src.logger import setup_logger
from src.planner.anchor_mapper import AnchorMapper
from src.planner.event_planner import EventPlanner
from src.planner.merger import EventMerger
from src.scene_templates import SceneTemplateStore
from src.schemas import AppConfig, CaseInput, TimelineEvent, to_dict
from src.sfx.library import SfxLibrary
from src.sfx.matcher import SfxMatcher
from src.style_controller import StyleController
from src.tts.mock_tts import MockTTSProvider
from src.tts.openai_tts import OpenAITTSProvider
from src.audio.io import load_audio
from src.audio.mix_engine import MixEngine
from src.utils.files import ensure_dir, write_json, write_text
from src.utils.text import make_case_id
from src.utils.time import anchor_to_ms


class DemoPipeline:
    def __init__(self, config: AppConfig, project_root: Path):
        self.config = config
        self.project_root = project_root
        self.rng = random.Random(config.random_seed)
        self.logger = setup_logger(project_root / config.output_dir / "pipeline.log")
        self.template_store = SceneTemplateStore(config.scene_templates_path, project_root)
        self.library = SfxLibrary(config.sfx_manifest_path, project_root)
        self.matcher = SfxMatcher(self.library, self.rng)
        self.enhancer = self._build_enhancer()
        self.planner = EventPlanner()
        self.anchor_mapper = AnchorMapper()
        self.merger = EventMerger(config.merge)
        self.style_controller = StyleController()
        self.tts = self._build_tts_provider()
        self.mixer = MixEngine(config.sample_rate, config.channels, config.mix.fade_ms)

    def run(self, plan_only: bool = False) -> list[dict]:
        cases = self._load_cases()
        manifests = [self.run_case(case, plan_only=plan_only) for case in cases]
        listening_path = self.project_root / self.config.output_dir / "listening_manifest.json"
        write_json(listening_path, manifests)
        self.logger.info("Wrote listening manifest: %s", listening_path)
        return manifests

    def run_case(self, case: CaseInput, plan_only: bool = False) -> dict:
        case_dir = ensure_dir(self.project_root / self.config.output_dir / case.case_id)
        self.logger.info("Running case %s", case.case_id)
        scene_template = self.template_store.get(case.scene)
        self.logger.info("Loaded scene template: %s", to_dict(scene_template))

        enhancement = self.enhancer.enhance(
            plain_text=case.text,
            scene=case.scene,
            emotion=case.emotion,
            allowed_events=self.config.allowed_events,
        )
        self.logger.info("Enhancement result: %s", to_dict(enhancement))

        planned_events = self.planner.plan(
            enhancement=enhancement,
            scene_template=scene_template,
            allowed_events=self.config.allowed_events,
        )
        self.logger.info("Generated original events: %s", [to_dict(item) for item in planned_events])

        style_views = self.style_controller.build(
            plain_text=case.text,
            scene=case.scene,
            emotion=case.emotion,
            events=planned_events,
            config=self.config.style,
        )

        script_path = case_dir / "script.txt"
        clean_path = case_dir / "clean_speech.wav"
        final_path = case_dir / "final_mix.wav"
        metadata_path = case_dir / "metadata.json"

        write_text(script_path, style_views.script_text)
        if plan_only:
            speech_duration_ms = self._estimate_speech_duration_ms(case.text)
        else:
            self.tts.synthesize(case.text, clean_path)
            clean_audio = load_audio(clean_path, self.config.sample_rate, self.config.channels)
            speech_duration_ms = len(clean_audio)
        original_timeline = self.anchor_mapper.map_events(
            plain_text=case.text,
            planned_events=planned_events,
            speech_duration_ms=speech_duration_ms,
            default_ducking_db=self.config.mix.default_ducking_db,
            background_gain_db=self.config.mix.background_gain_db,
        )
        merged_timeline = self.merger.merge(original_timeline)
        self.logger.info("Merged events: %s", [to_dict(item) for item in merged_timeline])
        timeline = self._select_assets(merged_timeline)
        self.logger.info("Selected assets: %s", [to_dict(item) for item in timeline])
        self.logger.info("Final event timeline: %s", [to_dict(item) for item in timeline])

        if not plan_only:
            self.mixer.mix(
                clean_speech_path=clean_path,
                timeline=timeline,
                output_path=final_path,
                speech_gain_db=self.config.mix.speech_gain_db,
            )

        selected_assets = [
            {"event_type": item.event_type, "asset_id": item.asset_id, "asset_path": item.asset_path}
            for item in timeline
            if item.asset_id
        ]
        skipped_events = [
            {"event_type": item.event_type, "anchor_text": item.anchor_text, "reason": item.skipped_reason}
            for item in timeline
            if item.skipped_reason
        ]
        metadata = {
            "case_id": case.case_id,
            "plain_text": case.text,
            "keyword_style": style_views.keyword_style,
            "brief_style": style_views.brief_style,
            "script_text": style_views.script_text,
            "scene": case.scene,
            "emotion": case.emotion,
            "scene_template": to_dict(scene_template),
            "enhancement_notes": enhancement.notes,
            "original_events": [to_dict(item) for item in planned_events],
            "merged_events": [to_dict(item) for item in merged_timeline],
            "selected_assets": selected_assets,
            "skipped_events": skipped_events,
            "event_timeline": [to_dict(item) for item in timeline],
            "mix_params": to_dict(self.config.mix),
            "run_mode": "plan_only" if plan_only else "full_audio",
            "estimated_speech_duration_ms": speech_duration_ms if plan_only else None,
            "output_files": {
                "clean_speech": None if plan_only else str(clean_path),
                "final_mix": None if plan_only else str(final_path),
                "script": str(script_path),
                "metadata": str(metadata_path),
            },
        }
        write_json(metadata_path, metadata)
        self.logger.info("Exported files: %s", metadata["output_files"])
        return {
            "case_id": case.case_id,
            "text": case.text,
            "final_mix": None if plan_only else str(final_path),
            "metadata": str(metadata_path),
        }

    def _select_assets(self, timeline: list[TimelineEvent]) -> list[TimelineEvent]:
        for event in timeline:
            asset = self.matcher.match(event)
            if asset:
                event.asset_id = asset.asset_id
                event.asset_path = str(self.library.resolve_path(asset))
                event.skipped_reason = None
            else:
                event.skipped_reason = "no_matching_asset"
        return timeline

    def _load_cases(self) -> list[CaseInput]:
        if self.config.input_mode == "single":
            return [
                CaseInput(
                    case_id=make_case_id(self.config.text),
                    text=self.config.text,
                    scene=self.config.scene,
                    emotion=self.config.emotion,
                )
            ]

        input_path = self.project_root / self.config.batch_input_path
        if not input_path.exists():
            raise FileNotFoundError(f"Batch input file not found: {input_path}")
        cases: list[CaseInput] = []
        for line_no, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            cases.append(
                CaseInput(
                    case_id=record.get("case_id") or make_case_id(record["text"]),
                    text=record["text"],
                    scene=record.get("scene", self.config.scene),
                    emotion=record.get("emotion", self.config.emotion),
                )
            )
        return cases

    def _build_tts_provider(self):
        if self.config.tts_provider == "mock":
            return MockTTSProvider(
                project_root=self.project_root,
                clean_voice_path=self.config.clean_voice_path,
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
            )
        if self.config.tts_provider == "openai":
            return OpenAITTSProvider(
                config=self.config.openai_tts,
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
            )
        raise ValueError(f"Unsupported tts_provider: {self.config.tts_provider}")

    def _build_enhancer(self):
        if self.config.enhancer == "rule_based":
            return RuleBasedEnhancer()
        if self.config.enhancer in {"llm_stub", "llm"}:
            return LLMEnhancerStub()
        raise ValueError(f"Unsupported enhancer: {self.config.enhancer}")

    def _estimate_speech_duration_ms(self, text: str) -> int:
        non_space_chars = len("".join(text.split()))
        return max(8000, int(non_space_chars / 4.5 * 1000))


def run_from_config(config_path: str | Path, plan_only: bool = False) -> list[dict]:
    project_root = Path(config_path).expanduser().resolve().parents[1]
    config = load_config(config_path)
    return DemoPipeline(config, project_root).run(plan_only=plan_only)
