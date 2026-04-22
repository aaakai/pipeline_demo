"""Pipeline for mixing ambience onto an existing dialogue audio file."""

from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path

from src.audio.io import export_wav, load_audio
from src.dialogue.audio_features import detect_energy_peaks, detect_pauses
from src.dialogue.asr_openai import transcribe_audio
from src.dialogue.script_planner import plan_dialogue_script
from src.logger import setup_logger
from src.mix_profiles import get_variant_profile
from src.planner.background_scheduler import BackgroundScheduler
from src.planner.merger import EventMerger
from src.scene_templates import SceneTemplateStore
from src.schemas import AppConfig, TimelineEvent, to_dict
from src.sfx.library import SfxLibrary
from src.sfx.matcher import SfxMatcher
from src.sfx.taxonomy import TAXONOMY
from src.audio.mix_engine import MixEngine
from src.utils.files import ensure_dir, write_json, write_text


class DialogueMixPipeline:
    def __init__(self, config: AppConfig, project_root: Path):
        self.config = config
        self.project_root = project_root
        self.rng = random.Random(config.random_seed)
        self.logger = setup_logger(project_root / config.output_dir / "dialogue_pipeline.log")
        self.template_store = SceneTemplateStore(config.scene_templates_path, project_root)
        self.library = SfxLibrary(config.sfx_manifest_path, project_root)
        self.matcher = SfxMatcher(self.library, self.rng, config.asset_selection)
        self.merger = EventMerger(config.merge)
        self.background_scheduler = BackgroundScheduler(config.background_scheduler, self.rng)
        self.mixer = MixEngine(
            config.sample_rate,
            config.channels,
            config.mix.fade_ms,
            config.loudness.max_mix_peak_dbfs,
        )

    def run(self, audio_path: str | Path | None = None) -> list[dict]:
        source_audio = self._resolve_audio(audio_path)
        self.logger.info("Dialogue source audio: %s", source_audio)

        analysis_audio = load_audio(source_audio, self.config.sample_rate, self.config.channels)
        duration_ms = len(analysis_audio)
        pauses = detect_pauses(source_audio)
        energy_peaks = detect_energy_peaks(source_audio)
        self.logger.info("Detected pauses: %s", pauses)
        self.logger.info("Detected energy peaks: %s", energy_peaks)

        transcript = transcribe_audio(source_audio, self.config.dialogue_audio.asr)
        if not transcript.get("duration_ms"):
            transcript["duration_ms"] = duration_ms
        self.logger.info("ASR transcript: %s", transcript.get("text", ""))

        plan = plan_dialogue_script(
            transcript=transcript,
            pauses=pauses,
            energy_peaks=energy_peaks,
            audio_duration_ms=duration_ms,
            config=self.config.dialogue_audio.planner,
        )
        self.logger.info("Dialogue LLM plan: %s", plan)

        scene = self._safe_scene(plan.get("scene"))
        emotion = str(plan.get("emotion") or "tense")
        scene_template = self.template_store.get(scene)
        base_timeline = self._timeline_from_plan(plan, duration_ms)
        base_case_id = self._case_id(source_audio)
        manifests: list[dict] = []

        for variant in self._variant_names():
            case_id = f"{base_case_id}_{variant}" if variant else base_case_id
            case_dir = ensure_dir(self.project_root / self.config.output_dir / case_id)
            clean_path = case_dir / "clean_dialogue.wav"
            final_path = case_dir / "final_mix.wav"
            script_path = case_dir / "script.txt"
            metadata_path = case_dir / "metadata.json"

            export_wav(analysis_audio, clean_path)
            variant_profile = get_variant_profile(variant)
            timeline = self._clone_timeline(base_timeline)
            timeline = self._apply_variant_profile(timeline, variant_profile)
            scheduled_timeline = self.background_scheduler.schedule(
                timeline=timeline,
                scene_template=scene_template,
                speech_duration_ms=duration_ms,
                background_gain_db=self.config.mix.background_gain_db,
                default_ducking_db=self.config.mix.default_ducking_db,
                variant=variant,
            )
            merged_timeline = self.merger.merge(scheduled_timeline)
            selected_timeline = self._select_assets(merged_timeline, self._scene_tags(scene, emotion))
            self._apply_loudness_compensation(selected_timeline)

            script_text = self._script_text(
                source_audio=source_audio,
                scene=scene,
                emotion=emotion,
                transcript=transcript,
                plan=plan,
                timeline=selected_timeline,
            )
            write_text(script_path, script_text)
            self.mixer.mix(
                clean_speech_path=clean_path,
                timeline=selected_timeline,
                output_path=final_path,
                speech_gain_db=self.config.mix.speech_gain_db,
            )

            selected_assets = [
                {"event_type": item.event_type, "asset_id": item.asset_id, "asset_path": item.asset_path}
                for item in selected_timeline
                if item.asset_id
            ]
            skipped_events = [
                {"event_type": item.event_type, "anchor_text": item.anchor_text, "reason": item.skipped_reason}
                for item in selected_timeline
                if item.skipped_reason
            ]
            metadata = {
                "case_id": case_id,
                "run_mode": "dialogue_audio_mix",
                "input_audio": str(source_audio),
                "audio_driven": True,
                "anchor_method": self.config.dialogue_audio.anchor_method,
                "dialogue_duration_ms": duration_ms,
                "variant": variant or "default",
                "variant_params": variant_profile,
                "scene": scene,
                "emotion": emotion,
                "asr_transcript": transcript.get("text", ""),
                "asr_segments": transcript.get("segments", []),
                "detected_pauses": pauses,
                "energy_peaks": energy_peaks,
                "llm_event_plan": plan,
                "background_schedule": [
                    to_dict(item)
                    for item in scheduled_timeline
                    if "background_scheduler" in item.source_event_ids
                ],
                "merged_events": [to_dict(item) for item in merged_timeline],
                "selected_assets": selected_assets,
                "asset_selection_trace": [
                    {
                        "event_id": item.event_id,
                        "event_type": item.event_type,
                        "asset_id": item.asset_id,
                        "selection_score": item.selection_score,
                        "selection_reason": item.selection_reason,
                    }
                    for item in selected_timeline
                    if item.asset_id
                ],
                "skipped_events": skipped_events,
                "event_timeline": [to_dict(item) for item in selected_timeline],
                "mix_params": to_dict(self.config.mix),
                "output_files": {
                    "clean_dialogue": str(clean_path),
                    "final_mix": str(final_path),
                    "script": str(script_path),
                    "metadata": str(metadata_path),
                },
            }
            write_json(metadata_path, metadata)
            manifests.append(
                {
                    "case_id": case_id,
                    "final_mix": str(final_path),
                    "metadata": str(metadata_path),
                    "scene": scene,
                    "emotion": emotion,
                }
            )
            self.logger.info("Exported dialogue case: %s", metadata["output_files"])

        listening_path = self.project_root / self.config.output_dir / "dialogue_listening_manifest.json"
        write_json(listening_path, manifests)
        return manifests

    def _resolve_audio(self, override_path: str | Path | None) -> Path:
        if override_path:
            path = Path(override_path)
            return path if path.is_absolute() else (self.project_root / path).resolve()
        configured = self.config.dialogue_audio.audio_path
        if configured:
            path = Path(configured)
            return path if path.is_absolute() else (self.project_root / path).resolve()
        input_dir = (self.project_root / self.config.dialogue_audio.input_dir).resolve()
        extensions = {item.lower() for item in self.config.dialogue_audio.allowed_audio_extensions}
        candidates = [
            path for path in input_dir.glob("*") if path.is_file() and path.suffix.lower() in extensions
        ]
        if not candidates:
            raise FileNotFoundError(f"No dialogue audio found in: {input_dir}")
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _timeline_from_plan(self, plan: dict, duration_ms: int) -> list[TimelineEvent]:
        timeline: list[TimelineEvent] = []
        for index, event in enumerate(plan.get("events") or [], start=1):
            event_type = event.get("event_type")
            if event_type not in TAXONOMY:
                continue
            taxonomy = TAXONOMY[event_type]
            start_ms = int(max(0, min(duration_ms - 1, int(event.get("start_ms", 0) or 0))))
            end_ms = int(event.get("end_ms") or (start_ms + taxonomy.default_duration_ms))
            if end_ms - start_ms < taxonomy.default_duration_ms:
                end_ms = start_ms + taxonomy.default_duration_ms
            end_ms = max(start_ms + 200, min(duration_ms, end_ms))
            strength = max(0.05, min(0.95, float(event.get("strength", 0.45) or 0.45)))
            gain_low, gain_high = taxonomy.gain_db_range
            gain_db = gain_low + (gain_high - gain_low) * strength
            if not taxonomy.foreground:
                gain_db = min(gain_db, self.config.mix.background_gain_db)
            timeline.append(
                TimelineEvent(
                    event_id=str(event.get("event_id") or f"llm_evt_{index:03d}"),
                    event_type=event_type,
                    anchor_text=str(event.get("reason") or event_type),
                    position="around_anchor",
                    foreground=taxonomy.foreground,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    gain_db=round(gain_db, 2),
                    ducking_db=self.config.mix.default_ducking_db if taxonomy.foreground else 0.0,
                    asset_id=None,
                    asset_path=None,
                    source_event_ids=[str(event.get("event_id") or f"llm_evt_{index:03d}")],
                )
            )
        return sorted(timeline, key=lambda item: (item.start_ms, item.end_ms))

    def _select_assets(self, timeline: list[TimelineEvent], scene_tags: set[str]) -> list[TimelineEvent]:
        for event in timeline:
            result = self.matcher.match(event, scene_tags=scene_tags)
            if result:
                asset, score, reason = result
                event.asset_id = asset.asset_id
                event.asset_path = str(self.library.resolve_path(asset))
                event.skipped_reason = None
                event.selection_score = score
                event.selection_reason = reason
            else:
                event.skipped_reason = "no_matching_asset"
        return timeline

    def _apply_variant_profile(
        self,
        timeline: list[TimelineEvent],
        profile: dict[str, float],
    ) -> list[TimelineEvent]:
        for event in timeline:
            if event.foreground:
                event.gain_db = round(event.gain_db + profile["foreground_gain_offset_db"], 2)
                event.ducking_db = round(event.ducking_db + profile["ducking_offset_db"], 2)
            else:
                event.gain_db = round(event.gain_db + profile["background_gain_offset_db"], 2)
            event.gain_trace["variant_gain_offset_db"] = (
                profile["foreground_gain_offset_db"]
                if event.foreground
                else profile["background_gain_offset_db"]
            )
            event.gain_trace["variant_ducking_offset_db"] = (
                profile["ducking_offset_db"] if event.foreground else 0.0
            )
        return timeline

    def _apply_loudness_compensation(self, timeline: list[TimelineEvent]) -> None:
        if not self.config.loudness.enabled:
            return
        assets_by_id = {asset.asset_id: asset for asset in self.library.assets}
        for event in timeline:
            if not event.asset_id:
                continue
            asset = assets_by_id.get(event.asset_id)
            if not asset or not asset.analysis:
                continue
            rms_dbfs = float(asset.analysis.get("rms_dbfs", -30.0))
            target_rms = (
                -22.0
                if event.foreground
                else -18.0 - self.config.loudness.background_headroom_db
            )
            compensation = target_rms - (rms_dbfs + event.gain_db)
            max_comp = self.config.loudness.max_loudness_compensation_db
            compensation = max(-max_comp, min(max_comp, compensation))
            event.gain_db = round(event.gain_db + compensation, 2)
            event.gain_trace.update(
                {
                    "asset_rms_dbfs": round(rms_dbfs, 2),
                    "target_rms_dbfs": round(target_rms, 2),
                    "loudness_compensation_db": round(compensation, 2),
                    "final_gain_db": event.gain_db,
                }
            )

    def _scene_tags(self, scene: str, emotion: str) -> set[str]:
        tags = {scene, emotion}
        if "street" in scene:
            tags.update({"street", "outdoor", "traffic", "wet"})
        if "rain" in scene:
            tags.update({"rain", "weather", "wet"})
        if "cafe" in scene:
            tags.update({"crowd", "indoor"})
        if "indoor" in scene or "office" in scene:
            tags.update({"indoor"})
        return tags

    def _script_text(
        self,
        source_audio: Path,
        scene: str,
        emotion: str,
        transcript: dict,
        plan: dict,
        timeline: list[TimelineEvent],
    ) -> str:
        lines = [
            f"Source Audio: {source_audio.name}",
            f"Scene: {scene}",
            f"Emotion: {emotion}",
            "",
            "Transcript:",
            str(transcript.get("text") or "").strip(),
            "",
            "Planner Summary:",
            str(plan.get("summary") or "").strip(),
            "",
            "Acoustic Plan:",
        ]
        for event in timeline:
            status = event.asset_id or event.skipped_reason or "unassigned"
            lines.append(
                f"- {event.start_ms / 1000:.2f}s-{event.end_ms / 1000:.2f}s "
                f"{event.event_type} gain={event.gain_db:.2f} asset={status}"
            )
        return "\n".join(lines)

    def _variant_names(self) -> list[str | None]:
        if not self.config.variants.enabled:
            return [None]
        return [name for name in self.config.variants.names if name]

    def _safe_scene(self, scene: object) -> str:
        try:
            self.template_store.get(str(scene))
            return str(scene)
        except Exception:
            return "rainy_street_chat"

    def _case_id(self, source_audio: Path) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_stem = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in source_audio.stem)
        return f"dialogue_{stamp}_{safe_stem[:40]}"

    def _clone_timeline(self, timeline: list[TimelineEvent]) -> list[TimelineEvent]:
        return [
            TimelineEvent(
                event_id=item.event_id,
                event_type=item.event_type,
                anchor_text=item.anchor_text,
                position=item.position,
                foreground=item.foreground,
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                gain_db=item.gain_db,
                ducking_db=item.ducking_db,
                asset_id=None,
                asset_path=None,
                skipped_reason=None,
                source_event_ids=list(item.source_event_ids),
                gain_trace=dict(item.gain_trace),
            )
            for item in timeline
        ]


def run_dialogue_from_config(
    config_path: str | Path,
    audio_path: str | Path | None = None,
) -> list[dict]:
    project_root = Path(config_path).expanduser().resolve().parents[1]
    from src.config import load_config

    config = load_config(config_path)
    return DialogueMixPipeline(config, project_root).run(audio_path=audio_path)
