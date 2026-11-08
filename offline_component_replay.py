"""Deterministic offline replay for PDMP component-score snapshots.

This module consumes archived observations only. It performs no network or
provider access and never changes production dashboard scores.
"""
from datetime import date, datetime, timezone
import math

from component_scoring import clamp_score, finite_number


def _parse_day(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def replay_component_scores(observations, replay_dates, max_age_days=1, weights=None):
    """Replay per-asset weighted scores using only observations known by each date.

    Observation schema:
      asset, component, score, source, source_date, observed_at, weight

    For each replay date and asset, the latest eligible observation per
    component is selected. Future observations, invalid provenance, invalid
    weights, non-finite scores and stale observations are excluded with reasons.
    """
    if not isinstance(observations, list):
        raise TypeError("observations must be a list")
    if not isinstance(replay_dates, (list, tuple)) or not replay_dates:
        raise ValueError("replay_dates must be a non-empty list")
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int) or max_age_days < 0:
        raise ValueError("max_age_days must be a non-negative integer")

    days = sorted({_parse_day(str(item)) for item in replay_dates})
    if None in days:
        raise ValueError("every replay date must be YYYY-MM-DD")
    configured = weights or {}
    normalized = []
    malformed = 0
    for row in observations:
        if not isinstance(row, dict):
            malformed += 1
            continue
        asset = str(row.get("asset") or "").strip().upper()
        component = str(row.get("component") or "").strip().lower()
        observed = _parse_timestamp(row.get("observed_at"))
        source_day = _parse_day(row.get("source_date"))
        score = clamp_score(row.get("score"))
        weight = finite_number(configured.get(component, row.get("weight")))
        source = row.get("source")
        if (not asset or not component or observed is None or source_day is None
                or score is None or weight is None or weight <= 0
                or not isinstance(source, str) or not source.strip()):
            malformed += 1
            continue
        normalized.append({
            "asset": asset, "component": component, "observed": observed,
            "source_day": source_day, "score": score, "weight": weight,
            "source": source.strip(),
        })

    results = []
    for replay_day in days:
        cutoff = datetime.combine(replay_day, datetime.max.time(), tzinfo=timezone.utc)
        selected = {}
        excluded = {"future_observation": 0, "stale_observation": 0}
        for row in normalized:
            if row["source_day"] > replay_day or row["observed"] > cutoff:
                excluded["future_observation"] += 1
                continue
            age = (replay_day - row["source_day"]).days
            if age > max_age_days:
                excluded["stale_observation"] += 1
                continue
            key = (row["asset"], row["component"])
            prior = selected.get(key)
            if prior is None or row["observed"] > prior["observed"]:
                selected[key] = row

        assets = {}
        for (asset, component), row in selected.items():
            assets.setdefault(asset, {})[component] = row
        for asset in sorted(assets):
            components = assets[asset]
            total_weight = sum(item["weight"] for item in components.values())
            score = sum(item["score"] * item["weight"] for item in components.values()) / total_weight
            assets[asset] = {
                "score": round(max(-10.0, min(10.0, score)), 4),
                "status": "available",
                "included_components": sorted(components),
                "normalized_weights_pct": {
                    name: round(item["weight"] / total_weight * 100.0, 2)
                    for name, item in sorted(components.items())
                },
                "evidence": {
                    name: {
                        "score": item["score"], "source": item["source"],
                        "source_date": item["source_day"].isoformat(),
                        "observed_at": item["observed"].isoformat().replace("+00:00", "Z"),
                    }
                    for name, item in sorted(components.items())
                },
            }
        results.append({
            "replay_date": replay_day.isoformat(),
            "assets": assets,
            "excluded_observations": excluded,
            "malformed_observations": malformed,
            "provider_calls": 0,
            "production_score_modified": False,
        })
    return {
        "mode": "offline_historical_replay",
        "provider_calls": 0,
        "production_score_modified": False,
        "observation_count": len(observations),
        "valid_observation_count": len(normalized),
        "malformed_observation_count": malformed,
        "results": results,
    }
