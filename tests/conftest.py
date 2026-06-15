"""Shared fixtures for mangagen tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import mangagen  # noqa: E402


def make_project(tmp_path, spec, rel: str = "production/spec"):
    spec_dir = tmp_path / rel
    spec_dir.mkdir(parents=True)
    spec_path = spec_dir / "storyboard.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return mangagen.Project(spec_path)


def book_spec(**over):
    spec = {
        "title": "テスト本",
        "global_art_prompt": "test style",
        "characters": {"a": "A-chan, short hair"},
        "pages": [
            {
                "page": 1,
                "title": "p1",
                "panels": [
                    {
                        "id": "p1a",
                        "pos": "top-wide",
                        "art": "smile",
                        "dialogue": [{"speaker": "a", "text": "こんにちは"}],
                    }
                ],
            },
        ],
    }
    spec.update(over)
    return spec


def card(n, beat, text="ねえ見て", n_panels=1):
    return {
        "page": n,
        "beat": beat,
        "title": f"c{n}",
        "panels": [
            {
                "id": f"c{n}p{i}",
                "art": "face",
                "dialogue": [{"speaker": "a", "text": text}],
            }
            for i in range(1, n_panels + 1)
        ],
    }


def carousel_spec(**over):
    spec = {
        "title": "テスト広告",
        "format": "x-carousel",
        "page_width": 1080,
        "page_height": 1080,
        "global_art_prompt": "test style",
        "characters": {"a": "A-chan, short hair"},
        "ad_copy": "短い本文",
        "pages": [card(1, "hook"), card(2, "body"), card(3, "cta")],
    }
    spec.update(over)
    return spec


def series_page(n, beat, text="セリフ", with_teaser=False):
    dialogue = [{"speaker": "a", "text": text}]
    if with_teaser:
        dialogue.append({"kind": "text", "text": f"第{n + 1}話 次 — 続く"})
    return {
        "page": n,
        "beat": beat,
        "panels": [
            {
                "id": f"p{n:02d}_01",
                "pos": "top-wide",
                "art": "scene",
                "dialogue": dialogue,
            }
        ],
    }


def book_pages(count=1, teaser=False):
    beats = ["ki", "sho", "ten", "ketsu"]
    pages = []
    for i in range(1, count + 1):
        pages.append(series_page(i, beats[(i - 1) % 4], with_teaser=(teaser and i == count)))
    return pages


def series_episode_spec(episode, *, pages=None, teaser=False, **over):
    spec = {
        "title": f"テスト 第{episode}話",
        "format": "series-episode",
        "series": "test-series",
        "episode": episode,
        "global_art_prompt": "test",
        "characters": {"a": "A-kun"},
        "quality_checks": ["Motif trackable across pages"],
        "pages": pages or book_pages(1, teaser=teaser),
    }
    spec.update(over)
    return spec


@pytest.fixture
def tools_path():
    return Path(__file__).resolve().parent.parent / "tools"
