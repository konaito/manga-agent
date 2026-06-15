"""CLI command and SeriesContext tests for mangagen."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import mangagen  # noqa: E402

from conftest import book_spec, make_project, series_episode_spec  # noqa: E402


def test_series_context_from_root(tmp_path):
    series_root = tmp_path / "spec"
    series_root.mkdir(parents=True)
    (series_root / "series.json").write_text(
        json.dumps({"title": "S", "slug": "s", "episodes": [{"number": 1, "path": "ep01"}]}),
        encoding="utf-8",
    )
    ctx = mangagen.SeriesContext.from_root(series_root)
    assert ctx.slug == "s"
    assert ctx.episode_numbers() == [1]


def test_series_context_missing_exits(tmp_path):
    with pytest.raises(SystemExit, match="series.json"):
        mangagen.SeriesContext.from_root(tmp_path / "missing")


def test_cmd_prompts_writes_files(tmp_path):
    project = make_project(tmp_path, book_spec())
    args = argparse.Namespace(pages="1", model="test-model")
    mangagen.cmd_prompts(project, args)
    assert (project.latest / "prompts" / "page_01.md").exists()


def test_cmd_series_review_writes_request(tmp_path):
    series_root = tmp_path / "manga" / "production" / "spec"
    series_root.mkdir(parents=True)
    ep_dir = tmp_path / "manga" / "ep01" / "production" / "spec"
    ep_dir.mkdir(parents=True)
    spec = series_episode_spec(1)
    (ep_dir / "storyboard.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    (series_root / "series.json").write_text(
        json.dumps({
            "title": "S",
            "slug": "test-series",
            "episodes": [{"number": 1, "spec": "../ep01/production/spec/storyboard.json"}],
        }),
        encoding="utf-8",
    )
    args = argparse.Namespace(series_root=str(series_root))
    mangagen.cmd_series_review(args)
    ctx = mangagen.SeriesContext.from_root(series_root)
    assert (ctx.series_output_dir() / "series_review_request.md").exists()


def test_qa_page_missing_png(tmp_path):
    project = make_project(tmp_path, book_spec())
    result = mangagen.qa_page(project, 1, save=False)
    assert result["verdict"] == "missing"


def test_qa_page_writes_request(tmp_path):
    project = make_project(tmp_path, book_spec())
    png = project.page_png(1)
    Image.new("RGB", (8, 8), "blue").save(png)
    result = mangagen.qa_page(project, 1)
    assert result["verdict"] == "agent_review_required"
    assert (project.latest / "qa" / "page_01_request.md").exists()


def test_text_render_instruction_kinds():
    kinds = ["ui", "caption", "monologue", "sfx", "unknown"]
    for kind in kinds:
        lines = mangagen.text_render_instructions({"kind": kind, "text": "x"})
        assert lines


def test_cmd_charsheet_mocked(tmp_path):
    project = make_project(tmp_path, book_spec())
    args = argparse.Namespace(model="m", max_tokens=100, image_size="1K")
    with patch("mangagen.call_api", return_value={"choices": [{"message": {"images": []}}]}):
        with patch("mangagen.extract_image", return_value=b"png"):
            mangagen.cmd_charsheet(project, args)
    assert (project.spec_dir / "character_sheet.png").exists()


def test_cmd_assemble_no_pages(tmp_path, capsys):
    project = make_project(tmp_path, book_spec())
    args = argparse.Namespace()
    mangagen.cmd_assemble(project, args)
    assert "no pages" in capsys.readouterr().out


def test_main_lint_command(tmp_path):
    spec_dir = tmp_path / "production" / "spec"
    spec_dir.mkdir(parents=True)
    spec_path = spec_dir / "storyboard.json"
    spec_path.write_text(json.dumps(book_spec()), encoding="utf-8")
    with patch("sys.argv", ["mangagen.py", "lint", "--spec", str(spec_path)]):
        assert mangagen.main() == 0


def test_cmd_lint_series(tmp_path, capsys):
    series_root = tmp_path / "manga" / "production" / "spec"
    series_root.mkdir(parents=True)
    ep_dir = tmp_path / "manga" / "ep01" / "production" / "spec"
    ep_dir.mkdir(parents=True)
    (ep_dir / "storyboard.json").write_text(json.dumps(series_episode_spec(1)), encoding="utf-8")
    (series_root / "series.json").write_text(
        json.dumps({
            "title": "S",
            "slug": "test-series",
            "episodes": [{"number": 1, "spec": "../ep01/production/spec/storyboard.json"}],
        }),
        encoding="utf-8",
    )
    args = argparse.Namespace(series_root=str(series_root))
    with patch("mangagen.lint_series_cross"), patch(
        "mangagen.run_lint", return_value={"errors": [], "warnings": []}
    ):
        mangagen.cmd_lint(None, args)
    assert "series lint" in capsys.readouterr().out


def test_cmd_qa_writes_requests(tmp_path):
    project = make_project(tmp_path, book_spec())
    png = project.page_png(1)
    Image.new("RGB", (8, 8), "red").save(png)
    args = argparse.Namespace(pages="1", concurrency=1)
    mangagen.cmd_qa(project, args)
    assert (project.latest / "qa" / "page_01_request.md").exists()


def test_main_series_review_requires_root():
    with patch("sys.argv", ["mangagen.py", "series-review"]):
        with pytest.raises(SystemExit, match="series-root"):
            mangagen.main()


def test_main_requires_spec_for_gen():
    with patch("sys.argv", ["mangagen.py", "gen"]):
        with pytest.raises(SystemExit, match="requires --spec"):
            mangagen.main()
