#!/usr/bin/env python3
"""mangagen: spec-driven manga production harness.

Single source of truth is the spec JSON (storyboard). The spec carries pages,
panels, cast identifiers, quality checks, and optional reference images, so
this tool never needs editing when the cast or story changes.

Design follows harness-engineering practice: deterministic feedforward checks
(lint) run before any paid call, inferential feedback checks (vision QA) run
after, regeneration receives the QA verdict as explicit feedback, loops have
hard attempt caps that escalate to a human, and every API call is journaled
to a cost ledger.

Subcommands:
  lint          - deterministic spec checks, free, run before paid generation
                  (--series-root lints all episodes in series.json)
  review        - editorial review request for one episode spec (free)
  series-review - cross-episode review request from series.json (free)
  prompts       - write page prompts only (free dry run)
  gen           - generate selected pages (paid image API); --candidates N for
                  QA-scored best-of-N selection per page
  qa            - vision-QA existing pages against the spec (cheap vision API)
  fix           - regenerate pages that fail QA, feeding the QA errors back into
                  the prompt, up to N attempts, then escalate
  assemble      - rebuild contact sheet and book.pdf from current pages
  charsheet     - generate a character reference sheet image from the cast list

Spec additions over the legacy storyboard format (all optional):
  "format": "x-carousel",               X ad carousel mode: 1:1 cards, 2-6
                                        slides, hook/body/cta beats, ad lint
  "format": "series-episode",           serialized manga episode (book layout
                                        + series lint/review; see series.json)
  "series": "slug",                     series identifier (matches series.json)
  "episode": 2,                         episode number within the series
  "series_root": "../../../production/spec",  path from spec dir to series.json
  "ad_copy": "...",                     post body text (280 weighted chars)
  "quality_checks": ["..."],            page-prompt + QA checklist lines
  "reference_images": ["relative.png"], image refs sent with every gen call
  panel "pos": "top-wide" etc.,         explicit slot -> kills order errors

Output layout (sibling of the spec dir):
  output/latest/{pages,prompts,raw,qa}/  current best book
  output/history/                        replaced pages, timestamped
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, JpegImagePlugin  # noqa: F401

from image_provider import get_provider  # noqa: E402

DEFAULT_GEN_MODEL = "openai/gpt-5.4-image-2"
DEFAULT_MAX_TOKENS = 16384

VALID_FORMATS = ("book", "x-carousel", "series-episode")
SERIES_JSON_NAME = "series.json"
SERIES_ROOT_SEARCH_DEPTH = 5
NEXT_EPISODE_RE = re.compile(r"続く|第\s*(\d+)\s*話")
CONTINUITY_HINTS = ("track", "consistent", "continuity", "追跡", "同一", "前話", "trackable")

LAYOUTS = {
    "hook4": "4 panels: a large full-width top hook panel, a middle row of two panels (right read first, then left), and a large full-width bottom panel.",
    "four": "4 panels in two rows. Each row reads right panel first, then left panel.",
    "five": "5 panels: a full-width top panel, then two rows of two panels, each row reading right first then left; the final panel may be full-width at the bottom.",
    "ending5": "5 panels in a slow ending rhythm: wide atmospheric top panel, a right-to-left middle row, a quiet motif panel, and a full-width bottom final image.",
}

POS_LABELS = {
    "top-wide": "full-width panel at the very top of the page",
    "bottom-wide": "full-width panel at the very bottom of the page",
    "row1-right": "RIGHT panel of the first row (read before the left panel of the same row)",
    "row1-left": "LEFT panel of the first row (read after the right panel of the same row)",
    "row2-right": "RIGHT panel of the second row (read before the left panel of the same row)",
    "row2-left": "LEFT panel of the second row (read after the right panel of the same row)",
    "row3-right": "RIGHT panel of the third row (read before the left panel of the same row)",
    "row3-left": "LEFT panel of the third row (read after the right panel of the same row)",
    "middle-wide": "full-width panel in the middle of the page",
}


# ---------------------------------------------------------------- env / paths

def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class SeriesContext:
    """Loads series.json and resolves episode specs relative to the series root."""

    def __init__(self, series_json_path: Path):
        self.path = series_json_path.resolve()
        self.root = self.path.parent
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    @classmethod
    def from_root(cls, series_root: Path) -> SeriesContext:
        root = series_root.resolve()
        candidate = root / SERIES_JSON_NAME if root.is_dir() else root
        if candidate.is_dir():
            candidate = candidate / SERIES_JSON_NAME
        if not candidate.exists():
            sys.exit(f"series.json not found at {candidate}")
        return cls(candidate)

    @classmethod
    def for_project(cls, project: Project) -> SeriesContext | None:
        path = resolve_series_json_path(project)
        if path is None:
            return None
        return cls(path)

    @property
    def title(self) -> str:
        return self.data.get("title", "")

    @property
    def slug(self) -> str:
        return self.data.get("slug", "")

    def episodes(self) -> list[dict]:
        return sorted(self.data.get("episodes", []), key=lambda e: int(e["number"]))

    def episode_numbers(self) -> list[int]:
        return [int(e["number"]) for e in self.episodes()]

    def episode_meta(self, number: int) -> dict | None:
        for ep in self.episodes():
            if int(ep["number"]) == number:
                return ep
        return None

    def resolve_spec_path(self, episode: dict) -> Path:
        return (self.root / episode["spec"]).resolve()

    def resolve_spec_path_for_number(self, number: int) -> Path | None:
        meta = self.episode_meta(number)
        if meta is None:
            return None
        return self.resolve_spec_path(meta)

    def is_final_episode(self, number: int) -> bool:
        nums = self.episode_numbers()
        return bool(nums) and number == max(nums)

    def prev_episode_meta(self, number: int) -> dict | None:
        return self.episode_meta(number - 1)

    def next_episode_meta(self, number: int) -> dict | None:
        return self.episode_meta(number + 1)

    def story_bible_path(self) -> Path | None:
        rel = self.data.get("story_bible")
        if not rel:
            return None
        path = (self.root / rel).resolve()
        return path if path.exists() else None

    def adaptation_design_path(self) -> Path | None:
        rel = self.data.get("adaptation_design")
        if not rel:
            return None
        path = (self.root / rel).resolve()
        return path if path.exists() else None

    def series_output_dir(self) -> Path:
        """Shared output for series-level artifacts (series-review)."""
        out = self.root.parent / "output" / "latest" / "qa"
        out.mkdir(parents=True, exist_ok=True)
        return out

    def load_episode_spec(self, number: int) -> dict | None:
        path = self.resolve_spec_path_for_number(number)
        if path is None or not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def prev_episode_final_page(self, episode_number: int) -> dict | None:
        spec = self.load_episode_spec(episode_number - 1)
        if not spec or not spec.get("pages"):
            return None
        last = max(spec["pages"], key=lambda p: int(p["page"]))
        return {
            "page": int(last["page"]),
            "dialogue": [
                d for panel in last.get("panels", [])
                for d in panel.get("dialogue", [])
            ],
        }


def resolve_series_json_path(project: Project) -> Path | None:
    spec = project.spec
    if spec.get("series_root"):
        candidate = (project.spec_dir / spec["series_root"] / SERIES_JSON_NAME).resolve()
        if candidate.exists():
            return candidate
    current = project.spec_dir
    for _ in range(SERIES_ROOT_SEARCH_DEPTH):
        candidate = current / SERIES_JSON_NAME
        if candidate.exists():
            return candidate.resolve()
        if current.parent == current:
            break
        current = current.parent
    return None


def load_episode_spec_from_path(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def page_dialogue_texts(page: dict) -> list[str]:
    texts: list[str] = []
    for panel in page.get("panels", []):
        for item in panel.get("dialogue", []):
            text = item.get("text", "")
            if text.strip():
                texts.append(text)
    return texts


def final_page(project: Project) -> dict | None:
    pages = project.pages()
    if not pages:
        return None
    return max(pages, key=lambda p: int(p["page"]))


def has_next_episode_teaser(project: Project, next_episode: int) -> bool:
    page = final_page(project)
    if page is None:
        return False
    combined = " ".join(page_dialogue_texts(page))
    if "続く" in combined:
        for match in NEXT_EPISODE_RE.finditer(combined):
            if match.group(1) and int(match.group(1)) == next_episode:
                return True
        if f"第{next_episode}話" in combined or f"第 {next_episode} 話" in combined:
            return True
        return True  # 「続く」 alone counts
    for match in NEXT_EPISODE_RE.finditer(combined):
        if match.group(1) and int(match.group(1)) == next_episode:
            return True
    return False


class Project:
    def __init__(self, spec_path: Path):
        self.spec_path = spec_path.resolve()
        self.spec_dir = self.spec_path.parent
        self.root = self.spec_dir.parent
        self.spec = json.loads(self.spec_path.read_text(encoding="utf-8"))
        load_dotenv(self.root / ".env")
        self.latest = self.root / "output" / "latest"
        self.history = self.root / "output" / "history"
        for sub in ("pages", "prompts", "raw", "qa", "candidates"):
            (self.latest / sub).mkdir(parents=True, exist_ok=True)
        self.history.mkdir(parents=True, exist_ok=True)
        self.ledger = self.root / "output" / "ledger.jsonl"

    @property
    def format(self) -> str:
        return self.spec.get("format", "book")

    @property
    def is_carousel(self) -> bool:
        return self.format == "x-carousel"

    @property
    def is_series_episode(self) -> bool:
        return self.format == "series-episode"

    def series_context(self) -> SeriesContext | None:
        if not self.is_series_episode:
            return None
        return SeriesContext.for_project(self)

    def episode_number(self) -> int | None:
        ep = self.spec.get("episode")
        return int(ep) if ep is not None else None

    def log(self, event: dict) -> None:
        event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **event}
        with self.ledger.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def craft_guide(self) -> str:
        path = self.spec_dir / self.spec.get("craft_guide", "pro_panel_craft.md")
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    def reference_data_urls(self) -> list[str]:
        urls = []
        for rel in self.spec.get("reference_images", []):
            path = (self.spec_dir / rel).resolve()
            if not path.exists():
                print(f"warning: reference image missing: {path}", file=sys.stderr)
                continue
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            urls.append(f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode())
        return urls

    def pages(self) -> list[dict]:
        return self.spec["pages"]

    def page(self, number: int) -> dict:
        for page in self.pages():
            if int(page["page"]) == number:
                return page
        sys.exit(f"page {number} not in spec")

    def page_png(self, number: int) -> Path:
        return self.latest / "pages" / f"page_{number:02d}.png"


def parse_pages(value: str | None, all_pages: list[int]) -> list[int]:
    if not value:
        return all_pages
    chosen: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            chosen.update(range(int(lo), int(hi) + 1))
        else:
            chosen.add(int(part))
    return [p for p in all_pages if p in chosen]


# ---------------------------------------------------------------- prompt build

def dialogue_label(item: dict) -> str:
    if "speaker" in item:
        return f'セリフ本文のみ: 「{item["text"]}」'
    kind = item.get("kind", "text")
    names = {"ui": "スマホUI文字", "caption": "キャプション", "monologue": "モノローグ", "sfx": "効果音"}
    return f'{names.get(kind, "文字")}: 「{item["text"]}」'


def text_render_instructions(item: dict) -> list[str]:
    """Per-item visual container rules for image generation (see docs/bubble_render_research.md)."""
    if item.get("speaker"):
        return [
            "Container type: spoken dialogue (セリフ).",
            "Draw a standard oval/ellipse speech balloon: solid black outline, white fill, same line weight as all text on the page.",
            "Add one sharp tail pointing clearly to the speaker's mouth. This is audible speech, not thought or narration.",
            "Do NOT use a cloud shape, rectangular caption box, or slanted narration frame for spoken dialogue.",
        ]
    kind = item.get("kind", "text")
    if kind == "monologue":
        return [
            "Container type: inner thought ONLY (思考 / 心の声) — not narration, not action result.",
            "Use ONLY when the character is thinking or deciding in this exact moment.",
            "Draw a cloud-shaped thought balloon, NOT an oval speech balloon and NOT a plain or slanted rectangular box.",
            "Connect to the thinking character's head with 3-5 small circular bubble dots (thought trail). No sharp mouth-pointing tail.",
            "Place near the thinker's head/face. Other characters cannot hear this text.",
            "Do NOT use this shape for factual results, time stamps, or retrospective narrator lines.",
        ]
    if kind == "caption":
        return [
            "Container type: narration / result / caption (地の文) — NOT inner thought.",
            "Use for time, place, action outcomes, factual observations, or retrospective narrator lines.",
            "Draw a slanted rectangular narration frame at a panel edge or corner: solid black outline, white fill, no tail, no bubble dots.",
            "Do NOT connect this box to any character's head. Do NOT use a cloud shape or oval speech balloon.",
            "If the art already shows the action, the caption states the result objectively — not as a thought bubble.",
        ]
    if kind == "sfx":
        return [
            "Container type: sound effect (効果音).",
            "Draw as stylized integrated lettering in the art, not inside a speech or narration box.",
        ]
    if kind == "ui":
        return [
            "Container type: on-screen UI text.",
            "Render only on the device screen surface, readable and large enough; not in a speech balloon.",
        ]
    return [
        "Container type: plain text.",
        "Use a consistent manga text style; do not mix with speech balloons unless the panel direction says otherwise.",
    ]


def build_prompt(project: Project, page: dict, model_hint: str, feedback: str | None = None) -> str:
    spec = project.spec
    page_no = int(page["page"])
    characters = "\n".join(f"- {value}" for value in spec["characters"].values())
    total = len(page["panels"])

    panel_lines: list[str] = []
    exact_texts: list[str] = []
    for idx, panel in enumerate(page["panels"], start=1):
        panel_lines.append(f"Panel {idx} of {total} ({panel['id']}):")
        pos = panel.get("pos")
        if pos:
            panel_lines.append(f"- Position on page: {POS_LABELS.get(pos, pos)}. This panel is read number {idx} of {total}.")
        else:
            panel_lines.append(f"- Reading order: this panel is read number {idx} of {total} in right-to-left flow.")
        panel_lines.append(f"- Art: {panel['art']}")
        if panel.get("dialogue"):
            panel_lines.append("- Text to render in this panel, exactly:")
            for item in panel["dialogue"]:
                panel_lines.append(f"  - {dialogue_label(item)}")
                for line in text_render_instructions(item):
                    panel_lines.append(f"    - {line}")
                if item.get("speaker"):
                    panel_lines.append(
                        "    - Tail target only: "
                        f"{item['speaker']}. Metadata; never render the speaker name or a colon in the balloon."
                    )
                exact_texts.append(item["text"])
        else:
            panel_lines.append("- Text: none. Keep this panel silent.")

    exact_block = "\n".join(f"- 「{t}」" for t in exact_texts) or "- No text on this page."
    checks = "\n".join(f"- {line}" for line in spec.get("quality_checks", []))
    craft = project.craft_guide()

    if project.is_carousel:
        return _build_prompt_carousel(project, page, page_no, characters, craft,
                                      panel_lines, exact_block, checks, feedback, model_hint)

    layout = LAYOUTS.get(page.get("layout", "five"), LAYOUTS["five"])
    return f"""You are creating page {page_no:02d} of a finished Japanese manga one-shot titled 「{spec['title']}」.

CRITICAL GENERATION SCOPE:
- ONE API call produces ONE complete vertical manga PAGE (not a poster, collage, or storyboard sheet).
- Aspect ratio 2:3, black-and-white, print-ready, clean panel borders.
- Japanese right-to-left reading order. Within every multi-panel row, the RIGHT panel is read before the LEFT panel. Never use Western left-to-right ordering.
- Follow the per-panel Position lines exactly; they define the page grid and the reading order.

TEXT RENDERING CONTRACT:
- Render the listed Japanese strings inside the image exactly as written: same particles, punctuation, ellipses, question marks.
- Render each allowed string at most once unless a panel direction explicitly repeats it.
- Do not invent any other text: no filler Japanese, fake UI labels, signage, numbers, watermarks, or random English.
- If smartphone UI text is small, enlarge the phone screen rather than shrinking the text.
- Speech balloons contain only the quoted speech. No speaker names, labels, colons, or brackets.
- TEXT CONTAINER CONSISTENCY (entire work): keep outline weight, white fill, and font style unified across every page.
- Spoken dialogue = oval balloon + sharp mouth tail. Inner thought (monologue) = cloud balloon + bubble-dot trail to head. Captions/results (caption) = slanted rectangle at panel edge, no tail, never connected to a character head. Never swap these shapes or semantic roles.
- Follow each panel's per-item Container type lines exactly; do not default all text to the same white box shape.

SCREEN PHYSICS (absolute rule):
- A display can only be seen from its front. NEVER draw screen content on the back of a laptop lid, the back of a phone, or any surface facing away from the character using it.
- When a character is reading a screen AND its text must be readable, use an over-the-shoulder or peek-over composition: the viewer looks at the screen from behind or beside the character, past their shoulder.
- Alternatively, devote the panel to the screen alone (a screen-only insert, character's hand at most), and show the character's face in an adjacent panel.
- If the character faces the viewer, their device's back faces the viewer and shows NO content.

GLOBAL ART STYLE:
{spec['global_art_prompt']}

CHARACTER CONTINUITY:
{characters}

PROFESSIONAL MANGA PANEL CRAFT (apply to every panel):
{craft}

PAGE TITLE / STORY ROLE:
{page['title']}

PAGE LAYOUT:
{layout}

EXACT JAPANESE TEXT STRINGS ALLOWED ON THIS PAGE:
{exact_block}

IN-PAGE PANEL DIRECTIONS:
{chr(10).join(panel_lines)}

QUALITY CHECK BEFORE FINAL IMAGE:
- Every panel communicates one clear main idea and follows its Position line.
- Reading order is unambiguous from upper right to lower left.
- Balloons never cover faces, hands, or phone screens, and tails point at the speaker.
- Spoken dialogue uses oval balloons with mouth tails only. Monologue uses cloud balloons with bubble trails only. Captions use slanted rectangles at panel edges only. These three must never look the same.
{checks}
{_feedback_block(feedback)}
Model hint: {model_hint}
"""


def _feedback_block(feedback: str | None) -> str:
    if not feedback:
        return ""
    return f"""
PREVIOUS ATTEMPT FAILED QA - FIX THESE EXACT PROBLEMS THIS TIME:
{feedback}
"""


CARD_ROLES = {
    "hook": "This is the FIRST card (hook): stop a scrolling reader within one second — a big "
            "expressive face, a question, or an instantly relatable moment. Absolutely no product "
            "pitch or ad-speak on this card.",
    "body": "This is a STORY card (body): advance the drama and make the reader swipe to the next "
            "card. Entertainment only — no product pitch, no slogans, no logos.",
    "cta": "This is the FINAL card (cta): the call-to-action lives here. Render only the CTA text "
           "given in the spec strings; keep the drawing warm and in-story, not a banner ad.",
}


def _build_prompt_carousel(project: Project, page: dict, page_no: int, characters: str,
                           craft: str, panel_lines: list[str], exact_block: str, checks: str,
                           feedback: str | None, model_hint: str) -> str:
    spec = project.spec
    cards = len(spec["pages"])
    total = len(page["panels"])
    # The whole pipeline (panel_lines, POS_LABELS, QA) assumes Japanese rtl reading;
    # an ltr branch here would contradict those shared blocks, so rtl is fixed.
    rd_line = ("within the card, the RIGHT panel of a row is read before the LEFT panel "
               "(Japanese right-to-left)")
    beat = page.get("beat", "body")
    if beat == "cta" and page_no != cards:
        beat = "body"  # mid-deck cta is a lint warn; never let the prompt claim "FINAL card" early
    role = CARD_ROLES.get(beat, CARD_ROLES["body"])
    return f"""You are creating card {page_no} of {cards} in a Japanese manga CAROUSEL AD for X (Twitter), titled 「{spec['title']}」.

CRITICAL GENERATION SCOPE:
- ONE API call produces ONE complete SQUARE carousel card (aspect ratio 1:1). Not a book page, not a poster, not a collage.
- The card is seen on a smartphone timeline: text must be large, bold, and high-contrast, readable without zooming.
- One card carries ONE main moment. This card has {total} panel(s); {rd_line}.
- The carousel advances by LEFT-to-RIGHT swipe between cards. Never draw page numbers, book gutters, or two-page-spread composition.
- {role}

TEXT RENDERING CONTRACT:
- Render the listed Japanese strings inside the image exactly as written: same particles, punctuation, ellipses, question marks.
- Render each allowed string at most once unless a panel direction explicitly repeats it.
- Do not invent any other text: no filler Japanese, fake UI labels, signage, numbers, watermarks, or random English.
- Speech balloons contain only the quoted speech. No speaker names, labels, colons, or brackets.
- TEXT CONTAINER CONSISTENCY (entire work): keep outline weight, white fill, and font style unified across every card.
- Spoken dialogue = oval balloon + sharp mouth tail. Inner thought (monologue) = cloud balloon + bubble-dot trail to head. Captions/results (caption) = slanted rectangle at panel edge, no tail, never connected to a character head. Never swap these shapes or semantic roles.
- Follow each panel's per-item Container type lines exactly; do not default all text to the same white box shape.

SCREEN PHYSICS (absolute rule):
- A display can only be seen from its front. NEVER draw screen content on the back of a laptop lid, the back of a phone, or any surface facing away from the character using it.
- When a character is reading a screen AND its text must be readable, use an over-the-shoulder or peek-over composition: the viewer looks at the screen from behind or beside the character, past their shoulder.
- Alternatively, devote the panel to the screen alone (a screen-only insert, character's hand at most), and show the character's face in an adjacent panel.
- If the character faces the viewer, their device's back faces the viewer and shows NO content.

GLOBAL ART STYLE:
{spec['global_art_prompt']}

CHARACTER CONTINUITY:
{characters}

PROFESSIONAL MANGA PANEL CRAFT (apply to every panel):
{craft}

CARD TITLE / STORY ROLE:
{page['title']}

EXACT JAPANESE TEXT STRINGS ALLOWED ON THIS CARD:
{exact_block}

IN-CARD PANEL DIRECTIONS:
{chr(10).join(panel_lines)}

QUALITY CHECK BEFORE FINAL IMAGE:
- Every panel communicates one clear main idea.
- Text is big enough to read on a phone without zooming.
- Balloons never cover faces or hands, and tails point at the speaker.
{checks}
{_feedback_block(feedback)}
Model hint: {model_hint}
"""


# ---------------------------------------------------------------- api

def call_api(messages_content, *, model: str, max_tokens: int, timeout: int = 300,
             retries: int = 2, image_config: dict | None = None) -> dict:
    return get_provider().generate(
        messages_content,
        model=model,
        max_tokens=max_tokens,
        timeout=timeout,
        retries=retries,
        image_config=image_config,
    )


def extract_image(result: dict) -> bytes:
    message = (result.get("choices") or [{}])[0].get("message") or {}
    images = message.get("images") or []
    if not images:
        raise RuntimeError(f"No image in response: {json.dumps(result, ensure_ascii=False)[:800]}")
    url = (images[0].get("image_url") or {}).get("url", "")
    match = re.match(r"data:image/[^;]+;base64,(.+)", url, re.DOTALL)
    if not match:
        raise RuntimeError("Expected base64 data URL image")
    return base64.b64decode(match.group(1))


def extract_text(result: dict) -> str:
    message = (result.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


# ---------------------------------------------------------------- generation

def backup_page(project: Project, number: int) -> None:
    src = project.page_png(number)
    if src.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(src, project.history / f"{stamp}_page_{number:02d}.png")


def generate_page(project: Project, number: int, args, *,
                  feedback: str | None = None, dest: Path | None = None) -> dict:
    page = project.page(number)
    prompt = build_prompt(project, page, args.model, feedback=feedback)
    (project.latest / "prompts" / f"page_{number:02d}.md").write_text(prompt, encoding="utf-8")

    content: list | str = prompt
    refs = project.reference_data_urls()
    if refs:
        content = [{"type": "text", "text": prompt + "\n\nThe attached image(s) are the official character reference sheet(s). Match faces, hairstyles, and outfits exactly."}]
        content += [{"type": "image_url", "image_url": {"url": u}} for u in refs]

    result = call_api(
        content, model=args.model, max_tokens=args.max_tokens,
        image_config={"aspect_ratio": "1:1" if project.is_carousel else "2:3",
                      "image_size": args.image_size},
    )
    (project.latest / "raw" / f"page_{number:02d}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    png = extract_image(result)
    if dest is None:
        backup_page(project, number)
        dest = project.page_png(number)
    dest.write_bytes(png)
    project.log({"cmd": "gen", "page": number, "model": args.model,
                 "cost": (result.get("usage") or {}).get("cost"),
                 "with_feedback": bool(feedback), "dest": dest.name})
    return {"page": number, "status": "generated", "dest": str(dest)}


def verdict_score(v: dict) -> tuple:
    rank = {"pass": 0, "warn": 1, "fail": 2}.get(v.get("verdict"), 3)
    issues = sum(len(v.get(k) or []) for k in ("text_errors", "identity_errors", "forbidden_found"))
    return (rank, issues)


def verdict_feedback(v: dict) -> str:
    lines = []
    for err in v.get("text_errors") or []:
        lines.append(f"- Text problem: {err}")
    for err in v.get("extra_text") or []:
        lines.append(f"- Remove invented text: {err}")
    if v.get("order_ok") is False:
        lines.append(f"- Reading order problem: {v.get('order_notes', '')}. Follow the per-panel Position lines exactly.")
    for err in v.get("identity_errors") or []:
        lines.append(f"- Character identity problem: {err}")
    for err in v.get("forbidden_found") or []:
        lines.append(f"- Forbidden element appeared: {err}")
    return "\n".join(lines)


def cmd_gen(project: Project, args) -> list[dict]:
    issues = run_lint(project)
    if issues["errors"] and not args.force:
        sys.exit(f"lint errors block generation (use --force to override):\n" +
                 "\n".join(issues["errors"]))
    numbers = parse_pages(args.pages, [int(p["page"]) for p in project.pages()])
    if not args.pages and not args.all_pages:
        sys.exit("Refusing paid generation of all pages without --all-pages. Use --pages N.")
    if args.candidates > 1:
        sys.exit("best-of-N selection requires vision QA, which is no longer API-backed. Use --candidates 1.")
    calls = len(numbers) * max(1, args.candidates)
    print(f"Paid image calls: {calls} ({','.join(map(str, numbers))} x{max(1, args.candidates)})")
    worker = generate_page
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(worker, project, n, args): n for n in numbers}
        for fut in concurrent.futures.as_completed(futures):
            n = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"page": n, "status": "error", "error": str(exc)}
            print(json.dumps(res, ensure_ascii=False), flush=True)
            results.append(res)
    cmd_assemble(project, args)
    return results


# ---------------------------------------------------------------- agent QA

QA_INSTRUCTIONS = """You are a strict but fair manga production QA inspector. You receive one generated manga page image and the JSON spec of what that page must contain. Work in two steps, then answer in JSON only.

STEP 1 - TRANSCRIBE THE GRID. Describe the actual panel grid you see, row by row from top to bottom. For each panel state: its row, whether it sits on the RIGHT half, LEFT half, or full width of the image (right/left = viewer's perspective of the image), and which spec panel its content matches (by the expected text or art summary). Put this in "grid" as ONE compact string, one short clause per row (e.g. "r1: full=P1 / r2: right=P2, left=P3 / r3: full=P4"). Keep it brief.

STEP 2 - JUDGE.
1. reading order: a Japanese manga reader reads rows top to bottom and, inside a row, the RIGHT panel before the LEFT panel. Walk the grid in that reader order and write down the sequence of matched spec panel numbers. order_ok is true if and only if that sequence is exactly 1..N ascending. The spec "pos" values are layout INTENT: if the panels landed in different rows/widths but the reader still encounters spec panels in ascending order, order_ok stays true (note the deviation in order_notes; it is a warn, not a fail).
2. text: every expected Japanese string appears, rendered correctly (particles, punctuation, ellipses). List each problem in text_errors. Ignore furigana-sized noise only if illegible.
3. extra_text: meaningful invented text NOT in the expected list. IGNORE printed page numbers and tiny plausible background signage; flag prominent invented text or nonsense glyphs.
4. identity: characters must match their identifiers from the spec. Flag wrong/missing identifiers or swaps between characters.
5. forbidden: report items from the forbidden list that actually appear.
6. anatomy: inspect every visible hand — fused or extra fingers, broken wrists, impossible grips on props (cans, phones, pens). Fingers naturally hidden behind a held object or by foreshortening are NOT defects; flag only visibly wrong anatomy. Report each genuinely bad hand in identity_errors with its panel.
7. screen physics: for every laptop, phone, or tablet, check which way the display faces. If screen content (text, UI, glow) is drawn on the BACK of a laptop lid or phone, or on a surface facing AWAY from the character who is supposedly reading it, that is a hard defect — report it in identity_errors and set verdict to fail.

Return ONLY a JSON object:
{"grid": "...", "reader_sequence": [1,2,3], "text_errors": ["..."], "extra_text": ["..."],
 "order_ok": true, "order_notes": "...", "identity_errors": ["..."], "forbidden_found": ["..."],
 "verdict": "pass" | "warn" | "fail"}

verdict=fail only when: an expected string is missing or wrongly rendered, the reader_sequence is not ascending, a main character is unidentifiable or swapped, or forbidden UI appears. Layout-slot deviations with correct reader_sequence, ignorable signage, and cosmetic issues are verdict=warn at most."""

QA_CAROUSEL_NOTE = """CONTEXT OVERRIDE: this image is ONE square card of an X (Twitter) ad carousel, NOT a book page. Cards advance left-to-right by swipe, but WITHIN this card panels still read in the spec order (rows top to bottom; the RIGHT panel of a row reads before the LEFT, Japanese rtl). Judge it as a standalone square card: page numbers, book gutters, or two-page-spread composition count as defects (report in extra_text or order_notes). Text must be readable at smartphone timeline size; flag tiny text as a text problem."""


def qa_payload(project: Project, page: dict) -> dict:
    return {
        "format": project.format,
        "page": int(page["page"]),
        "panel_sequence": [
            {
                "order": i + 1,
                "pos": panel.get("pos"),
                "art_summary": panel["art"][:200],
                "expected_text": [d["text"] for d in panel.get("dialogue", [])],
            }
            for i, panel in enumerate(page["panels"])
        ],
        "character_identifiers": project.spec["characters"],
        "forbidden": project.spec.get("quality_checks", []),
    }


def qa_request_content(project: Project, number: int, png_path: Path) -> tuple[str, dict]:
    page = project.page(number)
    instructions = QA_INSTRUCTIONS
    if project.is_carousel:
        instructions += "\n\n" + QA_CAROUSEL_NOTE
    payload = qa_payload(project, page)
    payload["image_path"] = str(png_path)
    content = (instructions
               + "\n\nUse the image_path below. Inspect the image directly with your available image-reading tool; do not call external APIs."
               + "\n\nSPEC:\n" + json.dumps(payload, ensure_ascii=False, indent=2))
    return content, payload


def qa_page(project: Project, number: int, *,
            png_path: Path | None = None, save: bool = True) -> dict:
    png_path = png_path or project.page_png(number)
    if not png_path.exists():
        return {"page": number, "verdict": "missing"}
    content, payload = qa_request_content(project, number, png_path)
    if save:
        (project.latest / "qa" / f"page_{number:02d}_request.md").write_text(content, encoding="utf-8")
        (project.latest / "qa" / f"page_{number:02d}_payload.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    verdict = {"page": number, "verdict": "agent_review_required",
               "image_path": str(png_path),
               "request": str(project.latest / "qa" / f"page_{number:02d}_request.md")}
    project.log({"cmd": "qa", "page": number, "mode": "agent_request",
                 "cost": 0, "file": png_path.name})
    if save:
        (project.latest / "qa" / f"page_{number:02d}.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    return verdict


def cmd_qa(project: Project, args) -> list[dict]:
    numbers = parse_pages(args.pages, [int(p["page"]) for p in project.pages()])
    verdicts: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(qa_page, project, n): n for n in numbers}
        for fut in concurrent.futures.as_completed(futures):
            n = futures[fut]
            try:
                v = fut.result()
            except Exception as exc:  # noqa: BLE001
                v = {"page": n, "verdict": "qa_error", "error": str(exc)}
            print(json.dumps(v, ensure_ascii=False), flush=True)
            verdicts.append(v)
    verdicts.sort(key=lambda v: v["page"])
    summary = {
        "mode": "agent_request",
        "pass": [v["page"] for v in verdicts if v.get("verdict") == "pass"],
        "warn": [v["page"] for v in verdicts if v.get("verdict") == "warn"],
        "fail": [v["page"] for v in verdicts if v.get("verdict") == "fail"],
        "other": [v["page"] for v in verdicts if v.get("verdict") not in ("pass", "warn", "fail")],
        "verdicts": verdicts,
    }
    (project.latest / "qa" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"QA: pass={summary['pass']} warn={summary['warn']} fail={summary['fail']} other={summary['other']}")
    return verdicts


def cmd_fix(project: Project, args) -> None:
    numbers = parse_pages(args.pages, [int(p["page"]) for p in project.pages()])
    needs_human: list[int] = []
    for number in numbers:
        verdict_path = project.latest / "qa" / f"page_{number:02d}.json"
        if not verdict_path.exists():
            print(f"page {number}: no QA verdict found. Run qa and have an agent write {verdict_path}.", flush=True)
            needs_human.append(number)
            continue
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        attempt = 0
        if verdict.get("verdict") == "fail" and attempt < args.attempts:
            attempt = 1
            feedback = verdict_feedback(verdict)
            print(f"page {number}: fail -> regenerating with feedback (attempt {attempt})", flush=True)
            print(feedback[:500], flush=True)
            generate_page(project, number, args, feedback=feedback)
            qa_page(project, number)
            print(f"page {number}: regenerated. Agent QA request written; re-run QA review before further fixes.", flush=True)
            needs_human.append(number)
        elif verdict.get("verdict") == "fail":
            needs_human.append(number)
        print(f"page {number}: final verdict {verdict.get('verdict')}", flush=True)
        project.log({"cmd": "fix", "page": number, "attempts": attempt,
                     "final": verdict.get("verdict")})
    if needs_human:
        print(f"ESCALATION: pages {needs_human} need agent QA before additional automatic fixes.")
    cmd_assemble(project, args)


# ---------------------------------------------------------------- assemble

def _font(size: int):
    for cand in ("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
                 "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"):
        if Path(cand).exists():
            return ImageFont.truetype(cand, size)
    return ImageFont.load_default()


def cmd_assemble(project: Project, args) -> None:
    paths = sorted((project.latest / "pages").glob("page_*.png"))
    if not paths:
        print("no pages to assemble")
        return
    if project.is_carousel:
        _assemble_carousel(project, paths)
        return
    thumbs = []
    for path in paths:
        img = Image.open(path).convert("RGB")
        img.thumbnail((240, 360))
        canvas = Image.new("RGB", (260, 390), "white")
        canvas.paste(img, ((260 - img.width) // 2, 10))
        ImageDraw.Draw(canvas).text((12, 360), path.stem, fill="black", font=_font(22))
        thumbs.append(canvas)
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 260, rows * 390), "white")
    for i, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((i % cols) * 260, (i // cols) * 390))
    sheet.save(project.latest / "contact_sheet.png")
    images = [Image.open(p).convert("RGB") for p in paths]
    images[0].save(project.latest / "book.pdf", save_all=True, append_images=images[1:])
    print(f"assembled {len(paths)} pages -> {project.latest}")


def _assemble_carousel(project: Project, paths: list[Path]) -> None:
    """Cards in swipe order, left to right, one horizontal strip. No book.pdf."""
    thumbs = []
    for path in paths:
        img = Image.open(path).convert("RGB")
        img.thumbnail((360, 360))
        canvas = Image.new("RGB", (380, 410), "white")
        canvas.paste(img, ((380 - img.width) // 2, 10))
        ImageDraw.Draw(canvas).text((12, 378), path.stem, fill="black", font=_font(20))
        thumbs.append(canvas)
    sheet = Image.new("RGB", (len(thumbs) * 380, 410), "white")
    for i, thumb in enumerate(thumbs):
        sheet.paste(thumb, (i * 380, 0))
    sheet.save(project.latest / "contact_sheet.png")
    ad_copy = project.spec.get("ad_copy")
    if ad_copy:
        (project.latest / "ad_copy.txt").write_text(ad_copy + "\n", encoding="utf-8")
    else:
        (project.latest / "ad_copy.txt").unlink(missing_ok=True)
    print(f"assembled {len(thumbs)} cards (swipe order L->R) -> {project.latest}")


# ---------------------------------------------------------------- charsheet

def cmd_charsheet(project: Project, args) -> None:
    spec = project.spec
    characters = "\n".join(f"- {k}: {v}" for k, v in spec["characters"].items())
    prompt = f"""Create ONE character reference sheet image for a Japanese manga titled 「{spec['title']}」.

STYLE: {spec['global_art_prompt']}

Draw every character listed below, standing full-body, front view, on a single clean white sheet, arranged in a row, with a small neutral-expression face close-up above each figure. Keep each character's listed identifiers exact and visually distinct. No text labels, no logos.

CHARACTERS:
{characters}
"""
    result = call_api(prompt, model=args.model, max_tokens=args.max_tokens,
                      image_config={"aspect_ratio": "3:2", "image_size": args.image_size})
    out = project.spec_dir / "character_sheet.png"
    out.write_bytes(extract_image(result))
    print(f"character sheet -> {out}")
    print('add to spec: "reference_images": ["character_sheet.png"]')


# ---------------------------------------------------------------- lint

POS_ORDER = {"top-wide": 0, "row1-right": 1, "row1-left": 2, "row2-right": 3, "row2-left": 4,
             "row3-right": 5, "row3-left": 6, "middle-wide": 7, "bottom-wide": 8}


BEAT_RATIOS = {"ki": 1 / 4, "sho": 1 / 4, "ten": 1 / 3, "ketsu": 1 / 8}
AD_BEATS = ("hook", "body", "cta")
BEAT_NAMES = {"ki": "起", "sho": "承", "ten": "転", "ketsu": "結"}


def lint_beats(project: Project, warnings: list[str], errors: list[str]) -> None:
    """If pages carry a `beat` tag, check allocation against the craft ratios
    (起1/4 承1/4 転1/3 結1/8; climax gets pages, the ending stays compact)."""
    beats = [p.get("beat") for p in project.pages()]
    if not any(beats):
        return
    total = len(beats)
    counts: dict[str, int] = {}
    for i, b in enumerate(beats):
        if b is None:
            warnings.append(f"P{int(project.pages()[i]['page'])}: beat tag missing while others are tagged")
        elif b not in BEAT_RATIOS:
            errors.append(f"P{int(project.pages()[i]['page'])}: unknown beat '{b}' (use ki/sho/ten/ketsu)")
        else:
            counts[b] = counts.get(b, 0) + 1
    order = [b for b in beats if b in BEAT_RATIOS]
    canonical = sorted(order, key=lambda b: ["ki", "sho", "ten", "ketsu"].index(b))
    if order != canonical:
        errors.append("beat order is not 起→承→転→結 across pages")
    for beat, ratio in BEAT_RATIOS.items():
        got = counts.get(beat, 0)
        ideal = ratio * total
        if got and abs(got - ideal) > max(1.5, ideal * 0.5):
            warnings.append(f"beat {BEAT_NAMES[beat]}: {got}p vs guideline {ideal:.1f}p "
                            f"(起1/4 承1/4 転1/3 結1/8; クライマックスに厚く、オチは短く)")
    if counts.get("ketsu", 0) > counts.get("ten", 1):
        warnings.append("結 is longer than 転; the craft guideline is the opposite (tezuka: tight endings)")


def x_weighted_len(text: str) -> int:
    """X's weighted character count: Latin and other narrow ranges count 1, CJK etc. count 2.
    Ranges follow X's twitter-text config (0-4351, 8192-8205, 8208-8223, 8242-8247 = weight 1).
    Approximation: no NFC normalization, no URL-as-23 rule (fine for plain ad copy)."""
    light = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))
    return sum(1 if any(lo <= ord(ch) <= hi for lo, hi in light) else 2 for ch in text)


def lint_carousel(project: Project, warnings: list[str], errors: list[str]) -> None:
    """X carousel ad rules (spec: docs/superpowers/specs/2026-06-11-x-carousel-format-design.md).
    X ads spec (verified 2026-06): 1:1 cards, 2-6 slides, body text 280 weighted chars."""
    pages = project.pages()
    n_cards = len(pages)
    if not 2 <= n_cards <= 6:
        errors.append(f"x-carousel needs 2-6 cards, got {n_cards} (X ads spec)")
    beats = [p.get("beat") for p in pages]
    for p, beat in zip(pages, beats):
        if beat is None:
            warnings.append(f"C{int(p['page'])}: beat tag missing (use hook/body/cta)")
        elif beat not in AD_BEATS:
            errors.append(f"C{int(p['page'])}: unknown beat '{beat}' for x-carousel (use hook/body/cta)")
    if beats and beats[0] != "hook":
        warnings.append("card 1 is not beat 'hook'; the first card must stop the scroll")
    if beats and beats[-1] != "cta":
        warnings.append("last card is not beat 'cta'; the CTA belongs on the final card")
    for p, beat in zip(pages[:-1], beats[:-1]):
        if beat == "cta":
            warnings.append(f"C{int(p['page'])}: 'cta' before the final card; "
                            "ad-speak mid-deck kills read-through")
    width, height = project.spec.get("page_width"), project.spec.get("page_height")
    if width and height and width != height:
        warnings.append(f"canvas {width}x{height} is not square; X 1:1 cards should be >=800x800 square")
    ad_copy_weight = x_weighted_len(project.spec.get("ad_copy") or "")
    if ad_copy_weight > 280:
        errors.append(f"ad_copy is {ad_copy_weight} weighted chars "
                      "(X limit 280; CJK counts as 2, so ~140 full-width chars)")
    # Carousel counterpart of lint_brand: the brand must exist, but ONLY on the
    # final (cta) card — ad-speak before that kills read-through.
    last_card = max((int(p["page"]) for p in pages), default=0)
    for brand in project.spec.get("brand_strings", []):
        hits = [int(p["page"]) for p in pages for panel in p["panels"]
                for d in panel.get("dialogue", []) if brand in d.get("text", "")]
        if not hits:
            errors.append(f"brand 「{brand}」 never appears in any dialogue/UI text")
        for hit in hits:
            if hit != last_card:
                warnings.append(f"C{hit}: brand 「{brand}」 appears before the final card; "
                                "keep all ad-speak on the cta card")


def lint_brand(project: Project, warnings: list[str], errors: list[str]) -> None:
    """A trailer manga must stamp the brand more than once, and not only on the
    final page. Checks spec authoring; render-level dropout is the QA's job."""
    brands = project.spec.get("brand_strings", [])
    if not brands:
        return
    pages = project.pages()
    last = max(int(p["page"]) for p in pages)
    for brand in brands:
        hits = [int(p["page"]) for p in pages for panel in p["panels"]
                for d in panel.get("dialogue", []) if brand in d.get("text", "")]
        if not hits:
            errors.append(f"brand 「{brand}」 never appears in any dialogue/UI text")
        elif len(hits) < 2:
            warnings.append(f"brand 「{brand}」 appears only once (P{hits[0]}); an ad needs at least 2 stamps")
        elif all(p == last for p in hits):
            warnings.append(f"brand 「{brand}」 appears only on the final page; stamp it at the discovery scene too")


def lint_series_episode(project: Project, warnings: list[str], errors: list[str]) -> None:
    """Serialized episode rules (requires format: series-episode)."""
    ep_num = project.episode_number()
    if ep_num is None:
        errors.append("series-episode requires an integer 'episode' field")
        return

    ctx = project.series_context()
    if ctx is None:
        warnings.append("series-episode: series.json not found (set series_root or place series.json upstream)")
        return

    meta = ctx.episode_meta(ep_num)
    if meta is None:
        errors.append(f"episode {ep_num} not listed in {ctx.path}")
    else:
        expected = ctx.resolve_spec_path(meta)
        if expected.resolve() != project.spec_path.resolve():
            warnings.append(
                f"spec path mismatch: series.json points to {expected}, linting {project.spec_path}")

    if ep_num >= 2:
        checks = " ".join(project.spec.get("quality_checks", []))
        if not any(hint in checks for hint in CONTINUITY_HINTS):
            warnings.append(
                f"ep{ep_num}: quality_checks have no continuity/motif tracking hint "
                f"(e.g. trackable, 追跡, 同一); consider adding cross-page motif lines")

        prev_spec = ctx.load_episode_spec(ep_num - 1)
        if prev_spec:
            prev_count = len(prev_spec.get("characters", {}))
            curr_count = len(project.spec.get("characters", {}))
            if curr_count - prev_count >= 2:
                warnings.append(
                    f"ep{ep_num}: {curr_count} characters vs ep{ep_num - 1}'s {prev_count} "
                    "(guideline: at most 1 new named character per episode)")

    is_final = ctx.is_final_episode(ep_num)
    has_teaser = has_next_episode_teaser(project, ep_num + 1)
    if is_final:
        if has_teaser:
            warnings.append(f"ep{ep_num} is the series finale but the last page has a next-episode teaser")
    elif not has_teaser:
        last = final_page(project)
        label = f"P{int(last['page'])}" if last else "last page"
        warnings.append(
            f"ep{ep_num}: {label} lacks a next-episode teaser "
            f"(expect 「続く」 or 第{ep_num + 1}話 in final-page dialogue)")


def lint_series_cross(ctx: SeriesContext, warnings: list[str], errors: list[str]) -> None:
    """Cross-episode checks when linting via --series-root."""
    nums = ctx.episode_numbers()
    if not nums:
        errors.append("series.json has no episodes")
        return
    expected = list(range(min(nums), max(nums) + 1))
    missing = [n for n in expected if n not in nums]
    if missing:
        warnings.append(f"episode number gap in series.json: missing {missing}")

    prev_count: int | None = None
    for ep in ctx.episodes():
        n = int(ep["number"])
        spec_path = ctx.resolve_spec_path(ep)
        if not spec_path.exists():
            errors.append(f"ep{n}: spec missing at {spec_path}")
            continue
        spec = load_episode_spec_from_path(spec_path)
        count = len(spec.get("characters", {}))
        if prev_count is not None and count - prev_count >= 2:
            warnings.append(
                f"ep{n}: character count jumped from {prev_count} to {count} "
                "(guideline: at most 1 new named character per episode)")
        prev_count = count


def run_lint(project: Project) -> dict:
    """Deterministic feedforward checks. Free, instant, runs before paid calls."""
    errors: list[str] = []
    warnings: list[str] = []
    forbidden = project.spec.get("forbidden_strings", [])
    if project.format not in VALID_FORMATS:
        errors.append(f"unknown format '{project.format}' (use 'book', 'x-carousel', or 'series-episode')")
    if project.is_carousel:
        lint_carousel(project, warnings, errors)
    else:
        # lint_brand's "2+ stamps, not only the final page" guidance is written for
        # trailer-manga books; the carousel counterpart lives in lint_carousel.
        lint_beats(project, warnings, errors)
        lint_brand(project, warnings, errors)
        if project.is_series_episode:
            lint_series_episode(project, warnings, errors)
    if project.spec.get("episode") is not None and project.format == "book":
        warnings.append(
            "spec has 'episode' but format is 'book'; use format: series-episode for serialized manga")

    for page in project.pages():
        n = int(page["page"])
        panels = page["panels"]
        texts: list[str] = []

        last_order = -1
        for i, panel in enumerate(panels):
            pos = panel.get("pos")
            if pos is None:
                if not project.is_carousel:
                    warnings.append(f"P{n} {panel['id']}: no pos slot (ordering left to the model)")
            elif pos not in POS_ORDER:
                errors.append(f"P{n} {panel['id']}: unknown pos '{pos}'")
            else:
                order = POS_ORDER[pos]
                if order < last_order:
                    errors.append(f"P{n} {panel['id']}: pos '{pos}' goes backwards in reading order")
                last_order = order

            for item in panel.get("dialogue", []):
                text = item.get("text", "")
                if not text.strip():
                    errors.append(f"P{n} {panel['id']}: empty dialogue text")
                if text != text.strip():
                    warnings.append(f"P{n} {panel['id']}: leading/trailing whitespace in 「{text}」")
                for bad in forbidden:
                    if bad in text:
                        errors.append(f"P{n} {panel['id']}: forbidden string 「{bad}」 in dialogue")
                texts.append(text)

            # The single most expensive failure in practice: a spoken question in the
            # right panel answered by speech in the left panel of the same row. Image
            # models swap these often; if swapped, the page must be rerolled.
            if i + 1 < len(panels):
                nxt = panels[i + 1]
                pair = (panel.get("pos", ""), nxt.get("pos", ""))
                side_by_side = pair in (("row1-right", "row1-left"), ("row2-right", "row2-left"),
                                        ("row3-right", "row3-left"))
                q = any("speaker" in d and d["text"].rstrip().endswith(("？", "?", "でしょ", "かよ"))
                        for d in panel.get("dialogue", []))
                a = any("speaker" in d for d in nxt.get("dialogue", []))
                if side_by_side and q and a:
                    warnings.append(
                        f"P{n} {panel['id']}->{nxt['id']}: question/answer split across a side-by-side row; "
                        "models often swap these. Consider making the question panel top-wide or merging.")

        dupes = {t for t in texts if texts.count(t) > 1}
        for d in dupes:
            warnings.append(f"P{n}: string 「{d}」 appears {texts.count(d)}x on the same page (text contract risk)")
        if len(texts) > 12:
            errors.append(f"P{n}: {len(texts)} text strings on one page; rendering will degrade (max 12)")
        elif len(texts) > 8:
            warnings.append(f"P{n}: {len(texts)} text strings on one page; consider trimming (soft cap 8)")

        # Craft limits (manga_craft_research.md): one balloon = 3-4 lines x 10-11 chars,
        # whole page around 150 chars. Beyond that, readability drops measurably.
        for panel in panels:
            for item in panel.get("dialogue", []):
                if "speaker" in item and len(item["text"]) > 40:
                    warnings.append(f"P{n} {panel['id']}: balloon is {len(item['text'])} chars 「{item['text'][:20]}…」; "
                                    "split or trim (3-4 lines x 10-11 chars is the readable limit)")
        page_chars = sum(len(t) for t in texts)
        if project.is_carousel:
            if page_chars > 120:
                errors.append(f"C{n}: {page_chars} chars on one card (mobile ad limit 120); cut text hard")
            elif page_chars > 80:
                warnings.append(f"C{n}: {page_chars} chars on one card (soft cap 80; a card must read in one swipe-pause)")
            if len(panels) > 4:
                warnings.append(f"C{n}: {len(panels)} panels on one card; 1-3 panels per card reads best on a phone")
        else:
            if page_chars > 150:
                warnings.append(f"P{n}: {page_chars} total chars on one page (guideline ~150); cut words or let the art speak")
            if len(panels) > 7:
                warnings.append(f"P{n}: {len(panels)} panels on one page; reading cost is high, consider merging beats")

    return {"errors": errors, "warnings": warnings}


def cmd_lint(project: Project | None, args) -> None:
    if getattr(args, "series_root", None):
        cmd_lint_series(Path(args.series_root), args)
        return
    if project is None:
        sys.exit("lint requires --spec or --series-root")
    issues = run_lint(project)
    for w in issues["warnings"]:
        print(f"warn : {w}")
    for e in issues["errors"]:
        print(f"ERROR: {e}")
    print(f"lint: {len(issues['errors'])} errors, {len(issues['warnings'])} warnings")
    if issues["errors"]:
        sys.exit(1)


def cmd_lint_series(series_root: Path, args) -> None:
    ctx = SeriesContext.from_root(series_root)
    cross_errors: list[str] = []
    cross_warnings: list[str] = []
    lint_series_cross(ctx, cross_warnings, cross_errors)

    total_errors = len(cross_errors)
    total_warnings = len(cross_warnings)
    for w in cross_warnings:
        print(f"warn : {w}")
    for e in cross_errors:
        print(f"ERROR: {e}")

    for ep in ctx.episodes():
        n = int(ep["number"])
        spec_path = ctx.resolve_spec_path(ep)
        print(f"\n--- ep{n}: {spec_path} ---")
        if not spec_path.exists():
            continue
        project = Project(spec_path)
        issues = run_lint(project)
        for w in issues["warnings"]:
            print(f"warn : {w}")
        for e in issues["errors"]:
            print(f"ERROR: {e}")
        print(f"lint ep{n}: {len(issues['errors'])} errors, {len(issues['warnings'])} warnings")
        total_errors += len(issues["errors"])
        total_warnings += len(issues["warnings"])

    print(f"\nseries lint: {total_errors} errors, {total_warnings} warnings")
    if total_errors:
        sys.exit(1)


# ---------------------------------------------------------------- editorial review

REVIEW_INSTRUCTIONS = """あなたはプロの漫画編集者です。読者コストを下げながら漫画としての快感を増やす編集者として、
ネーム（storyboard JSON）を画像生成の前にレビューします。添付の編集原則ドキュメントを判断基準として使ってください。

重点的に見るもの:
1. フック: 最初の5ページまでに読者の興味が作れているか。冒頭に大きい絵・顔の大きいコマがあるか
2. 変化量: 1ページ目と最終ページで何が変わるか。物理・感情・関係性・評価の複数軸か
3. キャラ: 主人公を好きになる最初の場面はどこか。価値観が行動で見えるか。メイン4人以下・問題2つ以下か
4. ページ配分: 起承転結が概ね 起1/4・承1/4・転1/3・結1/8 に収まっているか。クライマックスにページを使い、オチは短いか
5. ヒキとメクリ: 各ページの末尾コマは「続きが気になる」か。次ページ先頭はその受けになっているか（単ページ閲覧前提）
6. 大ゴマ配分: 見せ場級のコマ（wide/大ゴマ）が終盤に偏らず、序盤・中盤にもあるか
7. 読者コスト: 1コマ1主情報か。絵とセリフが同じ情報を指しているか。説明セリフを減らせる関係性か
8. 読み切りの満足: 読み終えたあと読者が主人公を好きになっているか
9. セリフ術: 説明セリフ（感情のこもらない情報伝達）がないか。キャラが「言いたいこと」を言っているか。
   反復フレーズ（テーマの刷り込み）が設計されているか。長ゼリフは分割できるか
10. 裏付け（ご都合主義チェック）: 登場人物の言動・知識・展開に作中の根拠があるか。
   「なぜ知ってる？」「なぜできる？」と読者が思う箇所を必ず指摘する

JSONのみで返答:
{"overall": {"hook": "...", "change": "...", "character": "...", "page_allocation": "...",
  "hiki_mekuri": "...", "big_panel_distribution": "...", "reader_cost": "..."},
 "page_notes": [{"page": 1, "notes": ["..."]}],
 "top_fixes": [{"priority": 1, "page": 3, "issue": "...", "fix": "..."}],
 "verdict": "ship" | "revise"}

top_fixesは効果の大きい順に最大5件。具体的な直し方まで書く。問題のないページはpage_notesに含めない。
verdict=reviseは「生成前に直すべき構造問題がある」場合のみ。"""

SERIES_EPISODE_REVIEW_INSTRUCTIONS = """あなたはプロの漫画編集者です。連載漫画の**1話分**のネーム（storyboard JSON）を、
画像生成の前にレビューします。添付の編集原則ドキュメントを判断基準として使ってください。
これはシリーズ全体の最終話ではなく、**単話の読み切り満足ではなく「続きが欲しい」**で評価する。

重点的に見るもの:
1. フック: 最初の5ページまでに読者の興味が作れているか。冒頭に大きい絵・顔の大きいコマがあるか
2. 話単位の変化量: payload の emotional_delta が、この話の1ページ目↔最終ページで達成されているか
3. 前話からの連続性: prev_episode_final がある場合、前話末の状態から自然に始まっているか
4. キャラ: 価値観が行動で見えるか。新キャラ登場は1人以内か（ep2以降）
5. ページ配分: 起承転結が概ね 起1/4・承1/4・転1/3・結1/8 に収まっているか
6. ヒキとメクリ: 各ページ末尾は「続きが気になる」か。最終話でなければ最終ページは次話への問いを残す
7. 大ゴマ配分: 見せ場級のコマが序盤・中盤にもあるか
8. 読者コスト: 1コマ1主情報か。説明セリフを減らせる関係性か
9. セリフ術: キャラが「言いたいこと」を言っているか。反復フレーズが設計されているか
10. 裏付け: 登場人物の言動・知識に作中の根拠があるか

読み切りの完結満足は**見ない**（シリーズ arc は series-review で評価する）。

JSONのみで返答:
{"overall": {"hook": "...", "emotional_delta": "...", "continuity": "...", "character": "...",
  "page_allocation": "...", "hiki_mekuri": "...", "episode_cliffhanger": "...", "reader_cost": "..."},
 "page_notes": [{"page": 1, "notes": ["..."]}],
 "top_fixes": [{"priority": 1, "page": 3, "issue": "...", "fix": "..."}],
 "verdict": "ship" | "revise"}

top_fixesは効果の大きい順に最大5件。具体的な直し方まで書く。問題のないページはpage_notesに含めない。
verdict=reviseは「生成前に直すべき構造問題がある」場合のみ。"""

SERIES_REVIEW_INSTRUCTIONS = """あなたはプロの漫画編集者です。連載漫画シリーズ全体を、全話のネーム要約と
story bible / 翻案設計を見比べてレビューします。添付の series_review_checklist と
series_principles.md を最優先の判断基準にしてください。

重点的に見るもの:
1. 各話の emotional_delta が adaptation_design / series.json と一致しているか
2. 反復モチーフの初出・変質が story bible の表と整合しているか
3. 話間の設定矛盾（性別・外見・禁止事項・時系列）
4. 各話ヒキが次話の premise と接続しているか
5. シリーズ arc: 第1話開始状態 ↔ 最終話終了状態の変化量
6. 1話1問題の原則が守られているか

JSONのみで返答:
{"overall": {"arc": "...", "motifs": "...", "continuity": "...", "episode_hooks": "..."},
 "episode_notes": [{"episode": 1, "notes": ["..."]}],
 "top_fixes": [{"priority": 1, "episode": 2, "issue": "...", "fix": "..."}],
 "verdict": "ship" | "revise"}

top_fixesは効果の大きい順に最大5件。verdict=reviseはシリーズ全体で生成前に直すべき構造問題がある場合のみ。"""


def repo_docs_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "docs"


def repo_templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def review_principles(project: Project | None = None) -> str:
    names = ["manga_principles.md", "jump_manga_school_principles.md",
             "review_checklist.md", "manga_craft_research.md"]
    if project is not None and project.is_carousel:
        names.append("x_ads_manga_principles.md")
    if project is not None and project.is_series_episode:
        names.append("series_principles.md")
    docs = []
    for name in names:
        path = repo_docs_dir() / name
        if path.exists():
            docs.append(f"===== {name} =====\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(docs)


def review_instructions(project: Project) -> str:
    if project.is_carousel:
        return REVIEW_INSTRUCTIONS
    if project.is_series_episode:
        return SERIES_EPISODE_REVIEW_INSTRUCTIONS
    return REVIEW_INSTRUCTIONS


def review_payload(project: Project) -> dict:
    spec = project.spec
    payload: dict = {
        "title": spec["title"],
        "format": project.format,
        "page_count": len(spec["pages"]),
        "characters": spec["characters"],
        "pages": [
            {
                "page": int(p["page"]), "title": p.get("title"), "layout": p.get("layout"),
                "beat": p.get("beat"),
                "panels": [
                    {"pos": pn.get("pos"), "art": pn["art"],
                     "dialogue": pn.get("dialogue", [])}
                    for pn in p["panels"]
                ],
            }
            for p in spec["pages"]
        ],
    }
    if not project.is_series_episode:
        return payload

    ep_num = project.episode_number()
    payload["episode"] = ep_num
    ctx = project.series_context()
    if ctx is not None and ep_num is not None:
        payload["series_title"] = ctx.title
        payload["series_slug"] = ctx.slug
        meta = ctx.episode_meta(ep_num)
        if meta and meta.get("emotional_delta"):
            payload["emotional_delta"] = meta["emotional_delta"]
        if ep_num >= 2:
            prev_final = ctx.prev_episode_final_page(ep_num)
            if prev_final:
                payload["prev_episode_final"] = prev_final
        payload["is_series_finale"] = ctx.is_final_episode(ep_num)
    return payload


def series_review_payload(ctx: SeriesContext) -> dict:
    episodes_summary = []
    for ep in ctx.episodes():
        n = int(ep["number"])
        spec_path = ctx.resolve_spec_path(ep)
        entry: dict = {
            "number": n,
            "title": ep.get("title", ""),
            "slug": ep.get("slug", ""),
            "emotional_delta": ep.get("emotional_delta", ""),
            "spec": str(spec_path),
        }
        if spec_path.exists():
            project = Project(spec_path)
            entry["page_count"] = len(project.pages())
            entry["characters"] = list(project.spec.get("characters", {}).keys())
            last = final_page(project)
            if last:
                entry["final_page_dialogue"] = page_dialogue_texts(last)
        episodes_summary.append(entry)
    return {
        "series_title": ctx.title,
        "series_slug": ctx.slug,
        "episode_count": len(episodes_summary),
        "episodes": episodes_summary,
    }


def review_request_content(project: Project, payload: dict) -> str:
    carousel_note = ""
    if project.is_carousel:
        carousel_note = ("\n\n===== フォーマット注意 =====\n"
                         "これはX広告カルーセル（1:1カード、2〜6枚、カード送りは左→右スワイプ）のネームであり、"
                         "冊子ではない。起承転結のページ配分基準は適用せず、hook→body→cta で評価する。"
                         "x_ads_manga_principles.md の「reviewで必ず見るもの」を最優先の観点にする。")
    series_note = ""
    if project.is_series_episode:
        series_note = ("\n\n===== フォーマット注意 =====\n"
                       "これは連載漫画の1話分のネームである。"
                       "読み切りの完結満足ではなく、話単位の変化量・前話連続性・次話ヒキで評価する。")
    return (review_instructions(project) + carousel_note + series_note
            + "\n\n===== 編集原則ドキュメント =====\n" + review_principles(project)
            + "\n\n===== ネーム(storyboard) =====\n" + json.dumps(payload, ensure_ascii=False, indent=2))


def series_review_request_content(ctx: SeriesContext, payload: dict) -> str:
    parts = [SERIES_REVIEW_INSTRUCTIONS]
    checklist = repo_templates_dir() / "series_review_checklist.md"
    if checklist.exists():
        parts.append("===== series_review_checklist.md =====\n" + checklist.read_text(encoding="utf-8"))
    parts.append("===== series_principles.md =====\n"
                   + (repo_docs_dir() / "series_principles.md").read_text(encoding="utf-8"))
    bible = ctx.story_bible_path()
    if bible:
        parts.append(f"===== story_bible ({bible.name}) =====\n" + bible.read_text(encoding="utf-8"))
    design = ctx.adaptation_design_path()
    if design:
        parts.append(f"===== adaptation_design ({design.name}) =====\n" + design.read_text(encoding="utf-8"))
    parts.append("===== 全話要約 =====\n" + json.dumps(payload, ensure_ascii=False, indent=2))
    return "\n\n".join(parts)


def cmd_series_review(args) -> None:
    ctx = SeriesContext.from_root(Path(args.series_root))
    payload = series_review_payload(ctx)
    content = series_review_request_content(ctx, payload)
    out_dir = ctx.series_output_dir()
    request_path = out_dir / "series_review_request.md"
    payload_path = out_dir / "series_review_payload.json"
    request_path.write_text(content, encoding="utf-8")
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"series review request -> {request_path}")
    print(f"series review payload -> {payload_path}")
    print("OpenRouter not used. Have a coding agent read series_review_request.md "
          "and write series_review.json alongside.")


def cmd_review(project: Project, args) -> None:
    payload = review_payload(project)
    content = review_request_content(project, payload)
    request_path = project.latest / "qa" / "review_request.md"
    payload_path = project.latest / "qa" / "review_payload.json"
    request_path.write_text(content, encoding="utf-8")
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    project.log({"cmd": "review", "mode": "agent_request", "cost": 0})
    print(f"review request -> {request_path}")
    print(f"review payload -> {payload_path}")
    print("OpenRouter not used. Have a coding agent read review_request.md and write qa/review.json.")


# ---------------------------------------------------------------- prompts only

def cmd_prompts(project: Project, args) -> None:
    numbers = parse_pages(args.pages, [int(p["page"]) for p in project.pages()])
    for n in numbers:
        prompt = build_prompt(project, project.page(n), args.model)
        (project.latest / "prompts" / f"page_{n:02d}.md").write_text(prompt, encoding="utf-8")
    print(f"wrote {len(numbers)} prompts -> {project.latest / 'prompts'}")


# ---------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description="Spec-driven manga production harness")
    parser.add_argument("command", choices=["lint", "review", "series-review", "prompts", "gen",
                                            "qa", "fix", "assemble", "charsheet"])
    parser.add_argument("--spec", help="Path to storyboard spec JSON")
    parser.add_argument("--series-root", help="Path to directory containing series.json (lint all episodes; series-review)")
    parser.add_argument("--pages", help="e.g. 1,5,8-10 (default: all)")
    parser.add_argument("--all-pages", action="store_true")
    parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", DEFAULT_GEN_MODEL))
    parser.add_argument("--image-size", default=os.environ.get("OPENROUTER_IMAGE_SIZE", "1K"), choices=["1K", "2K", "4K"])
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("OPENROUTER_MAX_TOKENS", DEFAULT_MAX_TOKENS)))
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--attempts", type=int, default=2, help="fix: max regen attempts per page")
    parser.add_argument("--candidates", type=int, default=1, help="gen: best-of-N QA-scored selection")
    parser.add_argument("--force", action="store_true", help="gen: proceed despite lint errors")
    args = parser.parse_args()

    if args.command == "series-review":
        if not args.series_root:
            sys.exit("series-review requires --series-root")
        if args.spec:
            sys.exit("series-review does not take --spec")
        cmd_series_review(args)
        return 0

    if args.command == "lint" and args.series_root:
        if args.spec:
            sys.exit("lint: use --spec or --series-root, not both")
        cmd_lint(None, args)
        return 0

    if not args.spec:
        sys.exit(f"{args.command} requires --spec")

    project = Project(Path(args.spec))
    {
        "lint": cmd_lint,
        "review": cmd_review,
        "prompts": cmd_prompts,
        "gen": cmd_gen,
        "qa": cmd_qa,
        "fix": cmd_fix,
        "assemble": cmd_assemble,
        "charsheet": cmd_charsheet,
    }[args.command](project, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
