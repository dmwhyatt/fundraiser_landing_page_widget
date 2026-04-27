#!/usr/bin/env python3
"""Scrape fundraising pages and write a shared JSON snapshot."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import find_dotenv, load_dotenv

from scrapers.justgiving import parse as parse_justgiving
from scrapers.gofundme import parse as parse_gofundme
from scrapers.generic import ParseResult

ROOT = Path(__file__).resolve().parents[1]
TOTALS_PATH = ROOT / "data" / "totals.json"
DEBUG_DIR = ROOT / "debug"
REQUEST_TIMEOUT_SECONDS = 12

# Local developer convenience: load variables from .env if present.
load_dotenv(find_dotenv(), override=False)


@dataclass
class CampaignConfig:
    id: str
    name: str
    env_var: str
    parser: Callable[[str], ParseResult]
    icon: str = ""


CAMPAIGNS = [
    CampaignConfig(
        id="hhbc",
        name="Hughes Hall BC",
        env_var="FUNDRAISER_URL_A",
        parser=parse_gofundme,
        icon="../icons/hhbclogo.png",
    ),
    CampaignConfig(
        id="lccbc",
        name="Lucy Cavendish College BC",
        env_var="FUNDRAISER_URL_B",
        parser=parse_justgiving,
        icon="../icons/lucybclogo.jpg",
    ),
    CampaignConfig(
        id="secbc",
        name="St Edmund's College BC",
        env_var="FUNDRAISER_URL_C",
        parser=parse_justgiving,
        icon="../icons/secbclogo.jpeg",
    ),
]


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_previous_payload() -> dict[str, Any]:
    if not TOTALS_PATH.exists():
        return {
            "campaigns": [],
            "totals": {"raised": 0, "target": 0, "progressPercent": 0},
            "meta": {"generatedAt": None, "runId": None, "partialFailure": False, "errors": []},
        }
    try:
        with TOTALS_PATH.open("r", encoding="utf-8") as fh:
            raw = fh.read().strip()
            if not raw:
                raise ValueError("totals snapshot is empty")
            return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Recover gracefully if snapshot file is empty/corrupt.
        return {
            "campaigns": [],
            "totals": {"raised": 0, "target": 0, "progressPercent": 0},
            "meta": {"generatedAt": None, "runId": None, "partialFailure": False, "errors": []},
        }


def previous_campaign_map(previous_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item.get("id"): item for item in previous_payload.get("campaigns", [])}


def fetch_campaign(
    url: str, parser: Callable[[str], ParseResult], campaign_id: str
) -> tuple[float, float]:
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "fundraiser-widget-updater/1.0"},
    )
    response.raise_for_status()
    if os.environ.get("FUNDRAISER_DEBUG_SAVE_HTML") == "1":
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / f"{campaign_id}.html").write_text(response.text, encoding="utf-8")
    parsed = parser(response.text)
    return parsed.raised, parsed.target


def campaign_progress(raised: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return round((raised / target) * 100, 2)


def build_payload(run_id: str) -> dict[str, Any]:
    previous_payload = load_previous_payload()
    previous_by_id = previous_campaign_map(previous_payload)

    campaigns = []
    errors = []
    partial_failure = False

    generated_at = iso_now()
    for config in CAMPAIGNS:
        source_url = os.environ.get(config.env_var)
        if not source_url:
            partial_failure = True
            fallback = previous_by_id.get(config.id, {})
            campaigns.append(
                {
                    "id": config.id,
                    "name": config.name,
                    "icon": config.icon,
                    "sourceUrl": fallback.get("sourceUrl", ""),
                    "raised": float(fallback.get("raised", 0)),
                    "target": float(fallback.get("target", 0)),
                    "progressPercent": float(fallback.get("progressPercent", 0)),
                    "updatedAt": fallback.get("updatedAt", generated_at),
                }
            )
            errors.append(f"{config.id}: missing env var {config.env_var}")
            continue

        try:
            raised, target = fetch_campaign(source_url, config.parser, config.id)
            campaigns.append(
                {
                    "id": config.id,
                    "name": config.name,
                    "icon": config.icon,
                    "sourceUrl": source_url,
                    "raised": round(raised, 2),
                    "target": round(target, 2),
                    "progressPercent": campaign_progress(raised, target),
                    "updatedAt": generated_at,
                }
            )
        except (requests.RequestException, ValueError) as exc:
            partial_failure = True
            fallback = previous_by_id.get(config.id, {})
            campaigns.append(
                {
                    "id": config.id,
                    "name": config.name,
                    "icon": config.icon,
                    "sourceUrl": source_url,
                    "raised": float(fallback.get("raised", 0)),
                    "target": float(fallback.get("target", 0)),
                    "progressPercent": float(fallback.get("progressPercent", 0)),
                    "updatedAt": fallback.get("updatedAt", generated_at),
                }
            )
            errors.append(f"{config.id}: {exc}")

    total_raised = round(sum(item["raised"] for item in campaigns), 2)
    total_target = round(sum(item["target"] for item in campaigns), 2)

    payload = {
        "campaigns": campaigns,
        "totals": {
            "raised": total_raised,
            "target": total_target,
            "progressPercent": campaign_progress(total_raised, total_target),
        },
        "meta": {
            "generatedAt": generated_at,
            "runId": run_id,
            "partialFailure": partial_failure,
            "errors": errors,
        },
    }
    return payload


def write_payload(payload: dict[str, Any]) -> None:
    TOTALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TOTALS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


def main() -> None:
    run_id = os.getenv("GITHUB_RUN_ID", f"local-{int(datetime.now().timestamp())}")
    payload = build_payload(run_id=run_id)
    write_payload(payload)
    print(f"Wrote snapshot to {TOTALS_PATH}")
    print(f"partialFailure={payload['meta']['partialFailure']}")


if __name__ == "__main__":
    main()
