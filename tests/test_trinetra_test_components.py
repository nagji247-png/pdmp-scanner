import datetime as dt

from trinetra_test_components import option_buildup_test_component


def _option(**changes):
    categories = {}
    rows = {
        "long_build_up": [("CE", 100), ("PE", 10)],
        "short_covering": [("CE", 100), ("PE", 10)],
        "short_build_up": [("CE", 10), ("PE", 100)],
        "long_unwinding": [("CE", 10), ("PE", 100)],
    }
    for category, contracts in rows.items():
        details = [{"side": side, "oi_quantity": qty} for side, qty in contracts]
        categories[category] = {
            "contracts": len(details),
            "contract_details": details,
            "ce_oi_quantity": sum(q for s, q in contracts if s == "CE"),
            "pe_oi_quantity": sum(q for s, q in contracts if s == "PE"),
            "oi_quantity": sum(q for _, q in contracts),
        }
    base = {
        "available": True, "status": "AVAILABLE",
        "integrity_validation": "PASSED", "source": "NSE F&O UDiFF",
        "source_date": "2026-11-24", "matched_contracts": 8,
        "classified_contracts": 8, "coverage_validated": False,
        "categories": categories,
    }
    base.update(changes)
    return base


def test_option_buildup_direction_signs_and_test_only_scope():
    component, reason = option_buildup_test_component(_option(), "2026-11-25", min_classified=8)
    assert reason is None
    assert component["bullish_oi_quantity"] == 400
    assert component["bearish_oi_quantity"] == 40
    assert component["score"] > 8
    assert component["test_only"] is True
    assert component["coverage_validated"] is False


def test_missing_or_malformed_oi_quantity_fails_closed():
    diagnostic = _option()
    del diagnostic["categories"]["long_build_up"]["ce_oi_quantity"]
    component, reason = option_buildup_test_component(diagnostic, "2026-11-25", min_classified=8)
    assert component is None and reason


def test_category_quantity_mismatch_fails_closed():
    diagnostic = _option()
    diagnostic["categories"]["short_covering"]["pe_oi_quantity"] = 999
    component, reason = option_buildup_test_component(diagnostic, "2026-11-25", min_classified=8)
    assert component is None and reason


def test_stale_future_or_insufficient_data_fails_closed():
    assert option_buildup_test_component(_option(source_date="2026-11-20"), "2026-11-25", min_classified=8)[0] is None
    assert option_buildup_test_component(_option(source_date="2026-11-26"), "2026-11-25", min_classified=8)[0] is None
    assert option_buildup_test_component(_option(classified_contracts=7), "2026-11-25", min_classified=8)[0] is None
    assert option_buildup_test_component(_option(integrity_validation="FAILED"), "2026-11-25", min_classified=8)[0] is None
    assert option_buildup_test_component(None, "2026-11-25")[0] is None
