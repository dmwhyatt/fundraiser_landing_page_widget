"""JustGiving page parser.

JustGiving uses Next.js App Router (>= 13), so donation totals are embedded as
React Server Component (RSC) streaming chunks in the raw HTML — no JS execution
required. The generic parser's try_parse_embedded_json() handles this; this
module simply provides the platform-specific entry point and hint words.
"""

from __future__ import annotations

from .generic import ParseResult, parse_raised_target_from_html


def parse(html: str) -> ParseResult:
    return parse_raised_target_from_html(html, hint_words=("raised", "goal", "target"))
