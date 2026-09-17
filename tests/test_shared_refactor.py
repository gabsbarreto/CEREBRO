from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from io import BytesIO
from pathlib import Path

from app import config
from app.models import JobSettings, public_model_presets
from app.services import jobs
from app.services import openai_rq
from app.shared.cli import parse_bool, parse_bool_arg
from app.shared.openai_responses import response_diagnostics, response_text
from app.shared.process_runner import run_event_process
from app.shared.rq_chat import build_chat_prompt, combined_prompt, strip_thinking


class SharedHelperTests(unittest.TestCase):
    def test_bool_parsing_preserves_script_semantics(self) -> None:
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("1"))
        self.assertFalse(parse_bool("false"))
        self.assertTrue(parse_bool_arg("yes"))
        self.assertFalse(parse_bool_arg("n"))

    def test_rq_chat_prompt_uses_chat_template_when_available(self) -> None:
        class Tokenizer:
            def apply_chat_template(self, messages, tokenize, add_generation_prompt, enable_thinking=False):
                self.messages = messages
                self.enable_thinking = enable_thinking
                return "templated"

        tokenizer = Tokenizer()
        self.assertEqual(build_chat_prompt(tokenizer, "SYS", "USER", True), "templated")
        self.assertEqual(
            tokenizer.messages,
            [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}],
        )
        self.assertTrue(tokenizer.enable_thinking)

    def test_rq_chat_prompt_fallback_and_thinking_strip(self) -> None:
        fallback = build_chat_prompt(object(), "SYS", "USER", False)
        self.assertEqual(fallback, combined_prompt("SYS", "USER"))
        self.assertEqual(strip_thinking("a <think>hidden</think> b"), "a  b")

    def test_openai_response_helpers_handle_sdk_shapes(self) -> None:
        class Content:
            type = "output_text"
            text = "from content"

        class Item:
            content = [Content()]
            type = "message"

        class Response:
            id = "resp_1"
            status = "completed"
            incomplete_details = None
            usage = {"total_tokens": 1}
            output = [Item()]

        response = Response()
        self.assertEqual(response_text(response), "from content")
        diagnostics = response_diagnostics(response)
        self.assertEqual(diagnostics["id"], "resp_1")
        self.assertEqual(diagnostics["output_types"], ["message"])

    def test_event_process_runner_parses_json_events(self) -> None:
        events = []
        result = run_event_process(
            cmd=[
                sys.executable,
                "-c",
                "import json; print('noise'); print(json.dumps({'event':'done','value':3}))",
            ],
            job_id=None,
            on_event=events.append,
            cancel_message="cancelled",
        )
        self.assertEqual(result.return_code, 0)
        self.assertIn("noise", result.details)
        self.assertEqual(events, [{"event": "done", "value": 3}])

    def test_openai_api_key_resolution_order(self) -> None:
        original_key_file = openai_rq.OPENAI_API_KEY_FILE
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                openai_rq.OPENAI_API_KEY_FILE = Path(tmpdir) / "api_key.txt"
                openai_rq.OPENAI_API_KEY_FILE.write_text("sk-file\n", encoding="utf-8")

                self.assertEqual(openai_rq.resolve_openai_api_key(" sk-form ", {}), "sk-form")
                self.assertEqual(
                    openai_rq.resolve_openai_api_key("", {"OPENAI_API_KEY": " sk-env "}),
                    "sk-env",
                )
                self.assertEqual(openai_rq.resolve_openai_api_key("", {}), "sk-file")

                openai_rq.OPENAI_API_KEY_FILE.unlink()
                self.assertEqual(openai_rq.resolve_openai_api_key("", {}), "")
        finally:
            openai_rq.OPENAI_API_KEY_FILE = original_key_file

    def test_gpt54_mini_xhigh_preset_is_public_openai_model(self) -> None:
        settings = JobSettings.from_form({"rq_model_preset": "openai_gpt54_mini_xhigh"})
        self.assertEqual(settings.rq_provider, "openai")
        self.assertEqual(settings.rq_screening_model, "gpt-5.4-mini")
        self.assertTrue(settings.rq_enable_thinking)
        self.assertEqual(settings.openai_reasoning_effort, "xhigh")

        public_presets = {preset["id"]: preset for preset in public_model_presets()}
        self.assertIn("openai_gpt54_mini_xhigh", public_presets)
        self.assertEqual(public_presets["openai_gpt54_mini_xhigh"]["settings"]["model"], "gpt-5.4-mini")
        self.assertEqual(public_presets["openai_gpt54_mini_xhigh"]["settings"]["openai_reasoning_effort"], "xhigh")

    def test_gpt54_mini_high_preset_is_separate_public_option(self) -> None:
        settings = JobSettings.from_form({"rq_model_preset": "openai_gpt54_mini_high"})
        self.assertEqual(settings.rq_provider, "openai")
        self.assertEqual(settings.rq_screening_model, "gpt-5.4-mini")
        self.assertEqual(settings.rq_model_preset, "openai_gpt54_mini_high")
        self.assertEqual(settings.openai_reasoning_effort, "high")

        public_presets = {preset["id"]: preset for preset in public_model_presets()}
        self.assertIn("openai_gpt54_mini_high", public_presets)
        self.assertEqual(public_presets["openai_gpt54_mini_high"]["settings"]["model"], "gpt-5.4-mini")
        self.assertEqual(public_presets["openai_gpt54_mini_high"]["settings"]["openai_reasoning_effort"], "high")

    def test_gpt54_nano_xhigh_preset_is_public_and_respects_model_limit(self) -> None:
        settings = JobSettings.from_form({"rq_model_preset": "openai_gpt54_nano_xhigh"})
        self.assertEqual(settings.rq_provider, "openai")
        self.assertEqual(settings.rq_screening_model, "gpt-5.4-nano")
        self.assertEqual(settings.rq_model_preset, "openai_gpt54_nano_xhigh")
        self.assertTrue(settings.rq_enable_thinking)
        self.assertEqual(settings.openai_reasoning_effort, "xhigh")
        self.assertEqual(settings.rq_max_tokens, 128_000)

        public_presets = {preset["id"]: preset for preset in public_model_presets()}
        self.assertIn("openai_gpt54_nano_xhigh", public_presets)
        self.assertEqual(public_presets["openai_gpt54_nano_xhigh"]["settings"]["model"], "gpt-5.4-nano")
        self.assertEqual(public_presets["openai_gpt54_nano_xhigh"]["settings"]["max_tokens"], 128_000)
        self.assertEqual(public_presets["openai_gpt54_nano_xhigh"]["settings"]["openai_reasoning_effort"], "xhigh")

    def test_all_gpt56_model_and_reasoning_presets_are_public(self) -> None:
        model_tiers = ("sol", "terra", "luna")
        reasoning_efforts = ("none", "low", "medium", "high", "xhigh", "max")
        public_presets = {preset["id"]: preset for preset in public_model_presets()}

        for tier in model_tiers:
            for effort in reasoning_efforts:
                preset_id = f"openai_gpt56_{tier}_{effort}"
                model = f"gpt-5.6-{tier}"
                settings = JobSettings.from_form({"rq_model_preset": preset_id})
                with self.subTest(preset_id=preset_id):
                    self.assertEqual(settings.rq_provider, "openai")
                    self.assertEqual(settings.rq_screening_model, model)
                    self.assertEqual(settings.rq_model_preset, preset_id)
                    self.assertTrue(settings.rq_enable_thinking)
                    self.assertEqual(settings.openai_reasoning_effort, effort)
                    self.assertEqual(settings.rq_max_tokens, 128_000)

                    self.assertIn(preset_id, public_presets)
                    self.assertEqual(public_presets[preset_id]["settings"]["model"], model)
                    self.assertEqual(public_presets[preset_id]["settings"]["max_tokens"], 128_000)
                    self.assertEqual(public_presets[preset_id]["settings"]["openai_reasoning_effort"], effort)

    def test_gpt54_mini_superseded_preset_family_resolves_to_xhigh(self) -> None:
        settings = JobSettings.from_form({"rq_model_preset": "openai_gpt54_mini_previous"})
        self.assertEqual(settings.rq_provider, "openai")
        self.assertEqual(settings.rq_screening_model, "gpt-5.4-mini")
        self.assertEqual(settings.rq_model_preset, "openai_gpt54_mini_xhigh")
        self.assertEqual(settings.openai_reasoning_effort, "xhigh")

    def test_openai_pdf_file_mode_is_openai_only(self) -> None:
        openai_settings = JobSettings.from_form(
            {"rq_model_preset": "openai_gpt5_mini_high", "openai_input_mode": "pdf_file"}
        )
        self.assertEqual(openai_settings.openai_input_mode, "pdf_file")

        local_settings = JobSettings.from_form(
            {"rq_model_preset": "qwen35_9b_8bit_reasoning", "openai_input_mode": "pdf_file"}
        )
        self.assertEqual(local_settings.openai_input_mode, "ocr_text")

    def test_openai_rq_passes_input_file_arguments(self) -> None:
        from app.services import openai_rq

        calls = []
        original_runner = openai_rq.run_event_process
        try:
            def fake_runner(**kwargs):
                calls.append(kwargs)
                return type("Result", (), {"return_code": 0, "details": ""})()

            openai_rq.run_event_process = fake_runner
            openai_rq.run_openai_rq(
                job_id="job-file",
                model="gpt-5.4-mini",
                system_prompt_file=Path("system.txt"),
                user_prompt_file=Path("user.txt"),
                output_file=Path("out.md"),
                max_tokens=100,
                enable_reasoning=True,
                reasoning_effort="xhigh",
                input_file_id="file-abc",
            )
        finally:
            openai_rq.run_event_process = original_runner

        cmd = calls[0]["cmd"]
        self.assertIn("--input-file-id", cmd)
        self.assertEqual(cmd[cmd.index("--input-file-id") + 1], "file-abc")
        self.assertEqual(cmd[cmd.index("--reasoning-effort") + 1], "xhigh")

    def test_openai_rq_passes_multiple_input_file_paths(self) -> None:
        calls = []
        original_runner = openai_rq.run_event_process
        try:
            def fake_runner(**kwargs):
                calls.append(kwargs)
                return type("Result", (), {"return_code": 0, "details": ""})()

            openai_rq.run_event_process = fake_runner
            openai_rq.run_openai_rq(
                job_id="study-bundle",
                model="gpt-5.4-mini",
                system_prompt_file=Path("system.txt"),
                user_prompt_file=Path("user.txt"),
                output_file=Path("out.md"),
                max_tokens=100,
                enable_reasoning=True,
                reasoning_effort="high",
                input_file_paths=[Path("primary.pdf"), Path("supplement.xlsx")],
            )
        finally:
            openai_rq.run_event_process = original_runner

        cmd = calls[0]["cmd"]
        indices = [index for index, value in enumerate(cmd) if value == "--input-file-path"]
        self.assertEqual([cmd[index + 1] for index in indices], ["primary.pdf", "supplement.xlsx"])


class JobIdentityTests(unittest.TestCase):
    def test_settings_metadata_updates_preserve_persisted_shape(self) -> None:
        settings = JobSettings.from_form(
            {
                "rq_model_preset": "openai_gpt5_mini_high",
                "openai_api_key": "sk-secret",
                "rq_prompt_filename": "prompt_a.txt",
                "rq_system_prompt": "system",
            }
        )

        payload = jobs.settings_metadata_updates(settings)
        self.assertEqual(payload["rq_provider"], "openai")
        self.assertEqual(payload["rq_screening_model"], "gpt-5-mini")
        self.assertEqual(payload["rq_prompt_filename"], "prompt_a.txt")
        self.assertEqual(payload["openai_reasoning_effort"], "high")
        self.assertNotIn("openai_api_key", payload["settings"])
        self.assertTrue(payload["settings"]["openai_api_key_provided"])

        completion_payload = jobs.settings_metadata_updates(
            settings,
            rq_prompt_filename="loaded_prompt.txt",
            include_settings=False,
        )
        self.assertEqual(completion_payload["rq_prompt_filename"], "loaded_prompt.txt")
        self.assertNotIn("settings", completion_payload)

    def test_run_identity_and_ocr_copy_helpers(self) -> None:
        original_jobs_dir = config.JOBS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.JOBS_DIR = Path(tmpdir) / "jobs"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                source_id = "source"
                target_id = "target"
                source_root = jobs.create_job(
                    source_id,
                    "same-file.pdf",
                    JobSettings.from_form(
                        {"rq_prompt_filename": "prompt1.txt", "rq_model_preset": "openai_gpt5_mini_high"}
                    ),
                )
                (source_root / "outputs" / "rq_screening_output.md").write_text("decision", encoding="utf-8")
                (source_root / "outputs" / "merged_full_text.txt").write_text(
                    "merged OCR text long enough to reuse",
                    encoding="utf-8",
                )
                (source_root / "ocr_text" / "page_0001.md").write_text("page OCR", encoding="utf-8")
                jobs.update_metadata(
                    source_root,
                    rq_prompt_filename="prompt1.txt",
                    rq_screening_model="gpt-5-mini",
                    openai_input_mode="ocr_text",
                    number_of_pages=1,
                )
                jobs.update_status(source_id, status="complete", stage="complete", message="complete", progress=1.0)

                self.assertEqual(
                    jobs.find_screened_job_by_run_identity("same-file.pdf", "prompt1.txt", "gpt-5-mini")["job_id"],
                    source_id,
                )
                self.assertIsNone(jobs.find_screened_job_by_run_identity("same-file.pdf", "prompt2.txt", "gpt-5-mini"))
                self.assertIsNone(
                    jobs.find_screened_job_by_run_identity(
                        "same-file.pdf",
                        "prompt1.txt",
                        "gpt-5-mini",
                        "pdf_file",
                    )
                )

                target_root = jobs.create_job(target_id, "same-file.pdf", JobSettings())
                jobs.copy_reusable_ocr(source_id, target_root)
                self.assertTrue((target_root / "ocr_text" / "page_0001.md").exists())
                self.assertIn(
                    "merged OCR",
                    (target_root / "outputs" / "merged_full_text.txt").read_text(encoding="utf-8"),
                )
                self.assertTrue(jobs.read_metadata(target_root)["pending_rerun_screening_only"])
        finally:
            config.JOBS_DIR = original_jobs_dir

    def test_reusable_openai_file_id_helpers(self) -> None:
        original_jobs_dir = config.JOBS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.JOBS_DIR = Path(tmpdir) / "jobs"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                source_root = jobs.create_job("source-file", "Pilots/122710267.pdf", JobSettings())
                jobs.update_metadata(
                    source_root,
                    pdf_sha256="digest-1",
                    openai_file_id="file-abc",
                    openai_input_mode="pdf_file",
                )
                match = jobs.find_reusable_openai_file_job("digest-1", "Other/122710267.pdf")
                self.assertEqual(match["job_id"], "source-file")

                target_root = jobs.create_job("target-file", "122710267.pdf", JobSettings())
                jobs.copy_reusable_openai_file("source-file", target_root)
                metadata = jobs.read_metadata(target_root)
                self.assertEqual(metadata["openai_file_id"], "file-abc")
                self.assertEqual(metadata["openai_file_reused_from_job_id"], "source-file")
        finally:
            config.JOBS_DIR = original_jobs_dir

    def test_different_identity_rerun_child_job_reuses_source_ocr(self) -> None:
        original_jobs_dir = config.JOBS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.JOBS_DIR = Path(tmpdir) / "jobs"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                source_settings = JobSettings.from_form(
                    {"rq_prompt_filename": "prompt1.txt", "rq_model_preset": "openai_gpt5_mini_high"}
                )
                source_root = jobs.create_job("source", "same-file.pdf", source_settings)
                (source_root / "input" / "uploaded.pdf").write_bytes(b"%PDF source")
                (source_root / "outputs" / "merged_full_text.txt").write_text(
                    "merged OCR text long enough to reuse",
                    encoding="utf-8",
                )
                (source_root / "ocr_text" / "page_0001.md").write_text("page OCR", encoding="utf-8")
                jobs.update_metadata(
                    source_root,
                    rq_prompt_filename="prompt1.txt",
                    rq_screening_model="gpt-5-mini",
                    number_of_pages=1,
                )

                self.assertTrue(jobs.job_matches_run_identity(source_root, source_settings))
                child_settings = JobSettings.from_form(
                    {"rq_prompt_filename": "prompt2.txt", "rq_model_preset": "qwen35_9b_8bit_reasoning"}
                )
                self.assertFalse(jobs.job_matches_run_identity(source_root, child_settings))

                child_id, child_root = jobs.create_screening_rerun_child_job("source", child_settings)
                self.assertNotEqual(child_id, "source")
                self.assertEqual((child_root / "input" / "uploaded.pdf").read_bytes(), b"%PDF source")
                self.assertTrue((child_root / "ocr_text" / "page_0001.md").exists())
                self.assertIn(
                    "merged OCR",
                    (child_root / "outputs" / "merged_full_text.txt").read_text(encoding="utf-8"),
                )
                metadata = jobs.read_metadata(child_root)
                self.assertEqual(metadata["rerun_created_from_job_id"], "source")
                self.assertEqual(metadata["reused_ocr_from_job_id"], "source")
                self.assertEqual(metadata["rq_prompt_filename"], "prompt2.txt")
                self.assertEqual(metadata["rq_screening_model"], config.RQ_SCREENING_MODEL)
                self.assertEqual(metadata["rq_max_tokens"], config.RQ_SCREENING_MAX_TOKENS)
                self.assertTrue(metadata["rq_enable_thinking"])
                self.assertTrue(metadata["pending_rerun_screening_only"])
        finally:
            config.JOBS_DIR = original_jobs_dir


class StudyBundleTests(unittest.TestCase):
    def test_bundle_persistence_and_rerun_keep_every_source_file(self) -> None:
        class Upload:
            def __init__(self, filename: str, payload: bytes) -> None:
                self.filename = filename
                self.file = BytesIO(payload)

        original_jobs_dir = config.JOBS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.JOBS_DIR = Path(tmpdir) / "jobs"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                settings = JobSettings()
                source_root = jobs.create_job("bundle-source", "article.pdf", settings)
                primary = Upload("article.pdf", b"%PDF primary")
                supplement = Upload("article supplementary.csv", b"study_id,result\nA,positive\n")
                bundle = jobs.save_source_bundle(
                    source_root,
                    primary,
                    "Pilot/article.pdf",
                    [{"upload": supplement, "relative_path": "Pilot/article supplementary.csv"}],
                )
                jobs.update_metadata(source_root, **bundle)

                records = jobs.source_file_records(source_root)
                self.assertEqual([record["role"] for record in records], ["primary_pdf", "supporting_file"])
                self.assertEqual([record["filename"] for record in records], ["article.pdf", "article supplementary.csv"])
                self.assertTrue((source_root / "input" / "uploaded.pdf").exists())
                self.assertTrue((source_root / "input" / "attachments").exists())
                self.assertEqual(bundle["source_bundle_sha256"], jobs.source_bundle_sha256(records))

                _child_id, child_root = jobs.create_screening_rerun_child_job("bundle-source", settings)
                child_records = jobs.source_file_records(child_root)
                self.assertEqual([record["filename"] for record in child_records], ["article.pdf", "article supplementary.csv"])
                self.assertEqual(
                    (child_records[1]["path"]).read_bytes(),
                    b"study_id,result\nA,positive\n",
                )
        finally:
            config.JOBS_DIR = original_jobs_dir

    def test_bundle_validation_maps_supporting_files_to_primary_pdf(self) -> None:
        from app.main import validated_study_upload_bundles
        from starlette.datastructures import UploadFile

        primary_one = UploadFile(filename="one.pdf", file=BytesIO(b"%PDF one"))
        primary_two = UploadFile(filename="two.pdf", file=BytesIO(b"%PDF two"))
        supplement = UploadFile(filename="one supplement.xlsx", file=BytesIO(b"xlsx"))
        bundles = validated_study_upload_bundles(
            [primary_one, primary_two],
            None,
            ["Pilot/one.pdf", "Pilot/two.pdf"],
            [supplement],
            ["0"],
            ["Pilot/one supplement.xlsx"],
        )

        self.assertEqual(len(bundles), 2)
        self.assertEqual(bundles[0]["relative_path"], "Pilot/one.pdf")
        self.assertEqual(bundles[0]["attachments"][0]["relative_path"], "Pilot/one supplement.xlsx")
        self.assertEqual(bundles[1]["attachments"], [])

    def test_pdf_job_endpoint_persists_multipart_study_bundle(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app, job_queue
        from app.services import projects

        original_data_dir = config.DATA_DIR
        original_jobs_dir = config.JOBS_DIR
        original_projects_dir = config.PROJECTS_DIR
        original_enqueue = job_queue.enqueue
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config.DATA_DIR = root / "data"
                config.JOBS_DIR = config.DATA_DIR / "jobs"
                config.PROJECTS_DIR = config.DATA_DIR / "projects"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.get_default_project()
                queued: list[tuple[str, str]] = []
                job_queue.enqueue = lambda job_id, _settings, *, project_id=None: queued.append((job_id, str(project_id)))

                response = TestClient(app).post(
                    "/api/jobs",
                    data={
                        "project_id": project["project_id"],
                        "rq_model_preset": "qwen35_9b_8bit_reasoning",
                        "rq_system_prompt": "Extract the supplied study.",
                        "pdf_relative_paths": "With attachment/article.pdf",
                        "attachment_primary_indices": "0",
                        "attachment_relative_paths": "With attachment/article supplementary.csv",
                    },
                    files=[
                        ("pdfs", ("article.pdf", b"%PDF primary", "application/pdf")),
                        ("attachments", ("article supplementary.csv", b"study_id,result\nA,positive\n", "text/csv")),
                    ],
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["count"], 1)
                self.assertEqual(payload["jobs"][0]["supporting_file_count"], "1")
                self.assertEqual(queued[0][1], project["project_id"])
                root = jobs.job_dir(payload["job_id"], project["project_id"])
                records = jobs.source_file_records(root)
                self.assertEqual([record["filename"] for record in records], ["article.pdf", "article supplementary.csv"])
                self.assertEqual(records[1]["relative_path"], "With attachment/article supplementary.csv")
        finally:
            job_queue.enqueue = original_enqueue
            config.DATA_DIR = original_data_dir
            config.JOBS_DIR = original_jobs_dir
            config.PROJECTS_DIR = original_projects_dir

    def test_csv_supporting_source_is_transcribed_for_local_prompting(self) -> None:
        from app.services import supplementary_sources

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "support.csv"
            source.write_text("study_id,result\nA,positive\n", encoding="utf-8")
            transcripts = supplementary_sources.transcript_spreadsheet_sources(
                [{"filename": "support.csv", "path": source}],
                root / "outputs",
            )

            self.assertEqual(len(transcripts), 1)
            self.assertEqual(transcripts[0].warning, "")
            self.assertTrue(transcripts[0].output_path and transcripts[0].output_path.exists())
            self.assertIn("Supporting spreadsheet: support.csv", transcripts[0].text)
            self.assertIn("study_id\tresult", transcripts[0].text)

    def test_ocr_merge_includes_primary_and_supporting_pdf_pages_in_order(self) -> None:
        from app.services.ocr_merge import merge_page_texts

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ocr_dir = root / "ocr_text"
            ocr_dir.mkdir()
            (ocr_dir / "page_000001__primary_0001.md").write_text("Primary text", encoding="utf-8")
            (ocr_dir / "page_000002__supporting_001_0001.md").write_text("Supporting text", encoding="utf-8")
            merged = merge_page_texts(ocr_dir, root / "merged.md")

            self.assertLess(merged.index("Primary text"), merged.index("Supporting text"))
            self.assertIn("[PRIMARY PDF - PAGE 1]", merged)
            self.assertIn("[SUPPORTING PDF 1 - PAGE 1]", merged)


class PipelineConcurrencyTests(unittest.TestCase):
    def test_openai_pdf_file_mode_skips_ocr_and_stores_file_id(self) -> None:
        from app.services import rq_screening_pipeline as pipeline

        original_jobs_dir = config.JOBS_DIR
        original_summary_path = config.SUMMARY_XLSX_PATH
        original_page_count = pipeline.page_count
        original_render = pipeline.render_pdf_to_images
        original_ocr = pipeline.run_deepseek_ocr
        original_openai = pipeline.run_openai_rq
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config.JOBS_DIR = root / "jobs"
                config.SUMMARY_XLSX_PATH = root / "summary.xlsx"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)

                pipeline.page_count = lambda _pdf_path: 2
                pipeline.render_pdf_to_images = lambda *args, **kwargs: self.fail("OCR rendering should be skipped")
                pipeline.run_deepseek_ocr = lambda *args, **kwargs: self.fail("OCR should be skipped")

                def fake_openai_runner(**kwargs) -> None:
                    self.assertEqual(kwargs["input_file_id"], "")
                    self.assertEqual(Path(kwargs["input_file_path"]).name, "uploaded.pdf")
                    callback = kwargs.get("on_event")
                    if callback is not None:
                        callback({"event": "openai_file_uploaded", "file_id": "file-abc"})
                        callback({"event": "rq_generation_finished"})
                    Path(kwargs["output_file"]).write_text("direct PDF result", encoding="utf-8")

                pipeline.run_openai_rq = fake_openai_runner
                settings = JobSettings.from_form(
                    {
                        "rq_model_preset": "openai_gpt5_mini_high",
                        "openai_input_mode": "pdf_file",
                        "rq_prompt_filename": "prompt_file.txt",
                        "rq_system_prompt": "Use the user-provided text.",
                    }
                )
                job_root = jobs.create_job("pdf-file-job", "paper.pdf", settings)
                (job_root / "input" / "uploaded.pdf").write_bytes(b"%PDF mock")

                pipeline.run_job("pdf-file-job", settings, defer_openai=False)

                status = jobs.read_status("pdf-file-job")
                metadata = jobs.read_metadata(job_root)
                self.assertEqual(status["status"], "complete")
                self.assertEqual(metadata["openai_file_id"], "file-abc")
                self.assertTrue(metadata["openai_file_complete"])
                self.assertFalse(metadata["ocr_complete"])
                self.assertFalse((job_root / "outputs" / "merged_full_text.txt").exists())
        finally:
            pipeline.page_count = original_page_count
            pipeline.render_pdf_to_images = original_render
            pipeline.run_deepseek_ocr = original_ocr
            pipeline.run_openai_rq = original_openai
            config.JOBS_DIR = original_jobs_dir
            config.SUMMARY_XLSX_PATH = original_summary_path

    def test_openai_pdf_file_mode_sends_primary_and_supporting_sources(self) -> None:
        from app.services import rq_screening_pipeline as pipeline

        class Upload:
            def __init__(self, filename: str, payload: bytes) -> None:
                self.filename = filename
                self.file = BytesIO(payload)

        original_jobs_dir = config.JOBS_DIR
        original_summary_path = config.SUMMARY_XLSX_PATH
        original_page_count = pipeline.page_count
        original_openai = pipeline.run_openai_rq
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config.JOBS_DIR = root / "jobs"
                config.SUMMARY_XLSX_PATH = root / "summary.xlsx"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                pipeline.page_count = lambda _pdf_path: 2

                captured = {}

                def fake_openai_runner(**kwargs) -> None:
                    captured.update(kwargs)
                    self.assertEqual(kwargs["input_file_id"], "")
                    self.assertIsNone(kwargs["input_file_path"])
                    self.assertEqual(
                        [Path(path).suffix for path in kwargs["input_file_paths"]],
                        [".pdf", ".xlsx"],
                    )
                    callback = kwargs.get("on_event")
                    if callback is not None:
                        callback({"event": "openai_file_uploaded", "file_id": "file-primary", "source_index": 0})
                        callback({"event": "openai_file_uploaded", "file_id": "file-support", "source_index": 1})
                        callback({"event": "rq_generation_finished"})
                    Path(kwargs["output_file"]).write_text("bundle result", encoding="utf-8")

                pipeline.run_openai_rq = fake_openai_runner
                settings = JobSettings.from_form(
                    {
                        "rq_model_preset": "openai_gpt5_mini_high",
                        "openai_input_mode": "pdf_file",
                        "rq_prompt_filename": "prompt_file.txt",
                        "rq_system_prompt": "Use all attached study sources.",
                    }
                )
                job_root = jobs.create_job("pdf-bundle-job", "paper.pdf", settings)
                metadata = jobs.save_source_bundle(
                    job_root,
                    Upload("paper.pdf", b"%PDF mock"),
                    "With attachment/paper.pdf",
                    [{"upload": Upload("paper supplementary.xlsx", b"xlsx"), "relative_path": "With attachment/paper supplementary.xlsx"}],
                )
                jobs.update_metadata(job_root, **metadata)

                pipeline.run_job("pdf-bundle-job", settings, defer_openai=False)

                self.assertTrue(captured)
                persisted = jobs.read_metadata(job_root)
                self.assertEqual(persisted["openai_file_ids"], ["file-primary", "file-support"])
                self.assertTrue(persisted["openai_file_complete"])
                self.assertEqual(jobs.read_status("pdf-bundle-job")["status"], "complete")
        finally:
            pipeline.page_count = original_page_count
            pipeline.run_openai_rq = original_openai
            config.JOBS_DIR = original_jobs_dir
            config.SUMMARY_XLSX_PATH = original_summary_path

    def test_deferred_openai_inference_does_not_block_next_ocr_job(self) -> None:
        from app.services import rq_screening_pipeline as pipeline
        from app.services.openai_inference_queue import OpenAIInferenceQueue

        original_jobs_dir = config.JOBS_DIR
        original_summary_path = config.SUMMARY_XLSX_PATH
        original_queue = pipeline.openai_inference_queue
        original_page_count = pipeline.page_count
        original_render = pipeline.render_pdf_to_images
        original_discover = pipeline.discover_deepseek_model
        original_ocr = pipeline.run_deepseek_ocr

        events: list[str] = []
        event_lock = threading.Lock()
        first_openai_started = threading.Event()
        release_first_openai = threading.Event()

        def record(event: str) -> None:
            with event_lock:
                events.append(event)

        def fake_render(_pdf_path: Path, _rendered_dir: Path, ocr_dir: Path, *, dpi: int) -> list[Path]:
            image = ocr_dir / "page_0001.png"
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"image")
            return [image]

        def fake_ocr(**kwargs) -> None:
            job_id = kwargs["job_id"]
            output_dir = Path(kwargs["output_dir"])
            record(f"ocr_start:{job_id}")
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "page_0001.md").write_text(
                f"OCR text for {job_id}. This is long enough to pass the merge validation.",
                encoding="utf-8",
            )
            callback = kwargs.get("on_event")
            if callback is not None:
                callback({"event": "ocr_finished"})
            record(f"ocr_finish:{job_id}")

        def fake_openai_runner(**kwargs) -> None:
            job_id = kwargs["job_id"]
            record(f"openai_start:{job_id}")
            if job_id == "job-1":
                first_openai_started.set()
                self.assertTrue(release_first_openai.wait(timeout=5), "Timed out waiting to release OpenAI mock")
            Path(kwargs["output_file"]).write_text(f"OpenAI result for {job_id}", encoding="utf-8")
            callback = kwargs.get("on_event")
            if callback is not None:
                callback({"event": "rq_generation_finished"})
            record(f"openai_finish:{job_id}")

        local_openai_queue = OpenAIInferenceQueue(
            max_workers=1,
            max_retries=0,
            runner=fake_openai_runner,
            sleep=lambda _delay: None,
        )

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config.JOBS_DIR = root / "jobs"
                config.SUMMARY_XLSX_PATH = root / "summary.xlsx"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)

                pipeline.openai_inference_queue = local_openai_queue
                pipeline.page_count = lambda _pdf_path: 1
                pipeline.render_pdf_to_images = fake_render
                pipeline.discover_deepseek_model = lambda: "mock-deepseek"
                pipeline.run_deepseek_ocr = fake_ocr

                settings = JobSettings.from_form(
                    {
                        "rq_model_preset": "openai_gpt5_mini_high",
                        "rq_prompt_filename": "prompt_async.txt",
                        "rq_system_prompt": "Use the user-provided text.",
                    }
                )
                for job_id in ["job-1", "job-2"]:
                    job_root = jobs.create_job(job_id, f"{job_id}.pdf", settings)
                    (job_root / "input" / "uploaded.pdf").write_bytes(b"%PDF mock")

                pipeline.run_job("job-1", settings, defer_openai=True)
                self.assertTrue(first_openai_started.wait(timeout=5), "OpenAI mock did not start")

                pipeline.run_job("job-2", settings, defer_openai=True)
                with event_lock:
                    snapshot = list(events)
                self.assertIn("ocr_start:job-2", snapshot)
                self.assertNotIn("openai_finish:job-1", snapshot)

                release_first_openai.set()
                local_openai_queue.join()

                self.assertEqual(jobs.read_status("job-1")["status"], "complete")
                self.assertEqual(jobs.read_status("job-2")["status"], "complete")
                self.assertEqual(
                    (jobs.job_dir("job-1") / "outputs" / "rq_screening_output.md").read_text(encoding="utf-8"),
                    "OpenAI result for job-1",
                )
                self.assertEqual(
                    (jobs.job_dir("job-2") / "outputs" / "rq_screening_output.md").read_text(encoding="utf-8"),
                    "OpenAI result for job-2",
                )
        finally:
            release_first_openai.set()
            local_openai_queue.shutdown()
            pipeline.openai_inference_queue = original_queue
            pipeline.page_count = original_page_count
            pipeline.render_pdf_to_images = original_render
            pipeline.discover_deepseek_model = original_discover
            pipeline.run_deepseek_ocr = original_ocr
            config.JOBS_DIR = original_jobs_dir
            config.SUMMARY_XLSX_PATH = original_summary_path

    def test_openai_queue_retries_transient_errors(self) -> None:
        from app.services.openai_inference_queue import OpenAIInferenceJob, OpenAIInferenceQueue

        original_jobs_dir = config.JOBS_DIR
        attempts = 0
        delays: list[float] = []
        completions: list[str] = []
        completion_started_at: list[float] = []

        def flaky_runner(**kwargs) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("rate limit 429")
            Path(kwargs["output_file"]).write_text("ok", encoding="utf-8")

        def complete_stub(**kwargs) -> None:
            completions.append(kwargs["job_id"])
            completion_started_at.append(kwargs["started_at"])
            jobs.update_status(
                kwargs["job_id"],
                status="complete",
                stage="complete",
                message="done",
                progress=1.0,
                event={"event": "complete"},
            )

        retry_queue = OpenAIInferenceQueue(
            max_workers=1,
            max_retries=1,
            retry_base_seconds=0.01,
            runner=flaky_runner,
            completion_handler=complete_stub,
            sleep=delays.append,
            clock=lambda: 123.45,
        )
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config.JOBS_DIR = root / "jobs"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                settings = JobSettings.from_form(
                    {
                        "rq_model_preset": "openai_gpt5_mini_high",
                        "rq_prompt_filename": "prompt_retry.txt",
                        "rq_system_prompt": "Use the user-provided text.",
                    }
                )
                job_root = jobs.create_job("retry-job", "retry.pdf", settings)
                system_prompt = job_root / "outputs" / "rq_system_prompt.txt"
                user_prompt = job_root / "outputs" / "rq_user_prompt.txt"
                output = job_root / "outputs" / "rq_screening_output.md"
                pdf_path = job_root / "input" / "uploaded.pdf"
                system_prompt.write_text("system", encoding="utf-8")
                user_prompt.write_text("user text", encoding="utf-8")
                pdf_path.write_bytes(b"%PDF mock")

                self.assertTrue(
                    retry_queue.enqueue(
                        OpenAIInferenceJob(
                            job_id="retry-job",
                            settings=settings,
                            started_at=0.0,
                            prompt_filename="prompt_retry.txt",
                            prompt_source_path="",
                            system_prompt_file=system_prompt,
                            user_prompt_file=user_prompt,
                            output_file=output,
                            pdf_path=pdf_path,
                        )
                    )
                )
                retry_queue.join()
                self.assertEqual(attempts, 2)
                self.assertEqual(delays, [0.01])
                self.assertEqual(completions, ["retry-job"])
                self.assertEqual(completion_started_at, [123.45])
                self.assertEqual(jobs.read_status("retry-job")["status"], "complete")
        finally:
            retry_queue.shutdown()
            config.JOBS_DIR = original_jobs_dir


class RerunEndpointTests(unittest.TestCase):
    def test_upload_display_name_keeps_folder_path_only_in_metadata(self) -> None:
        from app.main import source_folder_from_relative_path, upload_display_filename

        class Upload:
            filename = "PDFs included/122710267.pdf"

        self.assertEqual(upload_display_filename(Upload()), "122710267.pdf")
        self.assertEqual(source_folder_from_relative_path("PDFs included/122710267.pdf"), "PDFs included")
        self.assertEqual(source_folder_from_relative_path("122710267.pdf"), "")

    def test_rerun_with_different_identity_returns_new_job_record(self) -> None:
        from fastapi.testclient import TestClient
        from app.main import app, job_queue

        original_data_dir = config.DATA_DIR
        original_jobs_dir = config.JOBS_DIR
        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config.DATA_DIR = root / "data"
                config.JOBS_DIR = config.DATA_DIR / "jobs"
                config.PROJECTS_DIR = config.DATA_DIR / "projects"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                job_queue.pause()
                from app.services import projects

                project_id = projects.get_default_project()["project_id"]

                source_settings = JobSettings.from_form(
                    {"rq_prompt_filename": "prompt1.txt", "rq_model_preset": "openai_gpt5_mini_high"}
                )
                source_root = jobs.create_job("source", "same-file.pdf", source_settings, project_id=project_id)
                (source_root / "input" / "uploaded.pdf").write_bytes(b"%PDF source")
                (source_root / "outputs" / "merged_full_text.txt").write_text(
                    "merged OCR text long enough to reuse",
                    encoding="utf-8",
                )
                (source_root / "ocr_text" / "page_0001.md").write_text("page OCR", encoding="utf-8")
                jobs.update_metadata(
                    source_root,
                    rq_prompt_filename="prompt1.txt",
                    rq_screening_model="gpt-5-mini",
                    number_of_pages=1,
                )
                jobs.update_status("source", status="complete", stage="complete", message="done", progress=1.0)

                response = TestClient(app).post(
                    "/api/jobs/source/rerun",
                    data={
                        "rq_model_preset": "qwen35_9b_8bit_reasoning",
                        "rq_prompt_filename": "prompt2.txt",
                        "rq_system_prompt": "Use the user-provided text.",
                        "project_id": project_id,
                    },
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["created_new_job"])
                self.assertEqual(payload["source_job_id"], "source")
                self.assertNotEqual(payload["job"]["job_id"], "source")
                child_metadata = payload["job"]["metadata"]
                self.assertEqual(child_metadata["rerun_created_from_job_id"], "source")
                self.assertEqual(child_metadata["rq_prompt_filename"], "prompt2.txt")
                self.assertEqual(child_metadata["rq_screening_model"], config.RQ_SCREENING_MODEL)
                self.assertEqual(child_metadata["rq_max_tokens"], config.RQ_SCREENING_MAX_TOKENS)
                self.assertTrue(child_metadata["rq_enable_thinking"])

                job_queue.clean_queued(project_id=project_id)
                job_queue.resume(project_id=project_id)
        finally:
            config.DATA_DIR = original_data_dir
            config.JOBS_DIR = original_jobs_dir
            config.PROJECTS_DIR = original_projects_dir


class TextWorkbookTests(unittest.TestCase):
    def test_text_workbook_freezes_mapping_duplicates_sheets_and_exports_full_rows(self) -> None:
        from fastapi.testclient import TestClient
        from openpyxl import load_workbook
        from starlette.datastructures import UploadFile

        from app.main import app
        from app.services import projects, text_extraction, text_index

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Text workbook", "", "text")
                upload = UploadFile(
                    filename="records.csv",
                    file=BytesIO(b"study_id,title,abstract,authors\nS1,First title,First abstract,A One\nS2,Second title,,B Two\n"),
                )
                created = text_extraction.create_text_source(
                    project_id=str(project["project_id"]),
                    upload_file=upload,
                    column_mappings=[
                        {"column_name": "title", "prompt_label": "Title"},
                        {"column_name": "abstract", "prompt_label": "Abstract"},
                    ],
                    study_id_column="study_id",
                    initial_settings=JobSettings(rq_prompt_filename="screening.txt", rq_system_prompt="Screen each record."),
                )

                self.assertEqual(created["source"]["row_count"], 2)
                self.assertEqual([mapping["column_name"] for mapping in created["source"]["column_mappings"]], ["title", "abstract"])
                first_sheet = created["sheet"]
                self.assertTrue(
                    text_index.source_index_ready(
                        str(project["project_id"]),
                        str(created["source"]["source_id"]),
                        2,
                    )
                )
                rows = text_extraction.list_text_jobs(
                    project_id=str(project["project_id"]),
                    sheet_id=str(first_sheet["sheet_id"]),
                )
                self.assertEqual(rows["total"], 2)
                self.assertTrue(rows["index_ready"])
                self.assertEqual(rows["items"][0]["status"], "not_run")
                self.assertEqual(rows["items"][0]["mapped_cells"], {"title": "First title", "abstract": "First abstract"})
                text_index.upsert_job(
                    str(project["project_id"]),
                    {
                        "job_id": "indexed-row-job",
                        "sheet_id": str(first_sheet["sheet_id"]),
                        "source_id": str(created["source"]["source_id"]),
                        "source_row_index": 0,
                        "model": "test-model",
                        "prompt": "screening.txt",
                        "status": "queued",
                    },
                )
                self.assertTrue(text_index.has_job_index(str(project["project_id"])))
                self.assertEqual(text_index.queued_job_refs(str(project["project_id"])), [(0, "indexed-row-job")])
                self.assertTrue(text_index.update_result_preview(str(project["project_id"]), "indexed-row-job", "Preview text"))

                duplicate = text_extraction.duplicate_text_sheet(str(project["project_id"]), str(first_sheet["sheet_id"]))
                self.assertEqual(duplicate["name"], "Sheet 1 (1)")
                self.assertEqual(
                    [sheet["name"] for sheet in text_extraction.list_text_sheets(str(project["project_id"]))],
                    ["Sheet 1", "Sheet 1 (1)"],
                )
                self.assertEqual(duplicate["rq_system_prompt"], "Screen each record.")
                self.assertEqual(text_extraction.text_job_records(str(project["project_id"]), sheet_id=str(duplicate["sheet_id"])), [])

                with self.assertRaises(ValueError):
                    text_extraction.create_text_source(
                        project_id=str(project["project_id"]),
                        upload_file=UploadFile(filename="replacement.csv", file=BytesIO(b"title\nReplacement\n")),
                        column_mappings=[{"column_name": "title", "prompt_label": "Title"}],
                    )

                export_path = text_extraction.export_text_results(str(project["project_id"]))
                workbook = load_workbook(export_path, read_only=True, data_only=True)
                self.assertEqual(workbook.sheetnames, ["Sheet 1", "Sheet 1 (1)"])
                worksheet = workbook["Sheet 1"]
                headers = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
                self.assertEqual(headers[:4], ["study_id", "title", "abstract", "authors"])
                self.assertEqual(headers[-1], "cerebro_output")
                self.assertEqual(worksheet.max_row - 1, 2)
                self.assertEqual(worksheet.cell(row=2, column=headers.index("cerebro_status") + 1).value, "Not run")
                workbook.close()

                worksheet_path = text_extraction.export_text_worksheet(
                    str(project["project_id"]),
                    str(first_sheet["sheet_id"]),
                )
                selected_workbook = load_workbook(worksheet_path, read_only=True, data_only=True)
                self.assertEqual(selected_workbook.sheetnames, ["Sheet 1"])
                selected_worksheet = selected_workbook["Sheet 1"]
                selected_headers = [cell.value for cell in next(selected_worksheet.iter_rows(min_row=1, max_row=1))]
                self.assertEqual(selected_headers[:4], ["study_id", "title", "abstract", "authors"])
                self.assertEqual(selected_headers[-1], "cerebro_output")
                self.assertEqual(selected_worksheet.max_row - 1, 2)
                selected_workbook.close()

                client = TestClient(app)
                page_response = client.get(f"/text?project_id={project['project_id']}")
                self.assertEqual(page_response.status_code, 200)
                self.assertIn('id="textWorksheetExportButton"', page_response.text)
                worksheet_response = client.get(
                    f"/api/text/sheets/{first_sheet['sheet_id']}/export?project_id={project['project_id']}"
                )
                self.assertEqual(worksheet_response.status_code, 200)
                self.assertIn("sheet-1", worksheet_response.headers["content-disposition"])
                route_workbook = load_workbook(BytesIO(worksheet_response.content), read_only=True, data_only=True)
                self.assertEqual(route_workbook.sheetnames, ["Sheet 1"])
                route_workbook.close()
        finally:
            config.PROJECTS_DIR = original_projects_dir


class StructuredExtractionTests(unittest.TestCase):
    def test_project_type_normalizes_structured_pdf(self) -> None:
        from app.services import projects

        self.assertEqual(projects.normalize_extraction_type("pdf_structured"), "pdf_structured")
        self.assertEqual(projects.normalize_extraction_type("structured-pdf"), "pdf_structured")
        self.assertEqual(projects.normalize_extraction_type("structured_pdf_extraction"), "pdf_structured")

    def test_legacy_structured_sheets_migrate_to_a_default_workbook_without_moving_data(self) -> None:
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Legacy structured", "", "pdf_structured")
                project_id = str(project["project_id"])
                legacy_root = projects.project_root(project_id) / structured_extraction.STRUCTURED_SHEETS_DIRNAME / "legacy-sheet"
                legacy_root.mkdir(parents=True, exist_ok=True)
                jobs.write_json(
                    legacy_root / structured_extraction.SHEET_FILENAME,
                    {
                        "sheet_id": "legacy-sheet",
                        "project_id": project_id,
                        "name": "Legacy sheet",
                        "context": "Existing context.",
                        "row_unit": "Existing preferences.",
                        "columns": [{"column_name": "Finding", "question": "State the finding.", "rules": ""}],
                        "sheet_order": 0,
                        "created_at": "2026-09-01T00:00:00+00:00",
                    },
                )
                (legacy_root / structured_extraction.ROWS_JSONL_FILENAME).write_text(
                    json.dumps({"job_id": "legacy-job", "source_pdf": "legacy.pdf", "cells": {"Finding": "Present"}}) + "\n",
                    encoding="utf-8",
                )
                (legacy_root / structured_extraction.ERRORS_JSONL_FILENAME).write_text("", encoding="utf-8")

                workbooks = structured_extraction.list_workbooks(project_id)
                self.assertEqual([workbook["name"] for workbook in workbooks], ["Workbook 1"])
                migrated_sheet = structured_extraction.get_sheet(project_id, "legacy-sheet")
                self.assertEqual(migrated_sheet["workbook_id"], workbooks[0]["workbook_id"])
                self.assertTrue((legacy_root / structured_extraction.ROWS_JSONL_FILENAME).exists())
                self.assertEqual(
                    structured_extraction.list_rows(
                        project_id=project_id,
                        workbook_id=str(workbooks[0]["workbook_id"]),
                        sheet_id="legacy-sheet",
                    )["total"],
                    1,
                )
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_project_workbooks_scope_sheets_jobs_and_export(self) -> None:
        from openpyxl import load_workbook

        from app.models import JobSettings
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Workbook scope", "", "pdf_structured")
                project_id = str(project["project_id"])
                first_workbook = structured_extraction.get_default_workbook(project_id)
                first_sheet = structured_extraction.create_sheet(
                    project_id=project_id,
                    workbook_id=str(first_workbook["workbook_id"]),
                    name="First sheet",
                    columns=[{"column_name": "First", "question": "First question.", "rules": ""}],
                )
                second_workbook = structured_extraction.create_workbook(project_id=project_id, name="Comparison")
                second_sheet = structured_extraction.create_sheet(
                    project_id=project_id,
                    workbook_id=str(second_workbook["workbook_id"]),
                    name="Second sheet",
                    columns=[{"column_name": "Second", "question": "Second question.", "rules": ""}],
                )
                self.assertEqual(
                    [sheet["name"] for sheet in structured_extraction.list_sheets(project_id, str(first_workbook["workbook_id"]))],
                    ["First sheet"],
                )
                self.assertEqual(
                    [sheet["name"] for sheet in structured_extraction.list_sheets(project_id, str(second_workbook["workbook_id"]))],
                    ["Second sheet"],
                )

                root = jobs.create_job("comparison-job", "comparison.pdf", JobSettings(), project_id=project_id)
                jobs.update_metadata(
                    root,
                    extraction_type="pdf_structured",
                    structured_workbook_id=second_workbook["workbook_id"],
                    structured_sheet_id=second_sheet["sheet_id"],
                )
                self.assertEqual(
                    structured_extraction.list_structured_jobs_window(
                        project_id,
                        workbook_id=str(first_workbook["workbook_id"]),
                    )["total"],
                    0,
                )
                self.assertEqual(
                    structured_extraction.list_structured_jobs_window(
                        project_id,
                        workbook_id=str(second_workbook["workbook_id"]),
                    )["total"],
                    1,
                )

                structured_extraction.replace_job_sheet_records(
                    project_id,
                    str(second_sheet["sheet_id"]),
                    "comparison-job",
                    [{"job_id": "comparison-job", "source_pdf": "comparison.pdf", "cells": {"Second": "Value"}}],
                    [],
                )
                export_path = structured_extraction.export_structured_workbook(
                    project_id,
                    workbook_id=str(second_workbook["workbook_id"]),
                )
                exported = load_workbook(export_path, read_only=True)
                self.assertEqual(exported.sheetnames, ["Second sheet"])
                exported.close()

                duplicated = structured_extraction.duplicate_project_workbook(
                    project_id,
                    str(second_workbook["workbook_id"]),
                )
                self.assertEqual([sheet["name"] for sheet in duplicated["sheets"]], ["Second sheet"])
                self.assertFalse(duplicated["sheets"][0]["is_locked"])
                self.assertEqual(
                    structured_extraction.list_rows(
                        project_id=project_id,
                        workbook_id=str(duplicated["workbook"]["workbook_id"]),
                        sheet_id=str(duplicated["sheets"][0]["sheet_id"]),
                    )["total"],
                    0,
                )
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_structured_pdf_library_copies_complete_source_bundles_for_reuse(self) -> None:
        from app.services import projects, structured_sources

        class Upload:
            def __init__(self, filename: str, payload: bytes) -> None:
                self.filename = filename
                self.file = BytesIO(payload)

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Source library", "", "pdf_structured")
                project_id = str(project["project_id"])
                created = structured_sources.create_sources(
                    project_id,
                    [
                        {
                            "upload": Upload("article.pdf", b"%PDF primary"),
                            "relative_path": "Studies/article.pdf",
                            "attachments": [
                                {
                                    "upload": Upload("article supplement.csv", b"record,value\nA,1\n"),
                                    "relative_path": "Studies/article supplement.csv",
                                }
                            ],
                        }
                    ],
                )
                self.assertEqual(len(created["created"]), 1)
                source = created["created"][0]
                self.assertEqual(source["supporting_file_count"], 1)
                target = jobs.create_job("library-job", "article.pdf", JobSettings(), project_id=project_id)
                metadata = structured_sources.copy_source_to_job(project_id, str(source["source_id"]), target)
                jobs.update_metadata(target, **metadata)
                records = jobs.source_file_records(target)
                self.assertEqual([record["filename"] for record in records], ["article.pdf", "article supplement.csv"])
                self.assertEqual(records[1]["path"].read_bytes(), b"record,value\nA,1\n")
                self.assertEqual(metadata["source_library_id"], source["source_id"])
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_structured_source_routes_queue_library_jobs_in_the_selected_workbook(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app, job_queue
        from app.services import jobs as job_service
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        original_enqueue = job_queue.enqueue
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Library route", "", "pdf_structured")
                project_id = str(project["project_id"])
                workbook = structured_extraction.get_default_workbook(project_id)
                sheet = structured_extraction.create_sheet(
                    project_id=project_id,
                    workbook_id=str(workbook["workbook_id"]),
                    name="Route sheet",
                    columns=[{"column_name": "Finding", "question": "State the finding.", "rules": ""}],
                )
                job_queue.enqueue = lambda _job_id, _settings, project_id=None: None
                client = TestClient(app)
                source_response = client.post(
                    "/api/structured/sources",
                    data={
                        "project_id": project_id,
                        "pdf_relative_paths": "Route/article.pdf",
                        "attachment_primary_indices": "0",
                        "attachment_relative_paths": "Route/article supplement.csv",
                    },
                    files=[
                        ("pdfs", ("article.pdf", b"%PDF primary", "application/pdf")),
                        ("attachments", ("article supplement.csv", b"record,value\nA,1\n", "text/csv")),
                    ],
                )
                self.assertEqual(source_response.status_code, 200)
                source_id = source_response.json()["created"][0]["source_id"]

                job_response = client.post(
                    "/api/structured/jobs",
                    data={
                        "project_id": project_id,
                        "workbook_id": workbook["workbook_id"],
                        "sheet_id": sheet["sheet_id"],
                        "source_ids": json.dumps([source_id]),
                        "rq_model_preset": "qwen35_9b_8bit_reasoning",
                    },
                )
                self.assertEqual(job_response.status_code, 200)
                self.assertEqual(job_response.json()["count"], 1)
                self.assertEqual(job_response.json()["jobs"][0]["workbook_id"], workbook["workbook_id"])
                job_id = job_response.json()["job_id"]
                metadata = job_service.read_metadata(job_service.job_dir(job_id, project_id))
                self.assertEqual(metadata["structured_workbook_id"], workbook["workbook_id"])
                self.assertEqual(metadata["source_library_id"], source_id)
                self.assertEqual(len(job_service.source_file_records(job_service.job_dir(job_id, project_id))), 2)
        finally:
            job_queue.enqueue = original_enqueue
            config.PROJECTS_DIR = original_projects_dir

    def test_sheet_creation_loading_and_rows_are_project_scoped(self) -> None:
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Structured A", "", "pdf_structured")
                other_project = projects.create_project("Structured B", "", "pdf_structured")
                sheet = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Species characteristics",
                    context="Wild animal review",
                    row_unit="One row per species.",
                    columns=[
                        {
                            "column_name": "SpeciesLatinArticle",
                            "question": "State the scientific name.",
                            "rules": "Enter NA if absent.",
                        }
                    ],
                )

                self.assertEqual(sheet["project_id"], project["project_id"])
                self.assertIn("compiled_prompt", sheet)
                self.assertEqual(len(structured_extraction.list_sheets(str(project["project_id"]))), 1)
                self.assertEqual(structured_extraction.list_sheets(str(other_project["project_id"])), [])

                row = {
                    "row_id": "row-1",
                    "sheet_id": sheet["sheet_id"],
                    "project_id": project["project_id"],
                    "job_id": "job-1",
                    "source_pdf": "paper.pdf",
                    "extracted_at": "2026-06-19T00:00:00Z",
                    "model": "gpt-5.4-mini",
                    "parse_status": "parsed",
                    "parse_error": "",
                    "cells": {"SpeciesLatinArticle": "Ailuropoda melanoleuca"},
                }
                structured_extraction.replace_job_sheet_records(
                    str(project["project_id"]),
                    str(sheet["sheet_id"]),
                    "job-1",
                    [row],
                    [],
                )

                payload = structured_extraction.list_rows(
                    project_id=str(project["project_id"]),
                    sheet_id=str(sheet["sheet_id"]),
                    search="Ailuropoda",
                )
                self.assertEqual(payload["total"], 1)

                other_sheet = structured_extraction.create_sheet(
                    project_id=str(other_project["project_id"]),
                    name="Other sheet",
                    row_unit="One row per intervention.",
                    columns=[{"column_name": "Intervention", "question": "State the intervention.", "rules": ""}],
                )
                other_payload = structured_extraction.list_rows(
                    project_id=str(other_project["project_id"]),
                    sheet_id=str(other_sheet["sheet_id"]),
                )
                self.assertEqual(other_payload["total"], 0)
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_concurrent_job_completions_preserve_every_jobs_rows(self) -> None:
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        original_read_jsonl = structured_extraction.read_jsonl
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Concurrent structured", "", "pdf_structured")
                project_id = str(project["project_id"])
                sheet = structured_extraction.create_sheet(
                    project_id=project_id,
                    name="Concurrent sheet",
                    columns=[{"column_name": "Finding", "question": "State the finding.", "rules": ""}],
                )
                sheet_id = str(sheet["sheet_id"])
                start = threading.Barrier(3)
                failures: list[BaseException] = []

                def delayed_read_jsonl(path: Path) -> list[dict]:
                    records = original_read_jsonl(path)
                    if path.name == structured_extraction.ROWS_JSONL_FILENAME:
                        time.sleep(0.05)
                    return records

                def complete(job_id: str) -> None:
                    try:
                        start.wait()
                        structured_extraction.replace_job_sheet_records(
                            project_id,
                            sheet_id,
                            job_id,
                            [{"row_id": f"row-{job_id}", "job_id": job_id, "cells": {"Finding": job_id}}],
                            [],
                        )
                    except BaseException as exc:
                        failures.append(exc)

                structured_extraction.read_jsonl = delayed_read_jsonl
                threads = [threading.Thread(target=complete, args=(job_id,)) for job_id in ("job-a", "job-b")]
                for thread in threads:
                    thread.start()
                start.wait()
                for thread in threads:
                    thread.join(timeout=5)

                self.assertFalse(failures)
                self.assertTrue(all(not thread.is_alive() for thread in threads))
                rows = structured_extraction.read_sheet_rows(project_id, sheet_id)
                self.assertEqual({row["job_id"] for row in rows}, {"job-a", "job-b"})
        finally:
            structured_extraction.read_jsonl = original_read_jsonl
            config.PROJECTS_DIR = original_projects_dir

    def test_structured_sheet_drafts_load_before_questions_are_complete(self) -> None:
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Structured Draft", "", "pdf_structured")
                sheet = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Sheet 1",
                    columns=[{"column_name": "Column1", "question": "", "rules": ""}],
                )

                self.assertFalse(sheet["schema_ready"])
                self.assertIn("missing a question", sheet["schema_error"])
                self.assertEqual(len(structured_extraction.list_sheets(str(project["project_id"]))), 1)
                with self.assertRaises(ValueError):
                    structured_extraction.compile_sheet_prompt(sheet)

                saved = structured_extraction.update_sheet(
                    project_id=str(project["project_id"]),
                    sheet_id=str(sheet["sheet_id"]),
                    name="Sheet 1",
                    context="",
                    row_unit="",
                    columns=[{"column_name": "Column1", "question": "Extract the value.", "rules": ""}],
                )
                self.assertTrue(saved["schema_ready"])
                self.assertIn("Other preferences:", saved["compiled_prompt"])
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_column_block_parser_compiler_and_tsv_parser(self) -> None:
        from app.services import structured_extraction

        columns = structured_extraction.parse_column_blocks(
            """
Column name ### SpeciesLatinArticle

Question ### State the scientific name.

Rules ###

* Enter NA if absent.

---

Column name ### SpeciesCommonArticle

Question ### State the common name.

Rules ###

* Use the article wording.
"""
        )
        self.assertEqual([column["column_name"] for column in columns], ["SpeciesLatinArticle", "SpeciesCommonArticle"])
        prompt = structured_extraction.compile_sheet_prompt(
            {
                "context": "General context.",
                "row_unit": "One row per species.",
                "columns": columns,
            }
        )
        self.assertIn("SpeciesLatinArticle\tSpeciesCommonArticle", prompt)
        self.assertIn("Do not include a Markdown table", prompt)

        rows = structured_extraction.parse_tsv_output(
            "SpeciesLatinArticle\tSpeciesCommonArticle\nAiluropoda melanoleuca\tgiant panda\nMartes foina\t",
            ["SpeciesLatinArticle", "SpeciesCommonArticle"],
        )
        self.assertEqual(rows[0]["SpeciesCommonArticle"], "giant panda")
        self.assertEqual(rows[1]["SpeciesCommonArticle"], "")

    def test_sheet_import_parser_accepts_full_sheet_and_detects_conflicts(self) -> None:
        from app.services import structured_extraction

        payload = structured_extraction.parse_sheet_import(
            """
Sheet name ### Species characteristics

Context ###
Review of captive wild animal articles.

More information / other preferences ###
One row per eligible animal species.

Columns ###

Column name ### AnimalWelfare

Question ### State the welfare outcome.

Rules ###
Enter NA if absent.

---

Column name ### AnimalInformation

Question ### State the animal information.

Rules ###
Use article wording.
""",
            current_sheet={
                "name": "Existing sheet",
                "context": "Existing context.",
                "row_unit": "",
                "columns": [{"column_name": "AnimalWelfare", "question": "Old question", "rules": ""}],
            },
        )

        self.assertEqual(payload["fields"]["name"], "Species characteristics")
        self.assertEqual(payload["fields"]["context"], "Review of captive wild animal articles.")
        self.assertEqual(payload["fields"]["row_unit"], "One row per eligible animal species.")
        self.assertEqual([column["column_name"] for column in payload["columns"]], ["AnimalWelfare", "AnimalInformation"])
        self.assertTrue(payload["has_conflicts"])
        self.assertEqual(payload["conflicts"]["fields"], ["Context"])
        self.assertEqual(payload["conflicts"]["columns"], ["AnimalWelfare"])

    def test_sheet_import_text_export_matches_guide_format(self) -> None:
        from app.services import structured_extraction

        text = structured_extraction.format_sheet_import_text(
            {
                "name": "Species characteristics",
                "context": "Review of captive wild animal articles.",
                "row_unit": "One row per eligible animal species.",
                "columns": [
                    {
                        "column_name": "SpeciesLatinArticle",
                        "question": "State the scientific name.",
                        "rules": "* Enter NA if absent.",
                    },
                    {
                        "column_name": "SpeciesCommonArticle",
                        "question": "State the common name.",
                        "rules": "* Use article wording.",
                    },
                ],
            }
        )

        self.assertIn("Sheet name ### Species characteristics", text)
        self.assertIn("Context ###\nReview of captive wild animal articles.", text)
        self.assertIn("More information / other preferences ###\nOne row per eligible animal species.", text)
        self.assertIn("Columns ###\n\nColumn name ### SpeciesLatinArticle", text)
        self.assertIn("\n\n---\n\nColumn name ### SpeciesCommonArticle", text)

        payload = structured_extraction.parse_sheet_import(text)
        self.assertEqual(payload["fields"]["name"], "Species characteristics")
        self.assertEqual([column["column_name"] for column in payload["columns"]], ["SpeciesLatinArticle", "SpeciesCommonArticle"])

    def test_workbook_import_text_exports_every_sheet_in_order_without_compiled_prompt(self) -> None:
        from app.services import structured_extraction

        text = structured_extraction.format_workbook_import_text(
            [
                {
                    "name": "First sheet",
                    "context": "First context.",
                    "row_unit": "First preferences.",
                    "columns": [{"column_name": "FirstField", "question": "First question?", "rules": "First rules."}],
                },
                {
                    "name": "Second sheet",
                    "context": "Second context.",
                    "row_unit": "Second preferences.",
                    "columns": [{"column_name": "SecondField", "question": "Second question?", "rules": "Second rules."}],
                },
            ]
        )

        self.assertLess(text.index("Sheet name ### First sheet"), text.index("Sheet name ### Second sheet"))
        self.assertEqual(text.count(structured_extraction.WORKBOOK_IMPORT_TEXT_SEPARATOR.strip()), 1)
        self.assertIn("Column name ### FirstField", text)
        self.assertIn("Column name ### SecondField", text)
        self.assertNotIn("Required output format", text)
        self.assertNotIn("Return the results as tab-separated values", text)

    def test_sheet_import_parser_accepts_columns_only_and_validates(self) -> None:
        from app.services import structured_extraction

        payload = structured_extraction.parse_sheet_import(
            """
Column name ### SpeciesLatinArticle

Question ### State the scientific name.

Rules ###
Enter NA if absent.
""",
            current_sheet={"columns": []},
        )
        self.assertEqual(payload["fields"], {})
        self.assertEqual(payload["columns"][0]["column_name"], "SpeciesLatinArticle")
        self.assertFalse(payload["has_conflicts"])

        with self.assertRaises(ValueError):
            structured_extraction.parse_sheet_import(
                """
Column name ### SpeciesLatinArticle

Rules ###
Missing a question.
"""
            )

        with self.assertRaises(ValueError):
            structured_extraction.parse_sheet_import(
                """
Column name ### SpeciesLatinArticle

Question ### First question.

Rules ###

---

Column name ### SpeciesLatinArticle

Question ### Duplicate question.

Rules ###
"""
            )

    def test_tsv_parser_header_only_and_errors(self) -> None:
        from app.services import structured_extraction

        self.assertEqual(structured_extraction.parse_tsv_output("A\tB", ["A", "B"]), [])
        with self.assertRaises(structured_extraction.StructuredParseError):
            structured_extraction.parse_tsv_output("B\tA\n1\t2", ["A", "B"])
        with self.assertRaises(structured_extraction.StructuredParseError):
            structured_extraction.parse_tsv_output("A\tB\n1\t2\t3", ["A", "B"])
        with self.assertRaises(structured_extraction.StructuredParseError):
            structured_extraction.parse_tsv_output("| A | B |\n| 1 | 2 |", ["A", "B"])

    def test_structured_export_smoke_test(self) -> None:
        from openpyxl import load_workbook

        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Structured Export", "", "pdf_structured")
                sheet = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Species characteristics",
                    row_unit="One row per species.",
                    columns=[{"column_name": "SpeciesLatinArticle", "question": "State the scientific name.", "rules": ""}],
                )
                structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Study details",
                    columns=[{"column_name": "Country", "question": "State the country.", "rules": ""}],
                )
                structured_extraction.replace_job_sheet_records(
                    str(project["project_id"]),
                    str(sheet["sheet_id"]),
                    "job-1",
                    [
                        {
                            "row_id": "row-1",
                            "sheet_id": sheet["sheet_id"],
                            "project_id": project["project_id"],
                            "job_id": "job-1",
                            "source_pdf": "paper.pdf",
                            "extracted_at": "2026-06-19T00:00:00Z",
                            "model": "gpt-5.4-mini",
                            "parse_status": "parsed",
                            "parse_error": "",
                            "cells": {"SpeciesLatinArticle": "Ailuropoda melanoleuca"},
                        }
                    ],
                    [],
                )

                export_path = structured_extraction.export_structured_workbook(str(project["project_id"]))
                workbook = load_workbook(export_path)
                self.assertEqual(workbook.sheetnames, ["Species characteristics", "Study details"])
                worksheet = workbook["Species characteristics"]
                headers = [worksheet.cell(row=1, column=index).value for index in range(1, 9)]
                self.assertEqual(
                    headers,
                    [
                        "source_pdf",
                        "job_id",
                        "extracted_at",
                        "model",
                        "parse_status",
                        "parse_date",
                        "parse_error",
                        "SpeciesLatinArticle",
                    ],
                )
                self.assertEqual(worksheet.cell(row=2, column=1).value, "paper.pdf")
                self.assertEqual(worksheet.cell(row=2, column=8).value, "Ailuropoda melanoleuca")

                worksheet_path = structured_extraction.export_structured_worksheet(
                    str(project["project_id"]),
                    str(sheet["sheet_id"]),
                )
                selected_workbook = load_workbook(worksheet_path)
                self.assertEqual(selected_workbook.sheetnames, ["Species characteristics"])
                selected_worksheet = selected_workbook["Species characteristics"]
                self.assertEqual(selected_worksheet.cell(row=2, column=1).value, "paper.pdf")
                self.assertEqual(selected_worksheet.cell(row=2, column=8).value, "Ailuropoda melanoleuca")
                self.assertIn("species-characteristics", worksheet_path.name)
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_structured_rows_include_live_job_placeholders(self) -> None:
        from app.models import JobSettings
        from app.services import jobs, projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Structured Live Rows", "", "pdf_structured")
                sheet = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Species characteristics",
                    columns=[{"column_name": "SpeciesLatinArticle", "question": "State the scientific name.", "rules": ""}],
                )
                root = jobs.create_job("live-job", "live.pdf", JobSettings(), project_id=str(project["project_id"]))
                jobs.update_metadata(
                    root,
                    extraction_type="pdf_structured",
                    structured_sheet_id=sheet["sheet_id"],
                    rq_screening_model="gpt-5.4-mini",
                    source_relative_path="Pilots/live.pdf",
                )

                payload = structured_extraction.list_rows(
                    project_id=str(project["project_id"]),
                    sheet_id=str(sheet["sheet_id"]),
                )
                self.assertEqual(payload["total"], 1)
                self.assertEqual(payload["items"][0]["source_pdf"], "live.pdf")
                self.assertEqual(payload["items"][0]["parse_status"], "queued")
                self.assertEqual(payload["items"][0]["parse_date"], "")

                jobs.update_metadata(root, completed_at="2026-06-22T14:30:00Z", structured_parse_status="parsed")
                jobs.update_status(
                    "live-job",
                    status="complete",
                    stage="complete",
                    message="Done",
                    progress=1,
                    project_id=str(project["project_id"]),
                )
                updated = structured_extraction.list_rows(
                    project_id=str(project["project_id"]),
                    sheet_id=str(sheet["sheet_id"]),
                )
                self.assertEqual(updated["items"][0]["parse_status"], "parsed")
                self.assertEqual(updated["items"][0]["parse_date"], "2026-06-22T14:30:00Z")
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_structured_sheets_keep_creation_order_and_duplicate_next_to_source(self) -> None:
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Structured order", "", "pdf_structured")
                first = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Zeta",
                    columns=[{"column_name": "Column1", "question": "", "rules": ""}],
                )
                second = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Alpha",
                    columns=[{"column_name": "Column1", "question": "", "rules": ""}],
                )
                structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Middle",
                    columns=[{"column_name": "Column1", "question": "", "rules": ""}],
                )
                structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Zeta",
                    columns=[{"column_name": "Column1", "question": "", "rules": ""}],
                )

                self.assertEqual(
                    [sheet["name"] for sheet in structured_extraction.list_sheets(str(project["project_id"]))],
                    ["Zeta", "Alpha", "Middle", "Zeta (1)"],
                )

                duplicate = structured_extraction.duplicate_sheet(str(project["project_id"]), str(second["sheet_id"]))
                self.assertEqual(duplicate["name"], "Alpha (1)")
                self.assertEqual(
                    [sheet["name"] for sheet in structured_extraction.list_sheets(str(project["project_id"]))],
                    ["Zeta", "Alpha", "Alpha (1)", "Middle", "Zeta (1)"],
                )

                duplicate_again = structured_extraction.duplicate_sheet(str(project["project_id"]), str(duplicate["sheet_id"]))
                self.assertEqual(duplicate_again["name"], "Alpha (2)")
                self.assertEqual(
                    [sheet["name"] for sheet in structured_extraction.list_sheets(str(project["project_id"]))],
                    ["Zeta", "Alpha", "Alpha (1)", "Alpha (2)", "Middle", "Zeta (1)"],
                )
                self.assertEqual(first["name"], "Zeta")
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_structured_workbook_duplicate_copies_selected_schemas_without_data(self) -> None:
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Workbook", "Source description.", "pdf_structured")
                projects.create_project("Workbook (1)", "Existing copy.", "pdf_structured")
                first = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="First",
                    context="First context.",
                    row_unit="First preferences.",
                    columns=[{"column_name": "FirstValue", "question": "Extract first.", "rules": "Rule one."}],
                )
                second = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Second",
                    context="Second context.",
                    columns=[{"column_name": "SecondValue", "question": "Extract second.", "rules": ""}],
                )
                third = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Third",
                    context="Third context.",
                    columns=[{"column_name": "ThirdValue", "question": "Extract third.", "rules": "Rule three."}],
                )
                structured_extraction.replace_job_sheet_records(
                    str(project["project_id"]),
                    str(first["sheet_id"]),
                    "source-job",
                    [{"job_id": "source-job", "source_pdf": "source.pdf", "cells": {"FirstValue": "value"}}],
                    [{"job_id": "source-error", "source_pdf": "failed.pdf", "parse_error": "failed", "cells": {}}],
                )
                structured_extraction.lock_sheet_for_first_run(str(project["project_id"]), str(first["sheet_id"]), "source-job")

                duplicated = structured_extraction.duplicate_workbook(
                    str(project["project_id"]),
                    [str(third["sheet_id"]), str(first["sheet_id"])],
                )
                copied_project = duplicated["project"]
                copied_sheets = duplicated["sheets"]

                self.assertEqual(copied_project["name"], "Workbook (2)")
                self.assertEqual(copied_project["description"], "Source description.")
                self.assertEqual(copied_project["extraction_type"], "pdf_structured")
                self.assertEqual(
                    copied_project["dashboard_path"],
                    f"/structured-pdf?project_id={copied_project['project_id']}",
                )
                self.assertEqual([sheet["name"] for sheet in copied_sheets], ["First", "Third"])
                self.assertEqual(copied_sheets[0]["context"], "First context.")
                self.assertEqual(copied_sheets[0]["row_unit"], "First preferences.")
                self.assertEqual(copied_sheets[0]["columns"][0]["rules"], "Rule one.")
                self.assertTrue(all(not sheet["is_locked"] for sheet in copied_sheets))
                self.assertEqual(
                    structured_extraction.list_rows(
                        project_id=str(copied_project["project_id"]),
                        sheet_id=str(copied_sheets[0]["sheet_id"]),
                    )["total"],
                    0,
                )
                self.assertEqual(list(projects.get_project_jobs_dir(str(copied_project["project_id"])).iterdir()), [])
                self.assertNotIn(str(second["sheet_id"]), {str(sheet["sheet_id"]) for sheet in copied_sheets})
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_structured_sheet_locks_and_duplicates_without_rows(self) -> None:
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Structured Lock", "", "pdf_structured")
                sheet = structured_extraction.create_sheet(
                    project_id=str(project["project_id"]),
                    name="Species characteristics",
                    context="Original context.",
                    row_unit="One row per species.",
                    columns=[{"column_name": "SpeciesLatinArticle", "question": "State the scientific name.", "rules": ""}],
                )
                structured_extraction.replace_job_sheet_records(
                    str(project["project_id"]),
                    str(sheet["sheet_id"]),
                    "job-1",
                    [
                        {
                            "row_id": "row-1",
                            "sheet_id": sheet["sheet_id"],
                            "project_id": project["project_id"],
                            "job_id": "job-1",
                            "source_pdf": "paper.pdf",
                            "extracted_at": "2026-06-19T00:00:00Z",
                            "model": "gpt-5.4-mini",
                            "parse_status": "parsed",
                            "parse_error": "",
                            "cells": {"SpeciesLatinArticle": "Ailuropoda melanoleuca"},
                        }
                    ],
                    [],
                )

                locked = structured_extraction.lock_sheet_for_first_run(str(project["project_id"]), str(sheet["sheet_id"]), "job-1")
                self.assertTrue(locked["is_locked"])
                self.assertEqual(locked["locked_by_job_id"], "job-1")

                with self.assertRaises(ValueError):
                    structured_extraction.update_sheet(
                        project_id=str(project["project_id"]),
                        sheet_id=str(sheet["sheet_id"]),
                        name="Edited",
                        context="Changed",
                        row_unit="Changed",
                        columns=[{"column_name": "Changed", "question": "Changed?", "rules": ""}],
                    )

                duplicate = structured_extraction.duplicate_sheet(str(project["project_id"]), str(sheet["sheet_id"]))
                self.assertFalse(duplicate["is_locked"])
                self.assertEqual(duplicate["context"], "Original context.")
                self.assertEqual(duplicate["columns"][0]["column_name"], "SpeciesLatinArticle")
                original_rows = structured_extraction.list_rows(
                    project_id=str(project["project_id"]),
                    sheet_id=str(sheet["sheet_id"]),
                )
                duplicate_rows = structured_extraction.list_rows(
                    project_id=str(project["project_id"]),
                    sheet_id=str(duplicate["sheet_id"]),
                )
                self.assertEqual(original_rows["total"], 1)
                self.assertEqual(duplicate_rows["total"], 0)
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_structured_pdf_page_and_api_are_project_type_scoped(self) -> None:
        from fastapi.testclient import TestClient
        from openpyxl import load_workbook

        from app.main import app
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                structured_project = projects.create_project("Structured Project", "", "pdf_structured")
                pdf_project = projects.create_project("PDF Project", "", "pdf")
                sheet = structured_extraction.create_sheet(
                    project_id=str(structured_project["project_id"]),
                    name="Study fields",
                    context="Study context.",
                    row_unit="One row per study.",
                    columns=[{"column_name": "StudyTitle", "question": "State the title.", "rules": "Enter NA if absent."}],
                )
                structured_extraction.create_sheet(
                    project_id=str(structured_project["project_id"]),
                    name="Outcome fields",
                    context="Outcome context.",
                    row_unit="One row per outcome.",
                    columns=[
                        {
                            "column_name": "OutcomeName",
                            "question": "State the outcome.",
                            "rules": "Enter NA if absent.",
                        }
                    ],
                )
                client = TestClient(app)

                response = client.get(
                    f"/structured-pdf?project_id={structured_project['project_id']}",
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("Workbook-style PDF extraction", response.text)
                self.assertIn('id="duplicateWorkbookButton"', response.text)
                self.assertIn('id="exportAllSheetTextsButton"', response.text)
                self.assertIn('id="structuredWorksheetExportButton"', response.text)

                api_response = client.get(f"/api/structured/sheets?project_id={structured_project['project_id']}")
                self.assertEqual(api_response.status_code, 200)
                self.assertEqual(len(api_response.json()["sheets"]), 2)

                workbooks_response = client.get(f"/api/structured/workbooks?project_id={structured_project['project_id']}")
                self.assertEqual(workbooks_response.status_code, 200)
                self.assertEqual([item["name"] for item in workbooks_response.json()["workbooks"]], ["Workbook 1"])
                default_workbook_id = workbooks_response.json()["workbooks"][0]["workbook_id"]
                scoped_sheets_response = client.get(
                    f"/api/structured/sheets?project_id={structured_project['project_id']}&workbook_id={default_workbook_id}"
                )
                self.assertEqual(scoped_sheets_response.status_code, 200)
                self.assertEqual(len(scoped_sheets_response.json()["sheets"]), 2)
                sources_response = client.get(f"/api/structured/sources?project_id={structured_project['project_id']}")
                self.assertEqual(sources_response.status_code, 200)
                self.assertEqual(sources_response.json()["sources"], [])

                text_response = client.get(
                    f"/api/structured/sheets/{sheet['sheet_id']}/import-text?project_id={structured_project['project_id']}"
                )
                self.assertEqual(text_response.status_code, 200)
                self.assertIn("Sheet name ### Study fields", text_response.text)
                self.assertIn("Column name ### StudyTitle", text_response.text)

                workbook_text_response = client.get(
                    f"/api/structured/workbook/import-text?project_id={structured_project['project_id']}"
                )
                self.assertEqual(workbook_text_response.status_code, 200)
                self.assertIn("attachment;", workbook_text_response.headers["content-disposition"])
                self.assertIn(
                    "structured-project_workbook-1_structured_sheet_prompts.txt",
                    workbook_text_response.headers["content-disposition"],
                )
                self.assertIn("Sheet name ### Study fields", workbook_text_response.text)
                self.assertIn("Sheet name ### Outcome fields", workbook_text_response.text)
                self.assertLess(
                    workbook_text_response.text.index("Sheet name ### Study fields"),
                    workbook_text_response.text.index("Sheet name ### Outcome fields"),
                )
                self.assertNotIn("Required output format", workbook_text_response.text)

                wrong_type_text_response = client.get(
                    f"/api/structured/workbook/import-text?project_id={pdf_project['project_id']}"
                )
                self.assertEqual(wrong_type_text_response.status_code, 400)

                worksheet_response = client.get(
                    f"/api/structured/sheets/{sheet['sheet_id']}/export?project_id={structured_project['project_id']}"
                )
                self.assertEqual(worksheet_response.status_code, 200)
                self.assertIn("study-fields", worksheet_response.headers["content-disposition"])
                exported_worksheet = load_workbook(BytesIO(worksheet_response.content))
                self.assertEqual(exported_worksheet.sheetnames, ["Study fields"])

                wrong_type_worksheet_response = client.get(
                    f"/api/structured/sheets/{sheet['sheet_id']}/export?project_id={pdf_project['project_id']}"
                )
                self.assertEqual(wrong_type_worksheet_response.status_code, 400)

                duplicate_response = client.post(
                    "/api/structured/workbook/duplicate",
                    data={
                        "project_id": structured_project["project_id"],
                        "sheet_ids": json.dumps([sheet["sheet_id"]]),
                    },
                )
                self.assertEqual(duplicate_response.status_code, 200)
                duplicated_payload = duplicate_response.json()
                self.assertEqual(duplicated_payload["project"]["name"], "Structured Project (1)")
                self.assertEqual([item["name"] for item in duplicated_payload["sheets"]], ["Study fields"])

                wrong_type_response = client.get(
                    f"/structured-pdf?project_id={pdf_project['project_id']}",
                    follow_redirects=False,
                )
                self.assertEqual(wrong_type_response.status_code, 307)
                self.assertIn("/rq-screening", wrong_type_response.headers["location"])
        finally:
            config.PROJECTS_DIR = original_projects_dir


class UsabilityServiceTests(unittest.TestCase):
    def test_pdf_job_window_filters_counts_and_bounds_results(self) -> None:
        from app.services import projects

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Windowed PDF", "", "pdf")
                project_id = str(project["project_id"])
                for index, (filename, status) in enumerate(
                    [("alpha.pdf", "complete"), ("beta.pdf", "failed"), ("gamma.pdf", "queued")]
                ):
                    job_id = f"job-{index}"
                    root = jobs.create_job(job_id, filename, JobSettings(), project_id=project_id)
                    jobs.update_metadata(root, rq_prompt_filename="prompt.txt", rq_screening_model="model")
                    jobs.update_status(
                        job_id,
                        status=status,
                        stage="complete" if status == "complete" else status,
                        message=status,
                        progress=1.0 if status in {"complete", "failed"} else 0.0,
                        project_id=project_id,
                    )

                payload = jobs.list_jobs_window(project_id=project_id, offset=0, limit=1, status="completed", search="alpha")
                self.assertEqual(payload["total"], 1)
                self.assertEqual(len(payload["items"]), 1)
                self.assertEqual(payload["items"][0]["filename"], "alpha.pdf")
                self.assertEqual(payload["counts"], {"all": 3, "running": 0, "queued": 1, "completed": 1, "failed": 1})
                self.assertEqual([item["filename"] for item in payload["active_items"]], ["gamma.pdf"])
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_structured_job_window_is_sheet_scoped(self) -> None:
        from app.services import projects, structured_extraction

        original_projects_dir = config.PROJECTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config.PROJECTS_DIR = Path(tmpdir) / "projects"
                config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
                project = projects.create_project("Windowed structured", "", "pdf_structured")
                project_id = str(project["project_id"])
                columns = [{"column_name": "Finding", "question": "State the finding.", "rules": ""}]
                first = structured_extraction.create_sheet(project_id=project_id, name="First", columns=columns)
                second = structured_extraction.create_sheet(project_id=project_id, name="Second", columns=columns)
                for index, sheet in enumerate([first, second]):
                    job_id = f"structured-{index}"
                    root = jobs.create_job(job_id, f"paper-{index}.pdf", JobSettings(), project_id=project_id)
                    jobs.update_metadata(
                        root,
                        extraction_type="pdf_structured",
                        structured_sheet_id=sheet["sheet_id"],
                        structured_sheet_name=sheet["name"],
                    )
                payload = structured_extraction.list_structured_jobs_window(project_id, sheet_id=str(first["sheet_id"]), limit=10)
                self.assertEqual(payload["total"], 1)
                self.assertEqual(payload["items"][0]["filename"], "paper-0.pdf")
        finally:
            config.PROJECTS_DIR = original_projects_dir

    def test_spreadsheet_inspection_returns_headers_and_small_preview(self) -> None:
        from app.services import text_extraction

        class Upload:
            filename = "records.csv"
            file = BytesIO(b"study_id,title,abstract\nS1,One,First abstract\nS2,Two,Second abstract\n")

        payload = text_extraction.inspect_spreadsheet_upload(Upload(), preview_limit=1)
        self.assertEqual(payload["columns"], ["study_id", "title", "abstract"])
        self.assertEqual(payload["preview_rows"], [{"study_id": "S1", "title": "One", "abstract": "First abstract"}])


class BackendSmokeTests(unittest.TestCase):
    def test_key_get_endpoints_respond(self) -> None:
        original_jobs_dir = config.JOBS_DIR
        original_prompts_dir = config.PROMPTS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                config.JOBS_DIR = root / "jobs"
                config.PROMPTS_DIR = root / "prompts"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                config.PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

                from fastapi.testclient import TestClient
                from app.main import app

                client = TestClient(app)
                expectations = {
                    "/": 307,
                    "/rq-screening": 200,
                    "/api/jobs": 200,
                    "/api/queue": 200,
                    "/api/rq-prompts": 200,
                }
                for path, expected_status in expectations.items():
                    with self.subTest(path=path):
                        response = client.get(path, follow_redirects=False)
                        self.assertEqual(response.status_code, expected_status)
        finally:
            config.JOBS_DIR = original_jobs_dir
            config.PROMPTS_DIR = original_prompts_dir


class ExcelSummaryTests(unittest.TestCase):
    def test_summary_append_migrates_existing_workbook_to_prompt_column(self) -> None:
        from openpyxl import Workbook, load_workbook

        from app.services.excel_summary import SUMMARY_HEADERS, append_summary_row

        with tempfile.TemporaryDirectory() as tmpdir:
            workbook_path = Path(tmpdir) / "existing.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.append(
                [
                    "job_id",
                    "filename",
                    "when it was inferenced",
                    "how long it took",
                    "LLM model",
                    "LLM output",
                ]
            )
            worksheet.append(["old-job", "old.pdf", "old-date", 1.0, "old-model", "old-output"])
            workbook.save(workbook_path)

            append_summary_row(
                job_id="new-job",
                filename="new.pdf",
                inferenced_at="2026-05-20T00:00:00Z",
                duration_seconds=3.5,
                llm_model="gpt-5-mini",
                llm_output="new-output",
                prompt="prompt_a.txt",
                workbook_path=workbook_path,
            )

            workbook = load_workbook(workbook_path)
            worksheet = workbook.active
            self.assertEqual(
                [worksheet.cell(row=1, column=index).value for index in range(1, len(SUMMARY_HEADERS) + 1)],
                SUMMARY_HEADERS,
            )
            self.assertEqual(worksheet.cell(row=2, column=6).value, None)
            self.assertEqual(worksheet.cell(row=2, column=7).value, "old-output")
            self.assertEqual(worksheet.cell(row=3, column=6).value, "prompt_a.txt")
            self.assertEqual(worksheet.cell(row=3, column=7).value, "new-output")

    def test_summary_append_and_rebuild_share_headers_and_layout(self) -> None:
        from openpyxl import load_workbook

        from app.services.excel_summary import (
            SUMMARY_COLUMN_WIDTHS,
            SUMMARY_HEADERS,
            append_summary_row,
            rebuild_summary_from_jobs,
        )

        original_jobs_dir = config.JOBS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                append_path = root / "append.xlsx"
                append_summary_row(
                    job_id="job-1",
                    filename="Pilots/122710267.pdf",
                    inferenced_at="2026-05-20T00:00:00Z",
                    duration_seconds=3.5,
                    llm_model="gpt-5-mini",
                    llm_output="decision",
                    prompt="prompt_a.txt",
                    workbook_path=append_path,
                )
                workbook = load_workbook(append_path)
                worksheet = workbook.active
                self.assertEqual(
                    [worksheet.cell(row=1, column=index).value for index in range(1, len(SUMMARY_HEADERS) + 1)],
                    SUMMARY_HEADERS,
                )
                self.assertEqual(worksheet.cell(row=2, column=5).value, "gpt-5-mini")
                self.assertEqual(worksheet.cell(row=2, column=6).value, "prompt_a.txt")
                self.assertEqual(worksheet.cell(row=2, column=2).value, "122710267")
                for column, width in SUMMARY_COLUMN_WIDTHS.items():
                    self.assertEqual(worksheet.column_dimensions[column].width, width)

                config.JOBS_DIR = root / "jobs"
                config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
                job_root = jobs.create_job("job-2", "Pilots/screened.pdf", JobSettings())
                (job_root / "outputs" / "rq_screening_output.md").write_text("screening output", encoding="utf-8")
                jobs.update_metadata(
                    job_root,
                    completed_at="2026-05-20T01:00:00Z",
                    duration_seconds=4.0,
                    rq_screening_model="qwen",
                    rq_prompt_filename="prompt_b.txt",
                )
                jobs.update_status("job-2", status="complete", stage="complete", message="done", progress=1.0)

                rebuild_path = root / "rebuild.xlsx"
                rebuild_summary_from_jobs(workbook_path=rebuild_path)
                workbook = load_workbook(rebuild_path)
                worksheet = workbook.active
                self.assertEqual(
                    [worksheet.cell(row=1, column=index).value for index in range(1, len(SUMMARY_HEADERS) + 1)],
                    SUMMARY_HEADERS,
                )
                self.assertEqual(worksheet.cell(row=2, column=2).value, "screened")
                self.assertEqual(worksheet.cell(row=2, column=5).value, "qwen")
                self.assertEqual(worksheet.cell(row=2, column=6).value, "prompt_b.txt")
                for column, width in SUMMARY_COLUMN_WIDTHS.items():
                    self.assertEqual(worksheet.column_dimensions[column].width, width)
        finally:
            config.JOBS_DIR = original_jobs_dir


if __name__ == "__main__":
    unittest.main()
