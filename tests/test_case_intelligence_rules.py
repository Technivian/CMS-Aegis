from datetime import date, timedelta
import unittest

from contracts.case_intelligence import (
    detect_missing_information,
    detect_risk_signals,
    determine_next_best_action,
    evaluate_case_intelligence,
    generate_candidate_hints,
)


class CaseIntelligenceRulesTests(unittest.TestCase):
    def _base_case_data(self):
        return {
            "phase": "MATCHING",
            "care_category": "Jeugd",
            "urgency": "MEDIUM",
            "assessment_complete": True,
            "matching_run_exists": True,
            "top_match_confidence": "high",
            "top_match_has_capacity_issue": False,
            "top_match_wait_days": 7,
            "selected_provider_id": 42,
            "placement_status": "IN_REVIEW",
            "placement_updated_at": date(2026, 4, 10),
            "rejected_provider_count": 0,
            "open_signal_count": 0,
            "open_task_count": 1,
            "case_updated_at": date(2026, 4, 13),
            "candidate_suggestions": [
                {
                    "provider_id": 42,
                    "confidence": "high",
                    "has_capacity_issue": False,
                    "wait_days": 7,
                },
                {
                    "provider_id": 43,
                    "confidence": "medium",
                    "has_capacity_issue": False,
                    "wait_days": 9,
                },
            ],
            "now": date(2026, 4, 14),
        }

    def test_next_best_action_precedence_missing_information_wins(self):
        case_data = self._base_case_data()
        case_data["care_category"] = None
        case_data["assessment_complete"] = False
        case_data["matching_run_exists"] = False
        case_data["top_match_confidence"] = "low"
        case_data["top_match_has_capacity_issue"] = True

        action = determine_next_best_action(case_data)

        self.assertEqual(action["code"], "fill_missing_information")
        self.assertEqual(action["priority"], 1)

    def test_next_best_action_precedence_assessment_before_matching(self):
        case_data = self._base_case_data()
        case_data["assessment_complete"] = False
        case_data["matching_run_exists"] = False

        action = determine_next_best_action(case_data)

        self.assertEqual(action["code"], "complete_assessment")
        self.assertEqual(action["priority"], 2)

    def test_next_best_action_precedence_matching_before_quality(self):
        case_data = self._base_case_data()
        case_data["matching_run_exists"] = False
        case_data["top_match_confidence"] = "low"

        action = determine_next_best_action(case_data)

        self.assertEqual(action["code"], "run_matching")
        self.assertEqual(action["priority"], 3)

    def test_next_best_action_precedence_quality_before_capacity_and_stall(self):
        case_data = self._base_case_data()
        case_data["top_match_confidence"] = "low"
        case_data["top_match_has_capacity_issue"] = True
        case_data["placement_updated_at"] = case_data["now"] - timedelta(days=10)

        action = determine_next_best_action(case_data)

        self.assertEqual(action["code"], "review_matching_quality")
        self.assertEqual(action["priority"], 4)

    def test_next_best_action_precedence_capacity_before_stall(self):
        case_data = self._base_case_data()
        case_data["top_match_has_capacity_issue"] = True
        case_data["placement_updated_at"] = case_data["now"] - timedelta(days=10)

        action = determine_next_best_action(case_data)

        self.assertEqual(action["code"], "validate_capacity_wait")
        self.assertEqual(action["priority"], 5)

    def test_next_best_action_precedence_stall_before_monitor(self):
        case_data = self._base_case_data()
        case_data["placement_updated_at"] = case_data["now"] - timedelta(days=8)

        action = determine_next_best_action(case_data)

        self.assertEqual(action["code"], "resolve_placement_stall")
        self.assertEqual(action["priority"], 6)

    def test_next_best_action_monitor_when_no_blockers(self):
        case_data = self._base_case_data()
        case_data["placement_status"] = "APPROVED"

        action = determine_next_best_action(case_data)

        self.assertEqual(action["code"], "monitor")
        self.assertEqual(action["priority"], 7)

    def test_missing_information_detection(self):
        case_data = self._base_case_data()
        case_data["phase"] = ""
        case_data["care_category"] = None
        case_data["urgency"] = None
        case_data["selected_provider_id"] = None
        case_data["matching_run_exists"] = True
        case_data["top_match_confidence"] = None
        case_data["has_preferred_region"] = False
        case_data["has_assessment_summary"] = False
        case_data["has_client_age_category"] = False

        alerts = detect_missing_information(case_data)
        alert_codes = {alert["code"] for alert in alerts}

        self.assertIn("missing_phase", alert_codes)
        self.assertIn("missing_care_category", alert_codes)
        self.assertIn("missing_urgency", alert_codes)
        self.assertIn("missing_selected_provider", alert_codes)
        self.assertIn("missing_top_match_confidence", alert_codes)
        self.assertIn("missing_region", alert_codes)
        self.assertIn("missing_assessment_summary", alert_codes)
        self.assertIn("missing_age_category", alert_codes)

    def test_risk_signal_combinations(self):
        case_data = self._base_case_data()
        case_data["open_signal_count"] = 2
        case_data["rejected_provider_count"] = 3
        case_data["top_match_confidence"] = "low"
        case_data["top_match_has_capacity_issue"] = True
        case_data["top_match_wait_days"] = 35
        case_data["open_task_count"] = 6

        signals = detect_risk_signals(case_data)
        signal_codes = {signal["code"] for signal in signals}

        self.assertIn("open_signals", signal_codes)
        self.assertIn("repeated_rejections", signal_codes)
        self.assertIn("weak_matching_quality", signal_codes)
        self.assertIn("capacity_risk", signal_codes)
        self.assertIn("long_wait_risk", signal_codes)
        self.assertIn("task_backlog", signal_codes)

    def test_candidate_hint_generation(self):
        case_data = self._base_case_data()
        case_data["candidate_suggestions"] = [
            {
                "provider_id": 1,
                "confidence": "low",
                "has_capacity_issue": True,
                "wait_days": 40,
            },
            {
                "provider_id": 2,
                "confidence": "high",
                "has_capacity_issue": False,
                "wait_days": 8,
            },
        ]
        case_data["top_match_confidence"] = "low"
        case_data["top_match_has_capacity_issue"] = True
        case_data["top_match_wait_days"] = 40

        hints = generate_candidate_hints(case_data)

        self.assertEqual(hints[0]["hint_code"], "top_low_confidence")
        self.assertEqual(hints[1]["hint_code"], "capacity_alternative")

    def test_time_based_rules_stale_case_and_delayed_placement(self):
        case_data = self._base_case_data()
        case_data["placement_status"] = "IN_REVIEW"
        case_data["placement_updated_at"] = case_data["now"] - timedelta(days=9)
        case_data["case_updated_at"] = case_data["now"] - timedelta(days=12)

        signals = detect_risk_signals(case_data)
        signal_codes = {signal["code"] for signal in signals}

        self.assertIn("placement_stalled", signal_codes)
        self.assertIn("stale_case", signal_codes)

    def test_overall_case_intelligence_evaluation_shape(self):
        result = evaluate_case_intelligence(self._base_case_data())

        self.assertIn("missing_information", result)
        self.assertIn("risk_signals", result)
        self.assertIn("next_best_action", result)
        self.assertIn("candidate_hints", result)

    def test_scenario_clean_easy_case_feels_automatic(self):
        # Scenario 1: complete assessment, clear category, high urgency,
        # strong providers, and high-confidence top match.
        case_data = self._base_case_data()
        case_data["urgency"] = "HIGH"
        case_data["assessment_complete"] = True
        case_data["care_category"] = "Jeugd"
        case_data["matching_run_exists"] = True
        case_data["top_match_confidence"] = "high"
        case_data["top_match_has_capacity_issue"] = False
        case_data["top_match_wait_days"] = 5
        case_data["placement_status"] = "APPROVED"
        case_data["candidate_suggestions"] = [
            {
                "provider_id": 101,
                "confidence": "high",
                "has_capacity_issue": False,
                "wait_days": 5,
            },
            {
                "provider_id": 102,
                "confidence": "medium",
                "has_capacity_issue": False,
                "wait_days": 7,
            },
        ]

        result = evaluate_case_intelligence(case_data)

        self.assertEqual(result["missing_information"], [])
        self.assertEqual(result["risk_signals"], [])
        self.assertEqual(result["next_best_action"]["code"], "monitor")
        self.assertEqual(result["candidate_hints"][0]["provider_id"], 101)
        self.assertEqual(result["candidate_hints"][0]["hint_code"], "top_recommended")
        self.assertIn("Beste optie", result["candidate_hints"][0]["hint"])

    def test_scenario_messy_trade_off_case_feels_defensible(self):
        # Scenario 2: strong specialization intent, but real tensions:
        # limited capacity, longer wait, weaker region fit, medium confidence.
        case_data = self._base_case_data()
        case_data["assessment_complete"] = True
        case_data["care_category"] = "Jeugd"
        case_data["urgency"] = "HIGH"
        case_data["matching_run_exists"] = True
        case_data["top_match_confidence"] = "medium"
        case_data["top_match_has_capacity_issue"] = True
        case_data["top_match_wait_days"] = 35
        case_data["placement_status"] = "REJECTED"
        case_data["candidate_suggestions"] = [
            {
                "provider_id": 201,
                "confidence": "medium",
                "has_capacity_issue": True,
                "wait_days": 35,
                "has_region_mismatch": True,
            },
            {
                "provider_id": 202,
                "confidence": "medium",
                "has_capacity_issue": False,
                "wait_days": 14,
                "has_region_mismatch": False,
            },
        ]

        result = evaluate_case_intelligence(case_data)
        signal_codes = {signal["code"] for signal in result["risk_signals"]}
        top_hint = result["candidate_hints"][0]
        alternative_hint = result["candidate_hints"][1]

        # Tension is explicit in risk signals.
        self.assertIn("capacity_risk", signal_codes)
        self.assertIn("long_wait_risk", signal_codes)

        # Next action should guide toward validating trade-offs before committing.
        self.assertEqual(result["next_best_action"]["code"], "validate_capacity_wait")

        # Top option should show explicit trade-offs, not generic text.
        self.assertEqual(top_hint["hint_code"], "top_tradeoff")
        self.assertTrue(any("capaciteit" in item.lower() for item in top_hint["trade_offs"]))
        self.assertTrue(any("wachttijd" in item.lower() for item in top_hint["trade_offs"]))
        self.assertTrue(any("regio" in item.lower() for item in top_hint["trade_offs"]))

        # Alternative should help decision-making with a clearer compromise profile.
        self.assertIn(alternative_hint["hint_code"], {"capacity_alternative", "wait_time_alternative", "lower_risk_alternative"})
        self.assertIn("trade-off", alternative_hint["comparison_to_top"].lower())

    def test_scenario_bad_risky_case_blocks_and_forces_correction(self):
        # Scenario 3: bad/risky state with multiple red flags.
        case_data = self._base_case_data()
        case_data["care_category"] = None  # incomplete data
        case_data["assessment_complete"] = False
        case_data["matching_run_exists"] = True
        case_data["top_match_confidence"] = "low"
        case_data["top_match_has_capacity_issue"] = True
        case_data["top_match_wait_days"] = 45
        case_data["rejected_provider_count"] = 3
        case_data["placement_status"] = "IN_REVIEW"
        case_data["placement_updated_at"] = case_data["now"] - timedelta(days=12)
        case_data["candidate_suggestions"] = [
            {
                "provider_id": 301,
                "confidence": "low",
                "has_capacity_issue": True,
                "wait_days": 45,
                "has_region_mismatch": True,
            }
        ]

        result = evaluate_case_intelligence(case_data)
        signal_codes = {signal["code"] for signal in result["risk_signals"]}

        # System should block progression in this state.
        self.assertFalse(result["safe_to_proceed"])
        self.assertGreater(len(result["stop_reasons"]), 0)

        # Warnings should be strong and concrete.
        self.assertIn("weak_matching_quality", signal_codes)
        self.assertIn("capacity_risk", signal_codes)
        self.assertIn("long_wait_risk", signal_codes)
        self.assertIn("repeated_rejections", signal_codes)
        self.assertIn("placement_stalled", signal_codes)

        # Next action must be corrective, not permissive.
        self.assertEqual(result["next_best_action"]["code"], "fill_missing_information")


if __name__ == "__main__":
    unittest.main()
