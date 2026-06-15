"""Core unit tests for mangagen helpers and lint."""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import mangagen  # noqa: E402

from conftest import book_spec, make_project  # noqa: E402


def test_parse_pages_all_when_none():
    assert mangagen.parse_pages(None, [1, 2, 3]) == [1, 2, 3]


def test_parse_pages_filters_selection():
    assert mangagen.parse_pages("1,3-4", [1, 2, 3, 4, 5]) == [1, 3, 4]


def test_extract_image_from_base64_data_url():
    raw = b"\x89PNG\r"
    b64 = base64.b64encode(raw).decode()
    result = {
        "choices": [{
            "message": {
                "images": [{"image_url": {"url": f"data:image/png;base64,{b64}"}}],
            },
        }],
    }
    assert mangagen.extract_image(result) == raw


def test_extract_image_missing_raises():
    with pytest.raises(RuntimeError, match="No image"):
        mangagen.extract_image({"choices": [{"message": {}}]})


def test_extract_image_invalid_url_raises():
    result = {
        "choices": [{
            "message": {"images": [{"image_url": {"url": "https://example.com/x.png"}}]},
        }],
    }
    with pytest.raises(RuntimeError, match="base64"):
        mangagen.extract_image(result)


def test_extract_text_string_content():
    result = {"choices": [{"message": {"content": "hello"}}]}
    assert mangagen.extract_text(result) == "hello"


def test_extract_text_list_content():
    result = {"choices": [{"message": {"content": [{"text": "a"}, {"text": "b"}]}}]}
    assert mangagen.extract_text(result) == "ab"


def test_load_dotenv_sets_missing_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("DOTENV_TEST_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('DOTENV_TEST_KEY="from-file"\n# comment\nBAD\n', encoding="utf-8")
    mangagen.load_dotenv(env_file)
    assert os.environ["DOTENV_TEST_KEY"] == "from-file"


def test_load_dotenv_skips_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("DOTENV_TEST_KEY", "existing")
    env_file = tmp_path / ".env"
    env_file.write_text("DOTENV_TEST_KEY=ignored\n", encoding="utf-8")
    mangagen.load_dotenv(env_file)
    assert os.environ["DOTENV_TEST_KEY"] == "existing"


def test_verdict_score_and_feedback():
    assert mangagen.verdict_score({"verdict": "pass"}) < mangagen.verdict_score({"verdict": "fail"})
    fb = mangagen.verdict_feedback({
        "verdict": "fail",
        "text_errors": ["missing text"],
        "order_ok": False,
        "order_notes": "swapped",
        "identity_errors": ["bad hand"],
        "forbidden_found": ["logo"],
    })
    assert "missing text" in fb
    assert "swapped" in fb
    assert "bad hand" in fb
    assert "logo" in fb


def test_dialogue_label_variants():
    assert "セリフ" in mangagen.dialogue_label({"speaker": "a", "text": "hi"})
    assert "モノローグ" in mangagen.dialogue_label({"kind": "monologue", "text": "think"})


def test_lint_beats_reverse_order_warns(tmp_path):
    spec = book_spec(
        pages=[
            {
                "page": 1,
                "beat": "ketsu",
                "panels": [{"id": "p1", "pos": "top-wide", "art": "a", "dialogue": []}],
            },
            {
                "page": 2,
                "beat": "ki",
                "panels": [{"id": "p2", "pos": "top-wide", "art": "b", "dialogue": []}],
            },
        ]
    )
    issues = mangagen.run_lint(make_project(tmp_path, spec))
    assert any("beat order" in e for e in issues["errors"])


def test_lint_brand_stamp_rules(tmp_path):
    spec = book_spec(
        brand_strings=["BRAND"],
        pages=[
            {
                "page": 1,
                "beat": "ki",
                "panels": [{"id": "p1", "pos": "top-wide", "art": "a", "dialogue": [{"kind": "text", "text": "BRAND"}]}],
            },
            {
                "page": 2,
                "beat": "ketsu",
                "panels": [{"id": "p2", "pos": "top-wide", "art": "b", "dialogue": []}],
            },
        ],
    )
    issues = mangagen.run_lint(make_project(tmp_path, spec))
    assert issues["errors"] == [] or issues["warnings"]


def test_project_page_missing_raises(tmp_path):
    project = make_project(tmp_path, book_spec())
    with pytest.raises(SystemExit):
        project.page(99)


def test_page_dialogue_texts():
    page = {"panels": [{"dialogue": [{"text": "a"}, {"text": "b"}]}]}
    assert mangagen.page_dialogue_texts(page) == ["a", "b"]
