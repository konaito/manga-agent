"""Additional mangagen lint and web auth coverage tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import mangagen  # noqa: E402

from conftest import book_spec, make_project  # noqa: E402


def test_run_lint_panel_order_error(tmp_path):
    spec = book_spec(
        pages=[
            {
                "page": 1,
                "panels": [
                    {"id": "a", "pos": "row1-left", "art": "x", "dialogue": [{"speaker": "a", "text": "a"}]},
                    {"id": "b", "pos": "row1-right", "art": "y", "dialogue": [{"speaker": "a", "text": "b"}]},
                ],
            }
        ]
    )
    issues = mangagen.run_lint(make_project(tmp_path, spec))
    assert any("backwards" in e for e in issues["errors"])


def test_run_lint_forbidden_string(tmp_path):
    spec = book_spec(
        forbidden_strings=["SECRET"],
        pages=[
            {
                "page": 1,
                "panels": [
                    {"id": "a", "pos": "top-wide", "art": "x", "dialogue": [{"speaker": "a", "text": "SECRET"}]},
                ],
            }
        ],
    )
    issues = mangagen.run_lint(make_project(tmp_path, spec))
    assert any("forbidden" in e for e in issues["errors"])


def test_verdict_feedback_extra_text():
    fb = mangagen.verdict_feedback({"extra_text": ["noise"]})
    assert "invented text" in fb


def test_series_context_resolve_spec_path(tmp_path):
    series_root = tmp_path / "spec"
    series_root.mkdir()
    (series_root / "series.json").write_text(
        json.dumps({"title": "S", "slug": "s", "episodes": [{"number": 1, "spec": "ep01/storyboard.json"}]}),
        encoding="utf-8",
    )
    ctx = mangagen.SeriesContext.from_root(series_root)
    assert ctx.resolve_spec_path(ctx.episodes()[0]).name == "storyboard.json"


@pytest.mark.asyncio
async def test_web_auth_error_detail_invalid_json():
    from app.web import _auth_error_detail

    class Resp:
        text = "plain error"

        @staticmethod
        def json():
            raise ValueError("bad json")

    assert _auth_error_detail(Resp()) == "plain error"
