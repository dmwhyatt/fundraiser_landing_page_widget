"""Generic HTML fundraising parser helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from bs4 import BeautifulSoup

MONEY_PATTERN = re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d+)?")
NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?")
RAISED_OF_TARGET_PATTERN = re.compile(
    r"([$£€]\s?\d[\d,]*(?:\.\d+)?)\s*raised\s*of\s*([$£€]\s?\d[\d,]*(?:\.\d+)?)\s*target",
    flags=re.IGNORECASE,
)
TARGET_ONLY_PATTERN = re.compile(
    r"raised\s*of\s*([$£€]\s?\d[\d,]*(?:\.\d+)?)\s*target",
    flags=re.IGNORECASE,
)
DONATION_SUMMARY_TOTAL_PATTERN = re.compile(
    r"Donation summary.*?Total\s*([$£€]\s?\d[\d,]*(?:\.\d+)?)",
    flags=re.IGNORECASE | re.DOTALL,
)
# Next.js Pages Router (<= 12): full page props in a single JSON blob.
NEXT_DATA_PATTERN = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)
# Next.js App Router (>= 13): page data arrives as RSC streaming chunks.
RSC_CHUNK_PATTERN = re.compile(
    r'self\.__next_f\.push\(\[1,"(.*?)"\]\)',
    re.DOTALL,
)

# Keys searched (in order of preference) when walking JSON structures.
_RAISED_KEYS = ("totalAmount", "totalRaisedAmount", "amountRaised", "totalRaised", "raised")
_TARGET_KEYS = ("targetAmount", "fundraisingTarget", "targetWithCurrency", "target", "goal")


@dataclass
class ParseResult:
    raised: float
    target: float


def _as_number(value: str) -> float:
    cleaned = value.replace(",", "")
    return float(cleaned)


def _coerce_to_float(value: Any) -> float | None:
    """Try to turn a JSON value into a plain float, stripping currency symbols."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().lstrip("£$€").replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _find_key_in_data(data: Any, keys: tuple[str, ...]) -> float | None:
    """Recursively search a parsed JSON structure for the first matching key."""
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                val = data[key]
                # targetWithCurrency stores value in minor currency units (pence).
                if key == "targetWithCurrency" and isinstance(val, dict):
                    minor = _coerce_to_float(val.get("value"))
                    if minor is not None and minor > 0:
                        return minor / 100
                    continue
                result = _coerce_to_float(val)
                if result is not None and result > 0:
                    return result
        for value in data.values():
            result = _find_key_in_data(value, keys)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_key_in_data(item, keys)
            if result is not None:
                return result
    return None


def _parse_json_structure(text: str) -> ParseResult | None:
    """Try to extract raised/target by walking a JSON string."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    raised = _find_key_in_data(data, _RAISED_KEYS)
    target = _find_key_in_data(data, _TARGET_KEYS)
    if raised is not None and target is not None:
        return ParseResult(raised=raised, target=target)
    return None


def _reassemble_rsc_chunks(html: str) -> str:
    """
    Reassemble Next.js App Router RSC streaming chunks into a single string.
    Each chunk is a JSON-escaped string pushed via self.__next_f.push([1,"..."]).
    """
    parts = []
    for escaped in RSC_CHUNK_PATTERN.findall(html):
        try:
            parts.append(json.loads('"' + escaped + '"'))
        except json.JSONDecodeError:
            pass
    return "".join(parts)


def _extract_from_rsc_text(rsc_text: str) -> ParseResult | None:
    """
    Pull raised/target out of the flat RSC text by finding the donationSummary
    object which contains totalAmount and targetAmount as plain floats.
    """
    # Fast path: look for the two keys as adjacent JSON fields.
    raised_match = re.search(r'"totalAmount"\s*:\s*([\d.]+)', rsc_text)
    target_match = re.search(r'"targetAmount"\s*:\s*([\d.]+)', rsc_text)
    if raised_match and target_match:
        try:
            return ParseResult(
                raised=float(raised_match.group(1)),
                target=float(target_match.group(1)),
            )
        except ValueError:
            pass

    # Slower path: find JSON objects embedded in the RSC stream and walk them.
    for obj_match in re.finditer(r'\{[^{}]{20,}\}', rsc_text):
        result = _parse_json_structure(obj_match.group(0))
        if result is not None:
            return result
    return None


def try_parse_embedded_json(html: str) -> ParseResult | None:
    """
    Extract raised/target from Next.js server-rendered data in the raw HTML.

    Tries two strategies in order:
    1. RSC streaming chunks (Next.js App Router >= 13, used by JustGiving).
    2. __NEXT_DATA__ blob (Next.js Pages Router <= 12).
    """
    # Strategy 1: RSC chunks.
    rsc_text = _reassemble_rsc_chunks(html)
    if rsc_text:
        result = _extract_from_rsc_text(rsc_text)
        if result is not None:
            return result

    # Strategy 2: __NEXT_DATA__ blob.
    nd_match = NEXT_DATA_PATTERN.search(html)
    if nd_match:
        result = _parse_json_structure(nd_match.group(1))
        if result is not None:
            return result

    return None


def extract_money_candidates(text: str) -> list[float]:
    values = []
    for match in MONEY_PATTERN.findall(text):
        number_match = NUMBER_PATTERN.search(match)
        if number_match:
            values.append(_as_number(number_match.group(0)))
    return values


def extract_first_money_value(text: str) -> float:
    matches = extract_money_candidates(text)
    if not matches:
        raise ValueError(f"No currency-like amount found in text snippet: {text[:80]!r}")
    return matches[0]


def parse_raised_target_from_selectors(
    html: str, raised_selector: str, target_selector: str
) -> ParseResult:
    """
    Parse raised/target using explicit CSS selectors.

    This is the most stable approach once selectors are known for each platform.
    """
    soup = BeautifulSoup(html, "html.parser")
    raised_node = soup.select_one(raised_selector)
    target_node = soup.select_one(target_selector)

    if raised_node is None:
        raise ValueError(f"Could not find raised selector: {raised_selector}")
    if target_node is None:
        raise ValueError(f"Could not find target selector: {target_selector}")

    raised = extract_first_money_value(raised_node.get_text(" ", strip=True))
    target = extract_first_money_value(target_node.get_text(" ", strip=True))
    return ParseResult(raised=raised, target=target)


def parse_raised_target_from_html(
    html: str, hint_words: Iterable[str] | None = None
) -> ParseResult:
    """
    Parse raised and target values from a fundraising page.

    The parser first tries lines containing hint words. If no pair is found,
    it falls back to first two currency-like numbers in the page text.
    """
    hint_words = tuple(word.lower() for word in (hint_words or ("raised", "goal", "target")))

    # Highest-confidence path: pull values from Next.js server-rendered JSON
    # (RSC chunks or __NEXT_DATA__) embedded in the raw HTML. No JS execution
    # needed; works for JustGiving and other Next.js fundraising platforms.
    embedded_result = try_parse_embedded_json(html)
    if embedded_result is not None:
        return embedded_result

    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)

    # Prefer explicit phrase patterns first (common on JustGiving pages).
    direct_match = RAISED_OF_TARGET_PATTERN.search(full_text)
    if direct_match:
        raised_candidates = extract_money_candidates(direct_match.group(1))
        target_candidates = extract_money_candidates(direct_match.group(2))
        if raised_candidates and target_candidates:
            return ParseResult(raised=raised_candidates[0], target=target_candidates[0])

    # If only target phrase is detectable, use nearest preceding amount as raised.
    target_match = TARGET_ONLY_PATTERN.search(full_text)
    if target_match:
        target_value = extract_money_candidates(target_match.group(1))
        preceding_text = full_text[: target_match.start()]
        preceding_values = extract_money_candidates(preceding_text)
        if target_value and preceding_values:
            return ParseResult(raised=preceding_values[-1], target=target_value[0])

    # JustGiving fallback: raised appears in "Donation summary Total £x".
    summary_match = DONATION_SUMMARY_TOTAL_PATTERN.search(full_text)
    if summary_match:
        raised_value = extract_money_candidates(summary_match.group(1))
        target_from_phrase = TARGET_ONLY_PATTERN.search(full_text)
        if raised_value and target_from_phrase:
            target_value = extract_money_candidates(target_from_phrase.group(1))
            if target_value:
                return ParseResult(raised=raised_value[0], target=target_value[0])

    lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]

    # Common structure: one line with raised amount, next line says "raised of £X target".
    for index, line in enumerate(lines):
        lower = line.lower()
        if "raised of" not in lower or "target" not in lower:
            continue

        target_candidates = extract_money_candidates(line)
        if not target_candidates:
            continue
        target_value = target_candidates[0]

        for previous_index in range(index - 1, max(-1, index - 6), -1):
            raised_candidates = extract_money_candidates(lines[previous_index])
            if raised_candidates:
                return ParseResult(raised=raised_candidates[-1], target=target_value)

    for line in lines:
        lower = line.lower()
        if not any(word in lower for word in hint_words):
            continue
        candidates = extract_money_candidates(line)
        if len(candidates) >= 2:
            return ParseResult(raised=candidates[0], target=candidates[1])

    raise ValueError("Could not parse raised/target values from page content.")
