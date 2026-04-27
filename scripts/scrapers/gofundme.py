"""GoFundMe page parser.

GoFundMe uses Next.js Pages Router with Apollo GraphQL. The full page state is
embedded in __NEXT_DATA__ under props.pageProps.__APOLLO_STATE__. The fundraiser
object is keyed as "Fundraiser:<id>" and contains:

    currentAmount: { amount: <int>, currencyCode: "GBP" }   # raised so far
    goalAmount:    { amount: <int>, currencyCode: "GBP" }   # target

Amounts are in major currency units (pounds, not pence).
"""

from __future__ import annotations

import json
import re

from .generic import ParseResult, parse_raised_target_from_html

_NEXT_DATA_PATTERN = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)


def _try_parse_apollo_state(html: str) -> ParseResult | None:
    """Extract raised/target from GoFundMe's Apollo GraphQL cache."""
    match = _NEXT_DATA_PATTERN.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    apollo = (
        data.get("props", {})
        .get("pageProps", {})
        .get("__APOLLO_STATE__", {})
    )

    for value in apollo.values():
        if not isinstance(value, dict):
            continue
        if "goalAmount" not in value or "currentAmount" not in value:
            continue
        try:
            raised = float(value["currentAmount"]["amount"])
            target = float(value["goalAmount"]["amount"])
            return ParseResult(raised=raised, target=target)
        except (KeyError, TypeError, ValueError):
            continue

    return None


def parse(html: str) -> ParseResult:
    result = _try_parse_apollo_state(html)
    if result is not None:
        return result
    return parse_raised_target_from_html(html, hint_words=("raised", "goal", "funded"))
