import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import mangagen  # noqa: E402

from conftest import (  # noqa: E402
    book_pages,
    make_project,
    series_episode_spec,
    series_page,
)


def write_series_json(series_root, episodes):
    data = {
        "title": "テスト連載",
        "slug": "test-series",
        "format": "series",
        "episodes": episodes,
    }
    (series_root / "series.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def setup_two_episode_series(tmp_path):
    series_root = tmp_path / "manga" / "production" / "spec"
    series_root.mkdir(parents=True)

    ep1_dir = tmp_path / "manga" / "ep01" / "production" / "spec"
    ep2_dir = tmp_path / "manga" / "ep02" / "production" / "spec"
    ep1_dir.mkdir(parents=True)
    ep2_dir.mkdir(parents=True)

    ep1_spec = series_episode_spec(1, pages=book_pages(2, teaser=True))
    ep2_spec = series_episode_spec(
        2,
        pages=book_pages(1),
        characters={"a": "A-kun", "b": "B-kun", "c": "C-kun"},
        quality_checks=["Sports bag trackable from ep1"],
    )
    ep1_path = ep1_dir / "storyboard.json"
    ep2_path = ep2_dir / "storyboard.json"
    ep1_spec["series_root"] = "../../../production/spec"
    ep2_spec["series_root"] = "../../../production/spec"
    ep1_path.write_text(json.dumps(ep1_spec, ensure_ascii=False), encoding="utf-8")
    ep2_path.write_text(json.dumps(ep2_spec, ensure_ascii=False), encoding="utf-8")

    write_series_json(series_root, [
        {
            "number": 1,
            "slug": "ep01",
            "title": "第一話",
            "spec": "../../ep01/production/spec/storyboard.json",
            "emotional_delta": "開始 → 中間",
        },
        {
            "number": 2,
            "slug": "ep02",
            "title": "第二話",
            "spec": "../../ep02/production/spec/storyboard.json",
            "emotional_delta": "中間 → 終了",
        },
    ])
    return series_root, ep1_path, ep2_path


def test_series_episode_format_detected(tmp_path):
    p = make_project(tmp_path, series_episode_spec(1))
    assert p.format == "series-episode"
    assert p.is_series_episode
    assert not p.is_carousel


def test_unknown_format_still_errors(tmp_path):
    p = make_project(tmp_path, series_episode_spec(1, format="x-carosel"))
    issues = mangagen.run_lint(p)
    assert any("unknown format" in e for e in issues["errors"])


def test_episode_field_without_series_format_warns(tmp_path):
    spec = series_episode_spec(1)
    spec.pop("format")
    p = make_project(tmp_path, spec)
    issues = mangagen.run_lint(p)
    assert any("format is 'book'" in w for w in issues["warnings"])


def test_series_episode_requires_episode_number(tmp_path):
    spec = series_episode_spec(1)
    spec.pop("episode")
    p = make_project(tmp_path, spec)
    issues = mangagen.run_lint(p)
    assert any("requires an integer 'episode'" in e for e in issues["errors"])


def test_missing_next_episode_teaser_warns(tmp_path):
    _, ep1_path, _ = setup_two_episode_series(tmp_path)
    spec = json.loads(ep1_path.read_text(encoding="utf-8"))
    spec["pages"] = book_pages(2, teaser=False)
    ep1_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    p = mangagen.Project(ep1_path)
    issues = mangagen.run_lint(p)
    assert any("next-episode teaser" in w for w in issues["warnings"])


def test_finale_with_teaser_warns(tmp_path):
    series_root = tmp_path / "spec"
    series_root.mkdir()
    write_series_json(series_root, [{
        "number": 1,
        "slug": "ep01",
        "title": "最終話",
        "spec": "storyboard.json",
        "emotional_delta": "a → b",
    }])
    spec = series_episode_spec(1, teaser=True)
    spec["series_root"] = "."
    spec_path = series_root / "storyboard.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    p = mangagen.Project(spec_path)
    issues = mangagen.run_lint(p)
    assert any("series finale" in w for w in issues["warnings"])


def test_character_jump_warns(tmp_path):
    _, _, ep2_path = setup_two_episode_series(tmp_path)
    p = mangagen.Project(ep2_path)
    issues = mangagen.run_lint(p)
    assert any("characters vs ep1" in w for w in issues["warnings"])


def test_series_root_batch_lint(tmp_path):
    series_root, _, _ = setup_two_episode_series(tmp_path)
    ctx = mangagen.SeriesContext.from_root(series_root)
    cross_warnings: list[str] = []
    cross_errors: list[str] = []
    mangagen.lint_series_cross(ctx, cross_warnings, cross_errors)
    assert cross_errors == []
    for ep in ctx.episodes():
        project = mangagen.Project(ctx.resolve_spec_path(ep))
        issues = mangagen.run_lint(project)
        assert isinstance(issues["errors"], list)


def test_review_payload_includes_series_fields(tmp_path):
    _, _, ep2_path = setup_two_episode_series(tmp_path)
    p = mangagen.Project(ep2_path)
    payload = mangagen.review_payload(p)
    assert payload["format"] == "series-episode"
    assert payload["episode"] == 2
    assert payload["series_title"] == "テスト連載"
    assert payload["emotional_delta"] == "中間 → 終了"
    assert "prev_episode_final" in payload


def test_series_review_instructions_exclude_one_shot_satisfaction():
    assert "読み切りの満足" not in mangagen.SERIES_EPISODE_REVIEW_INSTRUCTIONS
    assert "読み切りの完結満足" in mangagen.SERIES_EPISODE_REVIEW_INSTRUCTIONS


def test_review_principles_includes_series_doc(tmp_path):
    p = make_project(tmp_path, series_episode_spec(1))
    text = mangagen.review_principles(p)
    assert "series_principles.md" in text


def test_series_review_payload_and_request(tmp_path):
    series_root, _, _ = setup_two_episode_series(tmp_path)
    ctx = mangagen.SeriesContext.from_root(series_root)
    payload = mangagen.series_review_payload(ctx)
    assert payload["episode_count"] == 2
    assert payload["episodes"][0]["number"] == 1
    content = mangagen.series_review_request_content(ctx, payload)
    assert "series_review_checklist" in content
    assert "全話要約" in content


def test_has_next_episode_teaser(tmp_path):
    p = make_project(tmp_path, series_episode_spec(1, pages=book_pages(1, teaser=True)))
    assert mangagen.has_next_episode_teaser(p, 2)
