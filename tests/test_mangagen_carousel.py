import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import mangagen  # noqa: E402

from conftest import book_spec, card, carousel_spec, make_project  # noqa: E402


# ---------------------------------------------------------------- back-compat

def test_book_spec_has_no_carousel_behavior(tmp_path):
    p = make_project(tmp_path, book_spec())
    assert p.format == "book"
    assert not p.is_carousel
    issues = mangagen.run_lint(p)
    assert issues["errors"] == []
    prompt = mangagen.build_prompt(p, p.page(1), "model-x")
    assert "Aspect ratio 2:3" in prompt
    assert "CAROUSEL" not in prompt


def test_unknown_format_is_lint_error(tmp_path):
    p = make_project(tmp_path, book_spec(format="x-carosel"))  # typo
    issues = mangagen.run_lint(p)
    assert any("unknown format" in e for e in issues["errors"])


def test_carousel_format_detected(tmp_path):
    p = make_project(tmp_path, carousel_spec())
    assert p.format == "x-carousel"
    assert p.is_carousel


# ---------------------------------------------------------------- carousel lint

def test_card_count_out_of_range_is_error(tmp_path):
    one = carousel_spec(pages=[card(1, "hook")])
    seven = carousel_spec(pages=[card(1, "hook")] + [card(i, "body") for i in range(2, 7)] + [card(7, "cta")])
    for spec in (one, seven):
        p = make_project(tmp_path / spec["pages"][-1]["title"], spec)
        issues = mangagen.run_lint(p)
        assert any("2-6 cards" in e for e in issues["errors"]), issues


def test_carousel_rejects_book_beats(tmp_path):
    p = make_project(tmp_path, carousel_spec(pages=[card(1, "ki"), card(2, "cta")]))
    issues = mangagen.run_lint(p)
    assert any("hook/body/cta" in e for e in issues["errors"])


def test_beat_position_warnings(tmp_path):
    spec = carousel_spec(pages=[card(1, "body"), card(2, "cta"), card(3, "body")])
    p = make_project(tmp_path, spec)
    issues = mangagen.run_lint(p)
    warns = "\n".join(issues["warnings"])
    assert "hook" in warns          # 1枚目がhookでない
    assert "final card" in warns    # 最終枚がctaでない or ctaが途中
    assert issues["errors"] == []


def test_clean_carousel_has_no_issues(tmp_path):
    p = make_project(tmp_path, carousel_spec())
    issues = mangagen.run_lint(p)
    assert issues["errors"] == []
    assert issues["warnings"] == []


def test_non_square_canvas_warns(tmp_path):
    p = make_project(tmp_path, carousel_spec(page_width=1600, page_height=2400))
    issues = mangagen.run_lint(p)
    assert any("square" in w for w in issues["warnings"])


def test_carousel_brand_rules(tmp_path):
    # ブランド未出現はerror
    p = make_project(tmp_path / "none", carousel_spec(brand_strings=["スキマッチ"]))
    issues = mangagen.run_lint(p)
    assert any("never appears" in e for e in issues["errors"])

    # 最終枚より前にブランドが出たらwarn（広告色の漏れ）
    spec = carousel_spec(brand_strings=["スキマッチ"],
                         pages=[card(1, "hook", text="スキマッチ見て"), card(2, "body"),
                                card(3, "cta", text="スキマッチで検索")])
    p = make_project(tmp_path / "leak", spec)
    issues = mangagen.run_lint(p)
    assert any("before the final card" in w and "スキマッチ" in w for w in issues["warnings"])
    assert issues["errors"] == []

    # 最終枚（cta）だけにあればクリーン
    spec = carousel_spec(brand_strings=["スキマッチ"],
                         pages=[card(1, "hook"), card(2, "body"),
                                card(3, "cta", text="スキマッチで検索")])
    p = make_project(tmp_path / "clean", spec)
    issues = mangagen.run_lint(p)
    assert issues["errors"] == []
    assert issues["warnings"] == []


# ---------------------------------------------------------------- text budgets

def test_x_weighted_len():
    assert mangagen.x_weighted_len("abc") == 3      # 半角=1
    assert mangagen.x_weighted_len("あいう") == 6    # CJK=2
    assert mangagen.x_weighted_len("aあ") == 3


def test_ad_copy_over_280_weighted_is_error(tmp_path):
    p = make_project(tmp_path, carousel_spec(ad_copy="あ" * 141))  # 282 weighted
    issues = mangagen.run_lint(p)
    assert any("ad_copy" in e for e in issues["errors"])


def test_card_char_budget(tmp_path):
    warn_spec = carousel_spec(pages=[card(1, "hook", text="あ" * 81), card(2, "cta")])
    p = make_project(tmp_path / "warn", warn_spec)
    issues = mangagen.run_lint(p)
    assert any("soft cap 80" in w for w in issues["warnings"])
    assert issues["errors"] == []

    err_spec = carousel_spec(pages=[card(1, "hook", text="あ" * 121), card(2, "cta")])
    p = make_project(tmp_path / "err", err_spec)
    issues = mangagen.run_lint(p)
    assert any("mobile ad limit 120" in e for e in issues["errors"])


def test_too_many_panels_per_card_warns(tmp_path):
    p = make_project(tmp_path, carousel_spec(pages=[card(1, "hook", n_panels=5), card(2, "cta")]))
    issues = mangagen.run_lint(p)
    assert any("panels on one card" in w for w in issues["warnings"])


def test_book_char_budget_unchanged(tmp_path):
    spec = book_spec()
    spec["pages"][0]["panels"][0]["dialogue"][0]["text"] = "あ" * 121
    p = make_project(tmp_path, spec)
    issues = mangagen.run_lint(p)
    assert issues["errors"] == []  # bookでは121字はerrorにならない（150字warnのみの世界）


def test_carousel_invalid_pos_still_errors(tmp_path):
    spec = carousel_spec()
    spec["pages"][0]["panels"][0]["pos"] = "top-wyde"  # typo
    p = make_project(tmp_path, spec)
    issues = mangagen.run_lint(p)
    assert any("unknown pos" in e for e in issues["errors"])


def test_carousel_missing_pos_is_silent(tmp_path):
    p = make_project(tmp_path, carousel_spec())
    issues = mangagen.run_lint(p)
    assert not any("no pos slot" in w for w in issues["warnings"])


# ---------------------------------------------------------------- prompt build

def test_carousel_prompt_content(tmp_path):
    p = make_project(tmp_path, carousel_spec())
    prompt = mangagen.build_prompt(p, p.page(1), "model-x")
    assert "CAROUSEL AD" in prompt
    assert "card 1 of 3" in prompt
    assert "SQUARE" in prompt
    assert "Aspect ratio 2:3" not in prompt
    assert "FIRST card (hook)" in prompt
    assert "LEFT-to-RIGHT swipe" in prompt
    assert "RIGHT panel of a row is read before the LEFT" in prompt  # rtl既定

    cta = mangagen.build_prompt(p, p.page(3), "model-x")
    assert "FINAL card (cta)" in cta


def test_carousel_prompt_keeps_text_contract(tmp_path):
    p = make_project(tmp_path, carousel_spec())
    prompt = mangagen.build_prompt(p, p.page(1), "model-x")
    assert "TEXT RENDERING CONTRACT" in prompt
    assert "「ねえ見て」" in prompt
    assert "CHARACTER CONTINUITY" in prompt
    assert "SCREEN PHYSICS" in prompt  # QAチェック7と対になる生成側指示


# ---------------------------------------------------------------- vision QA

def test_qa_payload_carries_format(tmp_path):
    p = make_project(tmp_path, carousel_spec())
    payload = mangagen.qa_payload(p, p.page(1))
    assert payload["format"] == "x-carousel"

    pb = make_project(tmp_path / "book", book_spec())
    assert mangagen.qa_payload(pb, pb.page(1))["format"] == "book"


def test_qa_carousel_note_exists():
    assert "square card" in mangagen.QA_CAROUSEL_NOTE
    assert "left-to-right" in mangagen.QA_CAROUSEL_NOTE.lower()


# ---------------------------------------------------------------- review

def test_review_principles_include_ads_doc_for_carousel(tmp_path):
    p = make_project(tmp_path, carousel_spec())
    text = mangagen.review_principles(p)
    assert "x_ads_manga_principles.md" in text

    pb = make_project(tmp_path / "book", book_spec())
    assert "x_ads_manga_principles.md" not in mangagen.review_principles(pb)
    assert "x_ads_manga_principles.md" not in mangagen.review_principles()  # 引数なし=book扱い


def test_review_writes_agent_request_without_api_call(tmp_path, monkeypatch):
    p = make_project(tmp_path, book_spec())

    def fail_call_api(*args, **kwargs):
        raise AssertionError("review must not call external APIs")

    monkeypatch.setattr(mangagen, "call_api", fail_call_api)

    mangagen.cmd_review(p, None)

    request = p.latest / "qa" / "review_request.md"
    payload = p.latest / "qa" / "review_payload.json"
    assert request.exists()
    assert payload.exists()
    assert "JSONのみで返答" in request.read_text(encoding="utf-8")
    data = json.loads(payload.read_text(encoding="utf-8"))
    assert data["title"] == "テスト本"
    assert data["format"] == "book"


def test_qa_writes_agent_request_without_api_call(tmp_path, monkeypatch):
    from PIL import Image

    p = make_project(tmp_path, book_spec())
    Image.new("RGB", (1600, 2400), "gray").save(p.page_png(1))

    def fail_call_api(*args, **kwargs):
        raise AssertionError("qa must not call external APIs")

    monkeypatch.setattr(mangagen, "call_api", fail_call_api)

    verdicts = mangagen.cmd_qa(p, type("Args", (), {"pages": None, "concurrency": 1})())

    request = p.latest / "qa" / "page_01_request.md"
    payload = p.latest / "qa" / "page_01_payload.json"
    assert request.exists()
    assert payload.exists()
    assert verdicts[0]["verdict"] == "agent_review_required"
    assert "Inspect the image directly" in request.read_text(encoding="utf-8")
    data = json.loads(payload.read_text(encoding="utf-8"))
    assert data["page"] == 1
    assert data["image_path"].endswith("page_01.png")


# ---------------------------------------------------------------- assemble

def _put_dummy_cards(project, n):
    from PIL import Image
    for i in range(1, n + 1):
        Image.new("RGB", (1080, 1080), "gray").save(project.page_png(i))


def test_assemble_carousel_strip(tmp_path):
    from PIL import Image
    p = make_project(tmp_path, carousel_spec())
    _put_dummy_cards(p, 3)
    mangagen.cmd_assemble(p, None)
    sheet = Image.open(p.latest / "contact_sheet.png")
    assert sheet.width == 3 * 380          # 横一列（スワイプ順）
    assert sheet.height == 410
    assert (p.latest / "ad_copy.txt").read_text(encoding="utf-8").strip() == "短い本文"
    assert not (p.latest / "book.pdf").exists()


def test_assemble_carousel_without_ad_copy_removes_stale_file(tmp_path):
    spec = carousel_spec()
    del spec["ad_copy"]
    p = make_project(tmp_path, spec)
    _put_dummy_cards(p, 3)
    (p.latest / "ad_copy.txt").write_text("古い本文\n", encoding="utf-8")  # 前回runの残骸
    mangagen.cmd_assemble(p, None)
    assert not (p.latest / "ad_copy.txt").exists()


def test_assemble_book_unchanged(tmp_path):
    from PIL import Image
    p = make_project(tmp_path, book_spec())
    Image.new("RGB", (1600, 2400), "gray").save(p.page_png(1))
    mangagen.cmd_assemble(p, None)
    assert (p.latest / "book.pdf").exists()
    assert not (p.latest / "ad_copy.txt").exists()


def test_text_render_instructions_distinguish_kinds():
    speech = mangagen.text_render_instructions({"speaker": "ヒロ", "text": "うち、来る？"})
    mono = mangagen.text_render_instructions({"kind": "monologue", "text": "見ない"})
    cap = mangagen.text_render_instructions({"kind": "caption", "text": "翌朝"})
    joined_speech = " ".join(speech).lower()
    joined_mono = " ".join(mono).lower()
    joined_cap = " ".join(cap).lower()
    assert "oval" in joined_speech
    assert "cloud-shaped" in joined_mono
    assert "slanted rectangular" in joined_cap
    assert "bubble-dot" not in joined_cap


def test_build_prompt_includes_container_instructions(tmp_path):
    spec = book_spec()
    spec["pages"] = [{"page": 1, "title": "p1", "panels": [
        {"id": "p1a", "pos": "top-wide", "art": "face",
         "dialogue": [
             {"speaker": "a", "text": "セリフ"},
             {"kind": "monologue", "text": "心の声"},
             {"kind": "caption", "text": "翌朝"},
         ]},
    ]}]
    p = make_project(tmp_path, spec)
    prompt = mangagen.build_prompt(p, p.page(1), "model-x")
    assert "Container type: spoken dialogue" in prompt
    assert "cloud-shaped thought balloon" in prompt
    assert "slanted rectangular narration frame" in prompt
    assert "TEXT CONTAINER CONSISTENCY" in prompt
