"""Pipeline for mixing ambience onto an existing dialogue audio file."""

from __future__ import annotations

import hashlib
import random
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from src.utils.files import ensure_dir, write_json
from src.utils.tos import (
    clear_local_input_dir,
    fetch_input_object,
    list_input_objects,
    remote_uri_to_relative_path,
    sync_case_dir,
)


class DialogueMixPipeline:
    def __init__(self, config: AppConfig, project_root: Path):
        self.config = config
        self.project_root = project_root
        self.logger = setup_logger(project_root / config.output_dir / "dialogue_pipeline.log")
        self.template_store = SceneTemplateStore(config.scene_templates_path, project_root)
        self.library = SfxLibrary(
            config.sfx_manifest_path,
            project_root,
            sfx_tos=config.sfx_tos,
        )
        self.merger = EventMerger(config.merge)
        self.mixer = MixEngine(
            config.sample_rate,
            config.channels,
            config.mix.fade_ms,
            config.loudness.max_mix_peak_dbfs,
        )

    def run(self, audio_path: str | Path | None = None) -> list[dict]:
        if audio_path is None and self.config.tos_input.enabled:
            manifests = self._run_from_tos_stream()
            listening_path = self.project_root / self.config.output_dir / "dialogue_listening_manifest.json"
            write_json(listening_path, manifests)
            return manifests
        source_audios = self._resolve_audio_paths(audio_path)
        self.logger.info("Dialogue source audio files: %s", [str(path) for path in source_audios])
        manifests: list[dict] = []
        for source_audio in source_audios:
            manifests.extend(self._run_single(source_audio))

        listening_path = self.project_root / self.config.output_dir / "dialogue_listening_manifest.json"
        write_json(listening_path, manifests)
        return manifests

    def _run_from_tos_stream(self) -> list[dict]:
        input_dir = (self.project_root / self.config.dialogue_audio.input_dir).resolve()
        if self.config.tos_input.clean_before_download:
            clear_local_input_dir(input_dir)

        allowed_extensions = {
            item.lower() for item in self.config.dialogue_audio.allowed_audio_extensions
        }
        remote_uris = list_input_objects(
            self.config.tos_input,
            self.logger,
            allowed_extensions=allowed_extensions,
        )
        if not remote_uris:
            raise FileNotFoundError(
                f"No dialogue audio found in TOS source: {self.config.tos_input.source_uri}"
            )

        self.logger.info(
            "Starting TOS dialogue stream run for %s object(s) from %s",
            len(remote_uris),
            self.config.tos_input.source_uri,
        )
        manifests: list[dict] = []
        total_inputs = len(remote_uris)
        for input_index, remote_uri in enumerate(remote_uris, start=1):
            relative_path = remote_uri_to_relative_path(remote_uri, self.config.tos_input.source_uri)
            local_path = input_dir / relative_path
            self.logger.info(
                "Starting input %s/%s from TOS: %s -> %s",
                input_index,
                total_inputs,
                remote_uri,
                local_path,
            )
            fetch_input_object(remote_uri, local_path, self.config.tos_input, self.logger)
            input_started_at = time.perf_counter()
            try:
                manifests.extend(self._run_single(local_path))
            finally:
                self._cleanup_streamed_input(local_path, input_dir)
            self.logger.info(
                "Finished input %s/%s in %.2fs: %s",
                input_index,
                total_inputs,
                time.perf_counter() - input_started_at,
                remote_uri,
            )
        return manifests

    def _cleanup_streamed_input(self, local_path: Path, input_root: Path) -> None:
        try:
            if local_path.exists():
                local_path.unlink()
        finally:
            current = local_path.parent
            while current != input_root and current.exists():
                try:
                    current.rmdir()
                except OSError:
                    break
                current = current.parent

    def _run_single(self, source_audio: Path) -> list[dict]:
        run_started_at = time.perf_counter()
        self.logger.info("Processing dialogue source audio: %s", source_audio)

        analysis_audio = load_audio(source_audio, self.config.sample_rate, self.config.channels)
        duration_ms = len(analysis_audio)
        min_duration_ms = int(self.config.dialogue_audio.min_duration_seconds * 1000)
        if duration_ms < min_duration_ms:
            self.logger.info(
                "Skipping short dialogue audio: %s (duration_ms=%s < min_duration_ms=%s)",
                source_audio,
                duration_ms,
                min_duration_ms,
            )
            return []

        pauses = detect_pauses(source_audio)
        energy_peaks = detect_energy_peaks(source_audio)
        self.logger.info("Detected pauses: %s", pauses)
        self.logger.info("Detected energy peaks: %s", energy_peaks)

        self.logger.info(
            "Starting ASR for %s (duration=%.2fs, model=%s)",
            source_audio.name,
            duration_ms / 1000,
            self.config.dialogue_audio.asr.model,
        )
        transcript = transcribe_audio(source_audio, self.config.dialogue_audio.asr)
        if not transcript.get("duration_ms"):
            transcript["duration_ms"] = duration_ms
        asr_metrics = transcript.get("_request_metrics") or {}
        self.logger.info(
            "Finished ASR for %s in %.2fs (segments=%s)",
            source_audio.name,
            float(asr_metrics.get("elapsed_seconds", 0.0)),
            len(transcript.get("segments") or []),
        )
        self.logger.info("ASR transcript: %s", transcript.get("text", ""))

        manifests: list[dict] = []
        scene_mode = self.config.dialogue_audio.scene_mode
        if scene_mode in {"all", "all_templates"}:
            target_scenes = self._resolve_scenes()
            self.logger.info(
                "Rendering dialogue source audio across all scene templates: %s",
                target_scenes,
            )
            manifests.extend(
                self._run_scene_batch(
                    source_audio=source_audio,
                    analysis_audio=analysis_audio,
                    duration_ms=duration_ms,
                    transcript=transcript,
                    pauses=pauses,
                    energy_peaks=energy_peaks,
                    target_scenes=target_scenes,
                )
            )
            self.logger.info(
                "Finished dialogue source audio in %.2fs: %s",
                time.perf_counter() - run_started_at,
                source_audio,
            )
            return manifests

        forced_scene = None
        if scene_mode in {"config", "fixed", "manual"}:
            forced_scene = self._safe_scene(self.config.scene)

        plan = self._plan_for_scene(
            transcript=transcript,
            pauses=pauses,
            energy_peaks=energy_peaks,
            duration_ms=duration_ms,
            forced_scene=forced_scene,
        )
        scene = self._resolve_scene(plan.get("scene"))
        matcher, background_scheduler = self._build_scene_runtime(source_audio, scene)
        manifests.extend(
            self._render_scene_variants(
                source_audio=source_audio,
                analysis_audio=analysis_audio,
                duration_ms=duration_ms,
                transcript=transcript,
                pauses=pauses,
                energy_peaks=energy_peaks,
                plan=plan,
                scene=scene,
                matcher=matcher,
                background_scheduler=background_scheduler,
            )
        )
        self.logger.info(
            "Finished dialogue source audio in %.2fs: %s",
            time.perf_counter() - run_started_at,
            source_audio,
        )
        return manifests

    def _plan_for_scene(
        self,
        transcript: dict,
        pauses: list[dict],
        energy_peaks: list[dict],
        duration_ms: int,
        forced_scene: str | None = None,
    ) -> dict:
        planner_label = forced_scene or "auto"
        self.logger.info(
            "Starting dialogue planner for scene %s (model=%s)",
            planner_label,
            self.config.dialogue_audio.planner.model,
        )
        plan = plan_dialogue_script(
            transcript=transcript,
            pauses=pauses,
            energy_peaks=energy_peaks,
            audio_duration_ms=duration_ms,
            config=self.config.dialogue_audio.planner,
            forced_scene=forced_scene,
        )
        planner_metrics = plan.get("_request_metrics") or {}
        self.logger.info(
            "Finished dialogue planner for scene %s in %.2fs with %s event(s)",
            planner_label,
            float(planner_metrics.get("elapsed_seconds", 0.0)),
            len(plan.get("events") or []),
        )
        self.logger.info("Dialogue LLM plan for scene %s: %s", planner_label, plan)
        return plan

    def _run_scene_batch(
        self,
        source_audio: Path,
        analysis_audio,
        duration_ms: int,
        transcript: dict,
        pauses: list[dict],
        energy_peaks: list[dict],
        target_scenes: list[str],
    ) -> list[dict]:
        total_scenes = len(target_scenes)
        worker_count = self._scene_worker_count(total_scenes)
        if worker_count <= 1:
            manifests: list[dict] = []
            for scene_index, scene in enumerate(target_scenes, start=1):
                manifests.extend(
                    self._run_scene(
                        source_audio=source_audio,
                        analysis_audio=analysis_audio,
                        duration_ms=duration_ms,
                        transcript=transcript,
                        pauses=pauses,
                        energy_peaks=energy_peaks,
                        scene=scene,
                        scene_index=scene_index,
                        total_scenes=total_scenes,
                    )
                )
            return manifests

        self.logger.info(
            "Starting parallel scene rendering for %s with %s worker(s)",
            source_audio.name,
            worker_count,
        )
        manifests_by_index: dict[int, list[dict]] = {}
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="scene-worker",
        ) as executor:
            future_map = {
                executor.submit(
                    self._run_scene,
                    source_audio,
                    analysis_audio,
                    duration_ms,
                    transcript,
                    pauses,
                    energy_peaks,
                    scene,
                    scene_index,
                    total_scenes,
                ): scene_index
                for scene_index, scene in enumerate(target_scenes, start=1)
            }
            for future in as_completed(future_map):
                scene_index = future_map[future]
                manifests_by_index[scene_index] = future.result()

        manifests: list[dict] = []
        for scene_index in range(1, total_scenes + 1):
            manifests.extend(manifests_by_index.get(scene_index, []))
        return manifests

    def _run_scene(
        self,
        source_audio: Path,
        analysis_audio,
        duration_ms: int,
        transcript: dict,
        pauses: list[dict],
        energy_peaks: list[dict],
        scene: str,
        scene_index: int,
        total_scenes: int,
    ) -> list[dict]:
        self.logger.info(
            "Starting scene %s/%s for %s: %s",
            scene_index,
            total_scenes,
            source_audio.name,
            scene,
        )
        scene_started_at = time.perf_counter()
        plan = self._plan_for_scene(
            transcript=transcript,
            pauses=pauses,
            energy_peaks=energy_peaks,
            duration_ms=duration_ms,
            forced_scene=scene,
        )
        matcher, background_scheduler = self._build_scene_runtime(source_audio, scene)
        manifests = self._render_scene_variants(
            source_audio=source_audio,
            analysis_audio=analysis_audio,
            duration_ms=duration_ms,
            transcript=transcript,
            pauses=pauses,
            energy_peaks=energy_peaks,
            plan=plan,
            scene=scene,
            matcher=matcher,
            background_scheduler=background_scheduler,
        )
        self.logger.info(
            "Finished scene %s/%s for %s in %.2fs: %s",
            scene_index,
            total_scenes,
            source_audio.name,
            time.perf_counter() - scene_started_at,
            scene,
        )
        return manifests

    def _render_scene_variants(
        self,
        source_audio: Path,
        analysis_audio,
        duration_ms: int,
        transcript: dict,
        pauses: list[dict],
        energy_peaks: list[dict],
        plan: dict,
        scene: str,
        matcher: SfxMatcher,
        background_scheduler: BackgroundScheduler,
    ) -> list[dict]:
        emotion = self._resolve_emotion(plan.get("emotion"))
        scene_template = self.template_store.get(scene)
        base_timeline = self._timeline_from_plan(plan, duration_ms, scene_template)
        base_case_id = self._case_id(source_audio, scene)
        manifests: list[dict] = []

        for variant in self._variant_names():
            case_id = f"{base_case_id}_{variant}" if variant else base_case_id
            case_dir = ensure_dir(self.project_root / self.config.output_dir / case_id)
            for legacy_name in ("script.txt", "clean_speech.wav", "clean_dialogue.wav"):
                legacy_path = case_dir / legacy_name
                if legacy_path.exists():
                    legacy_path.unlink()
            final_path = case_dir / "final_mix.wav"
            metadata_path = case_dir / "metadata.json"
            variant_profile = get_variant_profile(variant)
            timeline = self._clone_timeline(base_timeline)
            timeline = self._apply_variant_profile(timeline, variant_profile)
            scheduled_timeline = background_scheduler.schedule(
                timeline=timeline,
                scene_template=scene_template,
                speech_duration_ms=duration_ms,
                background_gain_db=self.config.mix.background_gain_db,
                default_ducking_db=self.config.mix.default_ducking_db,
                variant=variant,
            )
            merged_timeline = self.merger.merge(scheduled_timeline)
            selected_timeline = self._select_assets(
                merged_timeline,
                self._scene_tags(scene, emotion),
                matcher,
            )
            self._apply_loudness_compensation(selected_timeline)
            variant_label = variant or "default"
            selected_count = sum(1 for item in selected_timeline if item.asset_path)
            skipped_count = sum(1 for item in selected_timeline if not item.asset_path)
            self.logger.info(
                "Prepared timeline for case %s (scene=%s, variant=%s, events=%s, selected=%s, skipped=%s)",
                case_id,
                scene,
                variant_label,
                len(selected_timeline),
                selected_count,
                skipped_count,
            )
            temp_dir = Path(tempfile.mkdtemp(prefix="pipeline_demo_dialogue_"))
            clean_path = temp_dir / "clean_dialogue.wav"
            try:
                export_wav(analysis_audio, clean_path)
                mix_started_at = time.perf_counter()
                self.logger.info(
                    "Starting mix for case %s -> %s",
                    case_id,
                    final_path,
                )
                self.mixer.mix(
                    clean_speech_path=clean_path,
                    timeline=selected_timeline,
                    output_path=final_path,
                    speech_gain_db=self.config.mix.speech_gain_db,
                )
                self.logger.info(
                    "Finished mix for case %s in %.2fs",
                    case_id,
                    time.perf_counter() - mix_started_at,
                )
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

            metadata = {"merged_events": [to_dict(item) for item in merged_timeline]}
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
            self.logger.info(
                "Exported dialogue case: %s",
                {"final_mix": str(final_path), "metadata": str(metadata_path)},
            )
            sync_case_dir(case_dir, self.config.tos_sync, self.logger)
        return manifests

    def _resolve_audio_paths(self, override_path: str | Path | None) -> list[Path]:
        if override_path:
            path = Path(override_path)
            resolved = path if path.is_absolute() else (self.project_root / path).resolve()
            return [resolved]
        configured = self.config.dialogue_audio.audio_path
        if configured:
            path = Path(configured)
            resolved = path if path.is_absolute() else (self.project_root / path).resolve()
            return [resolved]
        input_dir = (self.project_root / self.config.dialogue_audio.input_dir).resolve()
        extensions = {item.lower() for item in self.config.dialogue_audio.allowed_audio_extensions}
        if not input_dir.exists():
            raise FileNotFoundError(f"Dialogue input directory not found: {input_dir}")
        candidates = [
            path
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in extensions
        ]
        if not candidates:
            raise FileNotFoundError(
                f"No dialogue audio found recursively in: {input_dir}"
            )
        return sorted(
            candidates,
            key=lambda path: (
                str(path.relative_to(input_dir)).lower(),
                path.stat().st_mtime,
            ),
        )

    def _timeline_from_plan(self, plan: dict, duration_ms: int, scene_template) -> list[TimelineEvent]:
        timeline: list[TimelineEvent] = []
        template_allowed = set(scene_template.allowed_foreground_events) | set(scene_template.allowed_background_events)
        global_allowed = set(self.config.allowed_events)
        for index, event in enumerate(plan.get("events") or [], start=1):
            event_type = event.get("event_type")
            if event_type not in TAXONOMY:
                continue
            if event_type not in template_allowed or event_type not in global_allowed:
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

    def _select_assets(
        self,
        timeline: list[TimelineEvent],
        scene_tags: set[str],
        matcher: SfxMatcher,
    ) -> list[TimelineEvent]:
        for event in timeline:
            result = matcher.match(event, scene_tags=scene_tags)
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
            tags.update({"street", "outdoor", "traffic"})
        if "rain" in scene:
            tags.update({"rain", "weather", "wet"})
        if "sunny" in scene:
            tags.update({"sunny", "daytime", "dry"})
        if "cafe" in scene:
            tags.update({"cafe", "coffee", "crowd", "indoor"})
        if "restaurant" in scene:
            tags.update({"restaurant", "crowd", "indoor", "table", "kitchen"})
        if "indoor" in scene or "office" in scene:
            tags.update({"indoor", "room"})
        if "office" in scene:
            tags.update({"office", "desk"})
        if "library" in scene:
            tags.update({"library", "study", "quiet", "indoor"})
        if "factory" in scene or "workshop" in scene:
            tags.update({"industrial", "factory", "machine", "indoor"})
        if "exercise" in scene:
            tags.update({"exercise", "rest", "indoor", "room"})
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

    def _scene_worker_count(self, total_scenes: int) -> int:
        configured = max(1, self.config.dialogue_audio.scene_parallel_workers)
        return min(configured, max(1, total_scenes))

    def _build_scene_runtime(
        self,
        source_audio: Path,
        scene: str,
    ) -> tuple[SfxMatcher, BackgroundScheduler]:
        matcher_rng = self._make_seeded_rng(source_audio, scene, "matcher")
        scheduler_rng = self._make_seeded_rng(source_audio, scene, "scheduler")
        return (
            SfxMatcher(self.library, matcher_rng, self.config.asset_selection),
            BackgroundScheduler(self.config.background_scheduler, scheduler_rng),
        )

    def _make_seeded_rng(
        self,
        source_audio: Path,
        scene: str,
        scope: str,
    ) -> random.Random:
        seed_basis = "|".join(
            [
                str(self.config.random_seed or 0),
                str(source_audio.resolve()),
                scene,
                scope,
            ]
        )
        digest = hashlib.sha1(seed_basis.encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))

    def _resolve_scene(self, planned_scene: object) -> str:
        scene_mode = self.config.dialogue_audio.scene_mode
        if scene_mode in {"config", "fixed", "manual"}:
            return self._safe_scene(self.config.scene)
        return self._safe_scene(planned_scene)

    def _resolve_scenes(self) -> list[str]:
        scene_mode = self.config.dialogue_audio.scene_mode
        if scene_mode in {"all", "all_templates"}:
            return self.template_store.names()
        if scene_mode in {"config", "fixed", "manual"}:
            return [self._safe_scene(self.config.scene)]
        return []

    def _resolve_emotion(self, planned_emotion: object) -> str:
        emotion_mode = self.config.dialogue_audio.emotion_mode
        if emotion_mode in {"config", "fixed", "manual"}:
            return str(self.config.emotion or "tense")
        return str(planned_emotion or "tense")

    def _safe_scene(self, scene: object) -> str:
        try:
            self.template_store.get(str(scene))
            return str(scene)
        except Exception:
            return "rainy_street_chat"

    def _case_id(self, source_audio: Path, scene: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_root = (self.project_root / self.config.dialogue_audio.input_dir).resolve()
        try:
            relative_source = source_audio.resolve().relative_to(input_root)
            source_key = relative_source.with_suffix("").as_posix()
        except ValueError:
            source_key = source_audio.stem
        safe_stem = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in source_key)
        safe_scene = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in scene)
        return f"dialogue_{stamp}_{safe_stem[:24]}_{safe_scene[:24]}"

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
