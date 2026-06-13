#!/usr/bin/env python3
"""Build a manga review prompt from local agent instructions."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

MODES = {
    "pitch": "企画レビュー。主人公、TPO、連載性、見せ場を中心に見る。",
    "one-shot": "読み切りレビュー。1ページ目と最終ページの変化、満足感、キャラの好感を中心に見る。",
    "name-review": "ネームレビュー。吹き出し導線、1コマ1情報、ショット配分、位置関係を中心に見る。",
    "battle": "バトルものレビュー。主人公、敵、被害者、勝ち方、ミスリードを中心に見る。",
    "ai-generation": "AI漫画制作レビュー。各コマの主情報、表情、手の演技、視線、整合性を中心に見る。",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def read_input(input_path: str | None) -> str:
    if input_path:
        return read_text(Path(input_path))

    if sys.stdin.isatty():
        return ""

    return sys.stdin.read().strip()


def build_prompt(mode: str, draft: str) -> str:
    agent = read_text(ROOT / "agents" / "manga_editor_agent.md")
    principles = read_text(ROOT / "docs" / "manga_principles.md")
    school_principles = read_text(ROOT / "docs" / "jump_manga_school_principles.md")
    checklist = read_text(ROOT / "docs" / "review_checklist.md")

    draft_section = draft or "まだ原稿や企画は未入力です。まず作者に埋めるべき項目を短く提示してください。"

    return f"""# 依頼

あなたは以下の漫画編集者エージェント設定に従ってレビューしてください。

## レビューモード

{mode}: {MODES[mode]}

---

{agent}

---

{principles}

---

{school_principles}

---

{checklist}

---

# レビュー対象

{draft_section}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a manga editor agent prompt.")
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="pitch",
        help="Review mode.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Draft, pitch, or name text file. Reads stdin when omitted.",
    )
    args = parser.parse_args()

    draft = read_input(args.input)
    print(build_prompt(args.mode, draft))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
