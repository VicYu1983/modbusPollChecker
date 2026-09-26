from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.domain.diagnosis import diagnose
from app.schemas import CheckResult


def make_result(status: str, error_type: str | None = None) -> CheckResult:
    return CheckResult(
        device_name="PLC-01",
        timestamp=datetime.now(timezone.utc),
        status=status,
        ip="127.0.0.1",
        port=502,
        unit_id=1,
        function="03",
        address=0,
        plc_address=40001,
        quantity=1,
        elapsed_ms=25,
        error_type=error_type,
    )


class DiagnosisTests(unittest.TestCase):
    def test_pass_result_has_no_diagnosis(self) -> None:
        self.assertIsNone(diagnose(make_result("PASS")))

    def test_timeout_returns_possible_checks_without_claiming_root_cause(self) -> None:
        diagnosis = diagnose(make_result("TIMEOUT", "TIMEOUT"))

        self.assertEqual(diagnosis.category, "MODBUS_TIMEOUT")
        self.assertTrue(diagnosis.suggestions)
        self.assertIn("可能", diagnosis.summary)

    def test_known_modbus_errors_map_to_actionable_categories(self) -> None:
        cases = {
            ("FAIL", "CONNECTION_FAILED"): "NETWORK",
            ("FAIL", "MODBUS_EXCEPTION"): "MODBUS_EXCEPTION",
            ("FAIL", "UNEXPECTED_VALUE"): "DATA_MISMATCH",
        }
        for (status, error_type), category in cases.items():
            with self.subTest(error_type=error_type):
                self.assertEqual(
                    diagnose(make_result(status, error_type)).category,
                    category,
                )

    def test_passing_device_with_changed_values_gets_comparison_guidance(self) -> None:
        diagnosis = diagnose(make_result("PASS"), "VALUE_CHANGED")

        self.assertEqual(diagnosis.category, "DATA_MISMATCH")
        self.assertTrue(diagnosis.suggestions)


if __name__ == "__main__":
    unittest.main()