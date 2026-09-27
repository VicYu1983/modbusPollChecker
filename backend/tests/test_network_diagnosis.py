from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.domain.network_diagnosis import diagnose_network
from app.schemas import DeviceConfig, NetworkCheckResult


class NetworkDiagnosisTests(unittest.TestCase):
    @staticmethod
    def _result(**updates: object) -> NetworkCheckResult:
        values: dict[str, object] = {
            "device_name": "PLC-01",
            "target_ip": "192.0.2.10",
            "timestamp": datetime.now(timezone.utc),
            "mode": "network_and_port",
            "ping_state": "PASS",
            "ping_attempts": 4,
            "ping_success_count": 4,
            "ping_loss_percent": 0,
            "ping_avg_ms": 5.0,
            "tcp_port": 502,
            "tcp_state": "OPEN",
            "overall_status": "PASS",
        }
        values.update(updates)
        return NetworkCheckResult.model_validate(values)

    def test_threshold_violations_fail_and_include_actionable_diagnosis(self) -> None:
        device = DeviceConfig(
            name="PLC-01",
            ip="192.0.2.10",
            max_latency_ms=3,
            max_loss_percent=0,
        )
        result = diagnose_network(
            self._result(ping_avg_ms=5.0, ping_loss_percent=25),
            device,
        )

        self.assertEqual(result.overall_status, "FAIL")
        self.assertEqual(result.failure_stage, "PING")
        self.assertEqual(result.error_type, "network_quality_threshold")
        self.assertEqual(len(result.threshold_violations), 2)
        self.assertTrue(result.diagnosis_summary)
        self.assertTrue(result.diagnosis_suggestions)

    def test_ping_failure_with_open_tcp_is_diagnosed_as_icmp_may_be_blocked(self) -> None:
        result = diagnose_network(
            self._result(
                ping_state="TIMEOUT",
                ping_avg_ms=None,
                ping_loss_percent=100,
                tcp_state="OPEN",
                overall_status="PARTIAL",
                failure_stage="PING",
                error_message="Ping 未回應，但 TCP Port 可連線。",
            ),
            DeviceConfig(name="PLC-01", ip="192.0.2.10"),
        )

        self.assertIn("可能停用 ICMP", result.diagnosis_summary)
        self.assertEqual(result.diagnosis_suggestions[0].find("ICMP") >= 0, True)

    def test_values_at_threshold_pass(self) -> None:
        result = diagnose_network(
            self._result(ping_avg_ms=10, ping_loss_percent=10),
            DeviceConfig(name="PLC-01", ip="192.0.2.10", max_latency_ms=10, max_loss_percent=10),
        )

        self.assertEqual(result.overall_status, "PASS")
        self.assertEqual(result.threshold_violations, [])


if __name__ == "__main__":
    unittest.main()
