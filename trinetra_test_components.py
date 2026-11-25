"""TRINETRA TEST-ONLY option build-up component from NSE EOD contract data.

This component is added only to the existing experimental TRINETRA combined
score. It never changes the published PDMP score or the verified/provisional
Final scores. Incomplete, stale, malformed or inconsistent evidence fails closed.
"""
import datetime as dt
import math

from component_scoring import build_component, finite_number
from nse_option_buildup import validate_option_buildup_diagnostic

EXPERIMENTAL_TEST_EXTRA_WEIGHTS = {"option_buildup": 10.0}

# Premium/OI pattern -> underlying direction, by option side.
_SIDE_SIGN = {
    "long_build_up": {"CE": 1, "PE": -1},
    "short_covering": {"CE": 1, "PE": -1},
    "short_build_up": {"CE": -1, "PE": 1},
    "long_unwinding": {"CE": -1, "PE": 1},
}


def option_buildup_test_component(
    diagnostic, reference_date, max_age_days=3, weight=10.0, min_classified=100
):
    """Return (TEST-only component, None) or (None, reason).

    coverage_validated=False is permitted only because this is explicitly a
    TEST-only diagnostic. The result carries that limitation as metadata.
    """
    if not isinstance(diagnostic, dict):
        return None, "Option build-up diagnostic उपलब्ध नहीं"

    checked = validate_option_buildup_diagnostic(
        diagnostic, min_matched_contracts=20
    )
    if checked.get("integrity_validation") != "PASSED":
        return None, "Option build-up की integrity जाँच PASSED नहीं"
    if checked.get("available") is not True or checked.get("status") != "AVAILABLE":
        return None, checked.get("reason") or "Option build-up डेटा उपलब्ध नहीं"

    try:
        observed = dt.date.fromisoformat(str(checked.get("source_date"))[:10])
        reference = dt.date.fromisoformat(str(reference_date)[:10])
        max_age = int(max_age_days)
    except (TypeError, ValueError, OverflowError):
        return None, "Option build-up की source date या freshness सीमा अमान्य है"
    age = (reference - observed).days
    if age < 0 or age > max_age:
        return None, "Option build-up का EOD डेटा पुराना या भविष्य की तारीख़ का है"

    classified = finite_number(checked.get("classified_contracts"))
    if classified is None or classified < min_classified or not classified.is_integer():
        return None, "वर्गीकृत contracts पर्याप्त नहीं (न्यूनतम %d)" % min_classified

    categories = checked.get("categories")
    if not isinstance(categories, dict):
        return None, "Option build-up categories उपलब्ध नहीं"

    bullish = bearish = 0.0
    for category, side_signs in _SIDE_SIGN.items():
        row = categories.get(category)
        if not isinstance(row, dict):
            return None, "Option build-up category अधूरी है: " + category
        details = row.get("contract_details")
        if not isinstance(details, list):
            return None, "Option build-up contract details अधूरे हैं: " + category

        side_totals = {"CE": 0.0, "PE": 0.0}
        for detail in details:
            if not isinstance(detail, dict):
                return None, "Option build-up contract detail अमान्य है"
            side = str(detail.get("side") or "").upper()
            quantity = finite_number(detail.get("oi_quantity"))
            if side not in side_totals or quantity is None or quantity < 0:
                return None, "Option build-up में OI quantity/side अमान्य है"
            side_totals[side] += quantity

        for side, sign in side_signs.items():
            reported = finite_number(row.get(side.lower() + "_oi_quantity"))
            if reported is None or reported < 0:
                return None, "Option build-up की " + side + " OI quantity उपलब्ध नहीं"
            if not math.isclose(reported, side_totals[side], rel_tol=1e-9, abs_tol=1e-6):
                return None, "Option build-up की category OI मात्रा contract details से मेल नहीं खाती"
            if sign > 0:
                bullish += reported
            else:
                bearish += reported

        reported_total = finite_number(row.get("oi_quantity"))
        if reported_total is None or reported_total < 0:
            return None, "Option build-up की कुल category OI quantity उपलब्ध नहीं"
        if not math.isclose(reported_total, sum(side_totals.values()), rel_tol=1e-9, abs_tol=1e-6):
            return None, "Option build-up की कुल OI मात्रा contract details से मेल नहीं खाती"

    total = bullish + bearish
    if total <= 0:
        return None, "Option build-up में दिशा वाली OI मात्रा नहीं"

    score = 10.0 * (bullish - bearish) / total
    component = build_component(
        score,
        checked.get("source") or "NSE F&O UDiFF Common Bhavcopy Final",
        str(checked.get("source_date"))[:10],
        weight,
        test_only=True,
        validation_status=(
            "TEST_ONLY · contract integrity passed; market-wide option coverage not independently validated"
            if checked.get("coverage_validated") is not True
            else "TEST_ONLY · contract integrity passed; historical prediction validation pending"
        ),
        coverage_validated=checked.get("coverage_validated") is True,
        bullish_oi_quantity=int(bullish),
        bearish_oi_quantity=int(bearish),
        classified_contracts=int(classified),
        score_method=(
            "10 × (bullish OI − bearish OI) ÷ total directional OI; "
            "CE long build-up/short covering and PE short build-up/long unwinding bullish"
        ),
        scope=(
            "NIFTY/BANKNIFTY NSE EOD option premium+OI pattern only; "
            "TEST ONLY, not an intraday entry signal or validated trade predictor"
        ),
    )
    return (component, None) if component else (None, "Option build-up component अधूरा है")
