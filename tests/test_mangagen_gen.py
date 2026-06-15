"""Generation pipeline tests for mangagen (mocked API)."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import mangagen  # noqa: E402

from conftest import book_spec, make_project  # noqa: E402


def _fake_api_result() -> dict:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {
        "choices": [{
            "message": {
                "images": [{"image_url": {"url": f"data:image/png;base64,{b64}"}}],
            },
        }],
    }


def test_generate_page_writes_prompt_and_png(tmp_path):
    project = make_project(tmp_path, book_spec())
    args = argparse.Namespace(
        model="test-model",
        max_tokens=100,
        image_size="1K",
    )
    with patch("mangagen.call_api", return_value=_fake_api_result()):
        result = mangagen.generate_page(project, 1, args)

    assert result["status"] == "generated"
    assert (project.latest / "prompts" / "page_01.md").exists()
    assert project.page_png(1).exists()


def test_backup_page_copies_existing_png(tmp_path):
    project = make_project(tmp_path, book_spec())
    png = project.page_png(1)
    png.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), "red").save(png)
    mangagen.backup_page(project, 1)
    assert list(project.history.glob("*_page_01.png"))


def test_cmd_gen_blocks_on_lint_errors(tmp_path):
    project = make_project(tmp_path, book_spec(format="x-carosel"))
    args = argparse.Namespace(
        pages="1",
        all_pages=False,
        force=False,
        concurrency=1,
        candidates=1,
        model="m",
        max_tokens=100,
        image_size="1K",
    )
    with pytest.raises(SystemExit, match="lint errors"):
        mangagen.cmd_gen(project, args)


def test_cmd_gen_runs_with_force(tmp_path):
    project = make_project(tmp_path, book_spec(format="x-carosel"))
    args = argparse.Namespace(
        pages="1",
        all_pages=False,
        force=True,
        concurrency=1,
        candidates=1,
        model="m",
        max_tokens=100,
        image_size="1K",
    )
    with patch("mangagen.generate_page", return_value={"page": 1, "status": "ok"}):
        with patch("mangagen.cmd_assemble"):
            results = mangagen.cmd_gen(project, args)
    assert results[0]["status"] == "ok"


def test_cmd_gen_refuses_all_pages_without_flag(tmp_path):
    project = make_project(tmp_path, book_spec())
    args = argparse.Namespace(
        pages=None,
        all_pages=False,
        force=True,
        concurrency=1,
        candidates=1,
        model="m",
        max_tokens=100,
        image_size="1K",
    )
    with pytest.raises(SystemExit, match="--all-pages"):
        mangagen.cmd_gen(project, args)


def test_cmd_fix_regenerates_fail_page(tmp_path):
    project = make_project(tmp_path, book_spec())
    qa_dir = project.latest / "qa"
    (qa_dir / "page_01.json").write_text(
        json.dumps({"verdict": "fail", "text_errors": ["missing"]}),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        pages="1",
        attempts=1,
        model="m",
        max_tokens=100,
        image_size="1K",
    )
    with patch("mangagen.generate_page", return_value={"page": 1, "status": "ok"}) as gen:
        with patch("mangagen.qa_page", return_value={"page": 1, "verdict": "agent_review_required"}):
            with patch("mangagen.cmd_assemble"):
                mangagen.cmd_fix(project, args)
    gen.assert_called_once()


def test_cmd_fix_missing_verdict_skips(tmp_path, capsys):
    project = make_project(tmp_path, book_spec())
    args = argparse.Namespace(pages="1", attempts=1, model="m", max_tokens=100, image_size="1K")
    with patch("mangagen.cmd_assemble"):
        mangagen.cmd_fix(project, args)
    assert "no QA verdict" in capsys.readouterr().out


def test_cmd_fix_pass_verdict_skips_regen(tmp_path, capsys):
    project = make_project(tmp_path, book_spec())
    (project.latest / "qa" / "page_01.json").write_text(
        json.dumps({"verdict": "pass"}),
        encoding="utf-8",
    )
    args = argparse.Namespace(pages="1", attempts=1, model="m", max_tokens=100, image_size="1K")
    with patch("mangagen.generate_page") as gen:
        with patch("mangagen.cmd_assemble"):
            mangagen.cmd_fix(project, args)
    gen.assert_not_called()
    assert "pass" in capsys.readouterr().out


def test_cmd_gen_rejects_multiple_candidates(tmp_path):
    project = make_project(tmp_path, book_spec())
    args = argparse.Namespace(
        pages="1",
        all_pages=False,
        force=True,
        concurrency=1,
        candidates=2,
        model="m",
        max_tokens=100,
        image_size="1K",
    )
    with pytest.raises(SystemExit, match="best-of-N"):
        mangagen.cmd_gen(project, args)


def test_main_series_review_rejects_spec_flag():
    with patch("sys.argv", ["mangagen.py", "series-review", "--series-root", "/tmp", "--spec", "x.json"]):
        with pytest.raises(SystemExit, match="does not take --spec"):
            mangagen.main()


def test_main_lint_rejects_spec_and_series_root():
    with patch("sys.argv", ["mangagen.py", "lint", "--spec", "a.json", "--series-root", "/tmp"]):
        with pytest.raises(SystemExit, match="not both"):
            mangagen.main()


def test_cmd_lint_exits_on_errors(tmp_path):
    project = make_project(tmp_path, book_spec(format="x-carosel"))
    args = argparse.Namespace(series_root=None)
    with pytest.raises(SystemExit) as exc:
        mangagen.cmd_lint(project, args)
    assert exc.value.code == 1
