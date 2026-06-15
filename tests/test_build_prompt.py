"""Tests for build_prompt CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import build_prompt  # noqa: E402


def test_build_prompt_includes_mode_and_draft():
    prompt = build_prompt.build_prompt("name-review", "draft text")
    assert "name-review" in prompt
    assert "draft text" in prompt
    assert "manga_editor_agent" not in prompt
    assert "漫画編集者" in prompt or "レビュー" in prompt


def test_build_prompt_empty_draft_placeholder():
    prompt = build_prompt.build_prompt("pitch", "")
    assert "未入力" in prompt


@pytest.mark.parametrize("mode", sorted(build_prompt.MODES))
def test_build_prompt_all_modes(mode):
    prompt = build_prompt.build_prompt(mode, "x")
    assert mode in prompt
    assert build_prompt.MODES[mode] in prompt


def test_read_input_from_file(tmp_path):
    path = tmp_path / "draft.md"
    path.write_text("hello draft", encoding="utf-8")
    assert build_prompt.read_input(str(path)) == "hello draft"


def test_read_input_tty_returns_empty(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert build_prompt.read_input(None) == ""


def test_read_input_stdin(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdin, "read", lambda: "stdin draft\n")
    assert build_prompt.read_input(None) == "stdin draft"


def test_main_prints_prompt(tmp_path, capsys):
    path = tmp_path / "draft.md"
    path.write_text("body", encoding="utf-8")
    with patch("sys.argv", ["build_prompt.py", "--mode", "one-shot", str(path)]):
        assert build_prompt.main() == 0
    out = capsys.readouterr().out
    assert "one-shot" in out
    assert "body" in out


def test_build_prompt_main_entrypoint():
    with patch("sys.argv", ["build_prompt.py", "--mode", "pitch"]):
        with patch("build_prompt.read_input", return_value="draft"):
            assert build_prompt.main() == 0

