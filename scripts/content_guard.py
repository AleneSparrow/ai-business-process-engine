"""Lint Flywheel founder-presence copy against USP guardrails.

Public posts live in docs/marketing/founder-presence/06-post-queue.md.
Nothing in DRAFT is published by this script.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = ROOT / "docs/marketing/founder-presence/06-post-queue.md"
DEFAULT_RULES = ROOT / "docs/marketing/founder-presence/guardrails.yaml"

POST_RE = re.compile(
    r"^### (?P<id>[A-Z]+-[A-Z0-9]+)\n"
    r"(?P<meta>(?:[a-z_]+: [^\n]+\n)+)"
    r"\n---\n\n"
    r"(?P<body>[\s\S]*?)"
    r"(?=\n### |\Z)",
    re.MULTILINE,
)

PERCENT_RE = re.compile(r"\d+\s*%\s*(conversion|close rate|win rate)", re.I)
CONVERTS_RE = re.compile(r"converts?\s+\d+\s*%", re.I)
NEGATION_RE = re.compile(
    r"\b(do not|does not|don't|doesn't|never|not|no)\b",
    re.I,
)


@dataclass(frozen=True)
class Post:
    post_id: str
    meta: dict[str, str]
    body: str


@dataclass(frozen=True)
class LintHit:
    post_id: str
    rule: str
    detail: str


def load_rules(path: Path = DEFAULT_RULES) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def parse_posts(markdown: str) -> list[Post]:
    posts: list[Post] = []
    for match in POST_RE.finditer(markdown):
        meta: dict[str, str] = {}
        for line in match.group("meta").strip().splitlines():
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
        body = match.group("body").strip()
        if body.endswith("\n---"):
            body = body[: -len("\n---")].strip()
        elif body.endswith("---"):
            body = body[: -len("---")].strip()
        posts.append(Post(post_id=match.group("id"), meta=meta, body=body))
    return posts


def _sentence_window(text: str, phrase: str) -> str:
    lower = text.lower()
    idx = lower.find(phrase.lower())
    if idx < 0:
        return text
    start = text.rfind(".", 0, idx)
    end = text.find(".", idx)
    start = 0 if start < 0 else start + 1
    end = len(text) if end < 0 else end
    return text[start:end]


def lint_body(post_id: str, body: str, rules: dict) -> list[LintHit]:
    hits: list[LintHit] = []
    lowered = body.lower()

    for phrase in rules.get("forbidden_substrings") or []:
        if phrase.lower() in lowered:
            hits.append(LintHit(post_id, "forbidden_substring", phrase))

    for phrase in rules.get("claim_substrings") or []:
        if phrase.lower() not in lowered:
            continue
        window = _sentence_window(body, phrase)
        if NEGATION_RE.search(window):
            continue
        hits.append(LintHit(post_id, "positive_claim", phrase))

    for pattern in rules.get("forbidden_regex") or []:
        if re.search(pattern, body, re.I):
            hits.append(LintHit(post_id, "forbidden_regex", pattern))

    if PERCENT_RE.search(body) or CONVERTS_RE.search(body):
        hits.append(LintHit(post_id, "conversion_percent", "unsourced conversion %"))

    if body.strip() and "flywheel" not in lowered:
        if post_id.startswith(("LI-", "FSV-")):
            hits.append(LintHit(post_id, "missing_product_name", "Flywheel"))

    return hits


def lint_posts(posts: list[Post], rules: dict) -> list[LintHit]:
    hits: list[LintHit] = []
    for post in posts:
        hits.extend(lint_body(post.post_id, post.body, rules))
    return hits


def export_csv(posts: list[Post], dest: Path) -> None:
    fieldnames = [
        "id",
        "channel",
        "audience",
        "pillar",
        "title_internal",
        "body",
        "media",
        "status",
        "lint",
        "approved_by",
        "approved_at",
        "scheduled_for",
        "published_url",
        "saves",
        "comments_icp",
        "inbound_yes",
        "kill",
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for post in posts:
            writer.writerow(
                {
                    "id": post.post_id,
                    "channel": post.meta.get("channel", ""),
                    "audience": post.meta.get("audience", ""),
                    "pillar": post.meta.get("pillar", ""),
                    "title_internal": post.post_id,
                    "body": post.body,
                    "media": "none",
                    "status": post.meta.get("status", "DRAFT"),
                    "lint": "unchecked",
                    "approved_by": "",
                    "approved_at": "",
                    "scheduled_for": post.meta.get("scheduled_for", ""),
                    "published_url": "",
                    "saves": "",
                    "comments_icp": "",
                    "inbound_yes": "",
                    "kill": "FALSE",
                }
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_QUEUE),
        help="Markdown queue or a file that contains ### POST-ID blocks",
    )
    parser.add_argument("--text-file", dest="text_file", help="Lint a raw text file as one post")
    parser.add_argument("--rules", default=str(DEFAULT_RULES))
    parser.add_argument("--csv-out", dest="csv_out")
    args = parser.parse_args(argv)

    rules = load_rules(Path(args.rules))

    if args.text_file:
        body = Path(args.text_file).read_text(encoding="utf-8")
        hits = lint_body("STDIN", body, rules)
        posts: list[Post] = []
    else:
        markdown = Path(args.path).read_text(encoding="utf-8")
        posts = parse_posts(markdown)
        if not posts:
            print(f"No posts parsed from {args.path}", file=sys.stderr)
            return 2
        hits = lint_posts(posts, rules)

    if args.csv_out and posts:
        export_csv(posts, Path(args.csv_out))

    if not hits:
        label = f"{len(posts)} posts" if posts else "text"
        print(f"PASS {label}")
        return 0

    for hit in hits:
        print(f"FAIL {hit.post_id}: {hit.rule}: {hit.detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
