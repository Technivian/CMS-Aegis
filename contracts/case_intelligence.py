from datetime import date, datetime
from typing import Any, Dict, List


CASE_DATA_REQUIRED_FIELDS = (
    "phase",
    "care_category",
    "urgency",
    "assessment_complete",
    "matching_run_exists",
    "top_match_confidence",
    "top_match_has_capacity_issue",
    "top_match_wait_days",
    "selected_provider_id",
    "placement_status",
    "placement_updated_at",
    "rejected_provider_count",
    "open_signal_count",
    "open_task_count",
    "case_updated_at",
    "candidate_suggestions",
)


CASE_DATA_SHAPE: Dict[str, str] = {
    "phase": "str: current case phase/status code",
    "care_category": "str|None: normalized care category code/name",
    "urgency": "str|None: normalized urgency code",
    "assessment_complete": "bool: whether assessment is complete and matching-ready",
    "matching_run_exists": "bool: whether matching has been executed",
    "top_match_confidence": "str|None: high|medium|low|None",
    "top_match_has_capacity_issue": "bool: top match has no/limited capacity",
    "top_match_wait_days": "int|None: wait days for top match",
    "selected_provider_id": "int|str|None: selected provider identifier",
    "placement_status": "str|None: placement status code",
    "placement_updated_at": "date|datetime|None: last placement update",
    "rejected_provider_count": "int: amount of rejected providers",
    "open_signal_count": "int: number of open risk signals",
    "open_task_count": "int: number of open tasks",
    "case_updated_at": "date|datetime|None: last case update",
    "candidate_suggestions": (
        "list[dict]: providers with at least provider_id, confidence, has_capacity_issue, wait_days "
        "and optional has_region_mismatch"
    ),
    "has_preferred_region": "bool|None: whether a preferred region is set",
    "has_assessment_summary": "bool|None: whether assessment summary text is present",
    "has_client_age_category": "bool|None: whether age category is present",
    "assessment_status": "str|None: normalized assessment status code",
    "assessment_matching_ready": "bool|None: explicit matching-ready indicator",
    "matching_updated_at": "date|datetime|None: timestamp of latest matching selection",
    "provider_response_status": "str|None: provider response status code",
    "provider_response_recorded_at": "date|datetime|None: provider response recorded timestamp",
    "provider_response_requested_at": "date|datetime|None: latest provider response request timestamp",
    "provider_response_deadline_at": "date|datetime|None: response deadline timestamp",
    "now": "date|datetime|None: optional override for deterministic time-based rules",
}


def _validate_case_data(case_data: Dict[str, Any]) -> None:
    missing = [key for key in CASE_DATA_REQUIRED_FIELDS if key not in case_data]
    if missing:
        raise ValueError(f"case_data is missing required keys: {', '.join(sorted(missing))}")


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _resolve_today(case_data: Dict[str, Any]) -> date:
    raw_now = case_data.get("now")
    now_date = _to_date(raw_now)
    if now_date:
        return now_date
    return date.today()


def _days_since(value: Any, *, today: date) -> int:
    target_date = _to_date(value)
    if not target_date:
        return 0
    return max((today - target_date).days, 0)


def _normalize_confidence(confidence: Any) -> str:
    if confidence is None:
        return ""
    return str(confidence).strip().lower()


def _normalize_candidate_suggestions(case_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    suggestions = case_data.get("candidate_suggestions") or []
    normalized: List[Dict[str, Any]] = []
    for row in suggestions:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "provider_id": row.get("provider_id"),
                "confidence": _normalize_confidence(row.get("confidence")),
                "has_capacity_issue": bool(row.get("has_capacity_issue")),
                "wait_days": _coerce_int(row.get("wait_days")),
                "has_region_mismatch": bool(row.get("has_region_mismatch")),
            }
        )
    return normalized


def _candidate_trade_offs(candidate: Dict[str, Any]) -> List[str]:
    trade_offs: List[str] = []
    if candidate["has_capacity_issue"]:
        trade_offs.append("Beperkte capaciteit")
    if candidate["wait_days"] >= 28:
        trade_offs.append(f"Lange wachttijd ({candidate['wait_days']} dagen)")
    if candidate.get("has_region_mismatch"):
        trade_offs.append("Regio minder passend")

    confidence = candidate["confidence"]
    if confidence == "medium":
        trade_offs.append("Confidence is gemiddeld")
    elif confidence in {"", "low"}:
        trade_offs.append("Confidence is laag")

    return trade_offs


def detect_missing_information(case_data: Dict[str, Any]) -> List[Dict[str, str]]:
    _validate_case_data(case_data)

    alerts: List[Dict[str, str]] = []
    if not case_data.get("phase"):
        alerts.append(
            {
                "code": "missing_phase",
                "label": "Fase ontbreekt",
                "message": "De casusfase ontbreekt.",
                "action": "Vul de huidige fase van de casus in.",
            }
        )

    if not case_data.get("care_category"):
        alerts.append(
            {
                "code": "missing_care_category",
                "label": "Hoofdcategorie ontbreekt",
                "message": "Hoofdcategorie zorgvraag ontbreekt.",
                "action": "Vul de hoofdcategorie in.",
            }
        )

    if not case_data.get("urgency"):
        alerts.append(
            {
                "code": "missing_urgency",
                "label": "Urgentie ontbreekt",
                "message": "Urgentie van de casus ontbreekt.",
                "action": "Selecteer de juiste urgentie.",
            }
        )

    if case_data.get("has_preferred_region") is False:
        alerts.append(
            {
                "code": "missing_region",
                "label": "Voorkeursregio ontbreekt",
                "message": "Voorkeursregio ontbreekt.",
                "action": "Kies een voorkeursregio in de intake.",
            }
        )

    if case_data.get("has_assessment_summary") is False:
        alerts.append(
            {
                "code": "missing_assessment_summary",
                "label": "Intake samenvatting ontbreekt",
                "message": "Intake samenvatting ontbreekt.",
                "action": "Vul de intake samenvatting aan met hulpvraag en aandachtspunten.",
            }
        )

    if case_data.get("has_client_age_category") is False:
        alerts.append(
            {
                "code": "missing_age_category",
                "label": "Leeftijdscategorie ontbreekt",
                "message": "Leeftijdscategorie ontbreekt.",
                "action": "Selecteer de leeftijdscategorie van de client.",
            }
        )

    assessment_status = str(case_data.get("assessment_status") or "").strip().upper()
    if assessment_status == "NEEDS_INFO":
        alerts.append(
            {
                "code": "assessment_needs_info",
                "label": "Beoordeling vraagt aanvullende informatie",
                "message": "Beoordeling staat op aanvullende informatie nodig.",
                "action": "Werk ontbrekende beoordelingsinformatie bij.",
            }
        )

    if case_data.get("assessment_matching_ready") is False:
        alerts.append(
            {
                "code": "assessment_not_ready",
                "label": "Beoordeling nog niet matching-klaar",
                "message": "Beoordeling is nog niet als klaar voor matching gemarkeerd.",
                "action": "Markeer beoordeling als matching-klaar zodra compleet.",
            }
        )

    placement_status = str(case_data.get("placement_status") or "").strip().upper()
    if placement_status in {"IN_REVIEW", "NEEDS_INFO", "APPROVED", "REJECTED"} and not case_data.get("selected_provider_id"):
        alerts.append(
            {
                "code": "missing_selected_provider",
                "label": "Geselecteerde aanbieder ontbreekt",
                "message": "Plaatsingsstatus bestaat, maar er is geen aanbieder gekoppeld.",
                "action": "Koppel eerst een aanbieder aan de casus.",
            }
        )

    if case_data.get("matching_run_exists") and not case_data.get("top_match_confidence"):
        alerts.append(
            {
                "code": "missing_top_match_confidence",
                "label": "Topmatch confidence ontbreekt",
                "message": "Matching is uitgevoerd zonder confidence op de topmatch.",
                "action": "Controleer matching-output en vul confidence aan.",
            }
        )

    return alerts


def detect_risk_signals(case_data: Dict[str, Any]) -> List[Dict[str, str]]:
    _validate_case_data(case_data)

    today = _resolve_today(case_data)
    signals: List[Dict[str, str]] = []

    open_signal_count = _coerce_int(case_data.get("open_signal_count"))
    if open_signal_count > 0:
        signals.append(
            {
                "code": "open_signals",
                "label": "Open signalen",
                "message": f"Er zijn {open_signal_count} open signalen.",
                "action": "Beoordeel en verwerk open signalen.",
            }
        )

    rejected_provider_count = _coerce_int(case_data.get("rejected_provider_count"))
    if rejected_provider_count >= 2:
        signals.append(
            {
                "code": "repeated_rejections",
                "label": "Herhaalde afwijzingen",
                "message": f"{rejected_provider_count} aanbieders zijn afgewezen.",
                "action": "Herzie selectiecriteria of verbreed aanbod.",
            }
        )

    confidence = _normalize_confidence(case_data.get("top_match_confidence"))
    if case_data.get("matching_run_exists") and confidence in {"", "low"}:
        signals.append(
            {
                "code": "weak_matching_quality",
                "label": "Zwakke matchingkwaliteit",
                "message": "Topmatch heeft lage of ontbrekende confidence.",
                "action": "Controleer matchfactoren en herzie kandidaten.",
            }
        )

    if bool(case_data.get("top_match_has_capacity_issue")):
        signals.append(
            {
                "code": "capacity_risk",
                "label": "Capaciteitsrisico",
                "message": "Topmatch heeft capaciteitsbeperking.",
                "action": "Valideer beschikbaarheid bij de aanbieder.",
            }
        )

    top_wait_days = _coerce_int(case_data.get("top_match_wait_days"))
    if top_wait_days >= 28:
        signals.append(
            {
                "code": "long_wait_risk",
                "label": "Lange wachttijd",
                "message": f"Topmatch heeft een wachttijd van {top_wait_days} dagen.",
                "action": "Controleer alternatieven met kortere wachttijd.",
            }
        )

    placement_status = str(case_data.get("placement_status") or "").strip().upper()
    placement_stalled_days = _days_since(case_data.get("placement_updated_at"), today=today)
    if placement_status in {"IN_REVIEW", "NEEDS_INFO"} and placement_stalled_days >= 7:
        signals.append(
            {
                "code": "placement_stalled",
                "label": "Plaatsing stagneert",
                "message": f"Plaatsing staat al {placement_stalled_days} dagen zonder voortgang.",
                "action": "Neem contact op met aanbieder en werk status bij.",
            }
        )

    provider_response_status = str(case_data.get("provider_response_status") or "").strip().upper()
    response_requested_at = case_data.get("provider_response_requested_at") or case_data.get("placement_updated_at")
    response_age_days = _days_since(response_requested_at, today=today)
    response_deadline_at = _to_date(case_data.get("provider_response_deadline_at"))
    response_deadline_overdue = bool(response_deadline_at and today > response_deadline_at)
    urgency = str(case_data.get("urgency") or "").strip().upper()

    if provider_response_status in {"PENDING", "NEEDS_INFO"}:
        if response_age_days >= 3 or response_deadline_overdue:
            signals.append(
                {
                    "code": "provider_response_delayed",
                    "label": "Providerreactie vertraagd",
                    "message": f"Aanbiedersreactie wacht al {response_age_days} dagen op opvolging.",
                    "action": "Stuur herinnering of werk ontbrekende informatie direct bij.",
                }
            )
        if response_age_days >= 7 or (response_deadline_overdue and response_age_days >= 5):
            signals.append(
                {
                    "code": "provider_not_responding",
                    "label": "Aanbieder reageert niet",
                    "message": "Aanbieder reageert niet binnen de afgesproken termijn.",
                    "action": "Escaleer en start zo nodig rematch met alternatieve aanbieders.",
                }
            )
        if urgency in {"HIGH", "CRISIS"} and response_age_days >= 2:
            signals.append(
                {
                    "code": "high_urgency_response_delay",
                    "label": "Urgente casus wacht op reactie",
                    "message": f"Urgente casus wacht {response_age_days} dagen op providerreactie.",
                    "action": "Escaleer direct en bereid parallel een rematch voor.",
                }
            )

    if provider_response_status in {"REJECTED", "NO_CAPACITY"}:
        signals.append(
            {
                "code": "rematch_recommended",
                "label": "Her-match aanbevolen",
                "message": "Providerreactie blokkeert intake-voortgang.",
                "action": "Herstart matching met alternatieve aanbieders.",
            }
        )
    if provider_response_status == "NO_CAPACITY":
        signals.append(
            {
                "code": "provider_no_capacity",
                "label": "Geen capaciteit bij aanbieder",
                "message": "Geselecteerde aanbieder geeft aan geen capaciteit te hebben.",
                "action": "Markeer als hoog risico en voer direct rematch uit.",
            }
        )

    stale_case_days = _days_since(case_data.get("case_updated_at"), today=today)
    if stale_case_days >= 10:
        signals.append(
            {
                "code": "stale_case",
                "label": "Casus verouderd",
                "message": f"Casus is {stale_case_days} dagen niet bijgewerkt.",
                "action": "Werk casusinformatie en planning bij.",
            }
        )

    case_updated_at = _to_date(case_data.get("case_updated_at"))
    matching_updated = _to_date(case_data.get("matching_updated_at"))
    if case_updated_at and matching_updated and case_updated_at > matching_updated:
        signals.append(
            {
                "code": "matching_outdated",
                "label": "Matching mogelijk verouderd",
                "message": "Casusgegevens zijn gewijzigd na de laatste matchingselectie.",
                "action": "Herstart matching met actuele casusgegevens.",
            }
        )

    open_task_count = _coerce_int(case_data.get("open_task_count"))
    if open_task_count >= 5:
        signals.append(
            {
                "code": "task_backlog",
                "label": "Takenstuwmeer",
                "message": f"Er staan {open_task_count} open taken.",
                "action": "Prioriteer open taken en plan opvolging.",
            }
        )

    return signals


def _is_weak_or_low_confidence(case_data: Dict[str, Any]) -> bool:
    confidence = _normalize_confidence(case_data.get("top_match_confidence"))
    suggestions = _normalize_candidate_suggestions(case_data)
    return not suggestions or confidence in {"", "low"}


def _needs_capacity_wait_validation(case_data: Dict[str, Any]) -> bool:
    if bool(case_data.get("top_match_has_capacity_issue")):
        return True
    return _coerce_int(case_data.get("top_match_wait_days")) >= 28


def _is_placement_stalled(case_data: Dict[str, Any]) -> bool:
    placement_status = str(case_data.get("placement_status") or "").strip().upper()
    if placement_status not in {"IN_REVIEW", "NEEDS_INFO"}:
        return False
    today = _resolve_today(case_data)
    return _days_since(case_data.get("placement_updated_at"), today=today) >= 7


def determine_next_best_action(
    case_data: Dict[str, Any],
    *,
    missing_information: List[Dict[str, str]] | None = None,
    risk_signals: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    _validate_case_data(case_data)

    if missing_information is None:
        missing_information = detect_missing_information(case_data)
    if risk_signals is None:
        risk_signals = detect_risk_signals(case_data)

    if missing_information:
        return {
            "code": "fill_missing_information",
            "priority": 1,
            "reason": missing_information[0]["message"],
        }

    if not bool(case_data.get("assessment_complete")):
        return {
            "code": "complete_assessment",
            "priority": 2,
            "reason": "Beoordeling is nog niet volledig of niet matching-klaar.",
        }

    if not bool(case_data.get("matching_run_exists")):
        return {
            "code": "run_matching",
            "priority": 3,
            "reason": "Er is nog geen matching-run beschikbaar.",
        }

    provider_response_status = str(case_data.get("provider_response_status") or "").strip().upper()
    response_requested_at = case_data.get("provider_response_requested_at") or case_data.get("placement_updated_at")
    today = _resolve_today(case_data)
    response_age_days = _days_since(response_requested_at, today=today)

    if provider_response_status in {"PENDING", "NEEDS_INFO"} and response_age_days >= 3:
        return {
            "code": "follow_up_provider_response",
            "priority": 4,
            "reason": "Aanbiedersreactie vraagt opvolging om intakevertraging te voorkomen.",
        }

    if provider_response_status in {"REJECTED", "NO_CAPACITY"}:
        return {
            "code": "run_matching",
            "priority": 4,
            "reason": "Providerreactie vraagt om directe herstart van matching.",
        }

    if _is_weak_or_low_confidence(case_data):
        return {
            "code": "review_matching_quality",
            "priority": 4,
            "reason": "Topmatch heeft lage confidence of er zijn geen bruikbare kandidaten.",
        }

    if _needs_capacity_wait_validation(case_data):
        return {
            "code": "validate_capacity_wait",
            "priority": 5,
            "reason": "Capaciteit of wachttijd van de topmatch moet worden gevalideerd.",
        }

    if _is_placement_stalled(case_data):
        return {
            "code": "resolve_placement_stall",
            "priority": 6,
            "reason": "Plaatsing stagneert en heeft opvolging nodig.",
        }

    return {
        "code": "monitor",
        "priority": 7,
        "reason": "Geen directe actie nodig; monitor voortgang.",
    }


def generate_candidate_hints(case_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    _validate_case_data(case_data)

    suggestions = _normalize_candidate_suggestions(case_data)
    if not suggestions:
        return []

    hints: List[Dict[str, Any]] = []
    top_candidate = suggestions[0]
    top_confidence = top_candidate["confidence"]
    top_trade_offs = _candidate_trade_offs(top_candidate)

    for index, candidate in enumerate(suggestions):
        confidence = candidate["confidence"]
        trade_offs = _candidate_trade_offs(candidate)
        hint_code = "backup_option"
        hint = "Alternatieve optie met aanvullende verificatie."
        comparison_to_top = ""

        if index == 0:
            if confidence in {"high", "medium"} and not trade_offs:
                hint_code = "top_recommended"
                hint = "Beste optie op basis van huidige gegevens."
            elif confidence in {"high", "medium"} and trade_offs:
                hint_code = "top_tradeoff"
                hint = "Beste inhoudelijke match, met duidelijke afwegingen in capaciteit/wachttijd/regio."
            else:
                hint_code = "top_low_confidence"
                hint = "Geen sterke match gevonden; extra verificatie nodig."
        else:
            if candidate["has_capacity_issue"] is False and top_candidate["has_capacity_issue"] is True:
                hint_code = "capacity_alternative"
                hint = "Overweeg deze optie als alternatief vanwege betere capaciteit."
            elif candidate["wait_days"] < top_candidate["wait_days"] and top_candidate["wait_days"] >= 28:
                hint_code = "wait_time_alternative"
                hint = "Overweeg deze optie als alternatief met kortere wachttijd."
            elif len(trade_offs) < len(top_trade_offs):
                hint_code = "lower_risk_alternative"
                hint = "Overweeg deze optie als compromis met minder operationele risico's."
            elif confidence == "high" and top_confidence != "high":
                hint_code = "high_confidence_alternative"
                hint = "Sterk alternatief met hogere confidence dan de eerste optie."

            if top_trade_offs:
                comparison_to_top = (
                    f"Topoptie heeft {len(top_trade_offs)} trade-off(s), deze optie {len(trade_offs)}."
                )

        hints.append(
            {
                "provider_id": candidate["provider_id"],
                "confidence": confidence,
                "has_capacity_issue": candidate["has_capacity_issue"],
                "wait_days": candidate["wait_days"],
                "has_region_mismatch": candidate["has_region_mismatch"],
                "hint_code": hint_code,
                "hint": hint,
                "trade_offs": trade_offs,
                "comparison_to_top": comparison_to_top,
            }
        )

    return hints


def evaluate_case_intelligence(case_data: Dict[str, Any]) -> Dict[str, Any]:
    _validate_case_data(case_data)

    missing_information = detect_missing_information(case_data)
    risk_signals = detect_risk_signals(case_data)
    next_best_action = determine_next_best_action(
        case_data,
        missing_information=missing_information,
        risk_signals=risk_signals,
    )
    candidate_hints = generate_candidate_hints(case_data)

    stop_action_codes = {
        "fill_missing_information",
        "complete_assessment",
        "run_matching",
        "follow_up_provider_response",
        "review_matching_quality",
        "validate_capacity_wait",
        "resolve_placement_stall",
    }
    high_risk_signal_codes = {
        "open_signals",
        "repeated_rejections",
        "weak_matching_quality",
        "capacity_risk",
        "long_wait_risk",
        "placement_stalled",
        "provider_not_responding",
        "high_urgency_response_delay",
        "provider_no_capacity",
    }

    signal_codes = {signal.get("code") for signal in risk_signals}
    should_stop = bool(missing_information) or next_best_action["code"] in stop_action_codes
    if signal_codes.intersection(high_risk_signal_codes):
        should_stop = True

    stop_reasons: List[str] = []
    if missing_information:
        stop_reasons.append("Ontbrekende gegevens moeten eerst worden aangevuld.")
    if next_best_action["code"] in stop_action_codes:
        stop_reasons.append(next_best_action["reason"])
    for signal in risk_signals:
        if signal.get("code") in high_risk_signal_codes:
            stop_reasons.append(signal.get("message") or "")

    safe_to_proceed = not should_stop

    return {
        "missing_information": missing_information,
        "risk_signals": risk_signals,
        "next_best_action": next_best_action,
        "candidate_hints": candidate_hints,
        "safe_to_proceed": safe_to_proceed,
        "stop_reasons": [reason for reason in stop_reasons if reason],
    }
