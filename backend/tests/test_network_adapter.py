from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from app import main
from app.network_adapter import NetworkAdapter, PingProbeResult, TcpProbeResult
from app.schemas import (
    DeviceConfig,
    NetworkCheckRequest,
    NetworkCheckResult,
    SiteConfig,
)
from app.site_store import SiteStore


class NetworkAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.device = DeviceConfig(name="PLC-01", ip="127.0.0.1", ping_attempts=2)
        self.adapter = NetworkAdapter()

    def test_parses_windows_english_and_chinese_ping_times(self) -> None:
        self.assertEqual(
            self.adapter._parse_ping_output("Reply from 127.0.0.1: time<1ms\n時間=2.4ms"),
            [1.0, 2.4],
        )

    def test_windows_ping_arguments_use_one_request_per_interval(self) -> None:
        with patch("app.network_adapter.sys.platform", "win32"):
            self.assertEqual(
                self.adapter._ping_arguments("192.0.2.10", 750),
                ("-n", "1", "-w", "750", "192.0.2.10"),
            )

    def test_legacy_device_config_gets_network_defaults(self) -> None:
        device = DeviceConfig.model_validate({"name": "Legacy", "ip": "192.0.2.1"})
        self.assertTrue(device.enabled)
        self.assertEqual(device.ping_attempts, 4)
        self.assertEqual(device.tcp_timeout_ms, 2000)
        self.assertIsNone(device.tcp_port)

    async def test_ping_failure_with_open_tcp_is_partial(self) -> None:
        with (
            patch.object(
                self.adapter,
                "_ping_device",
                new=AsyncMock(return_value=PingProbeResult("TIMEOUT", 0, error_type="ping_timeout")),
            ),
            patch.object(
                self.adapter,
                "_test_tcp",
                new=AsyncMock(return_value=TcpProbeResult("OPEN", 4.2)),
            ),
        ):
            result = await self.adapter.check_device(self.device)

        self.assertEqual(result.ping_loss_percent, 100)
        self.assertEqual(result.tcp_state, "OPEN")
        self.assertEqual(result.overall_status, "PARTIAL")
        self.assertEqual(result.failure_stage, "PING")

    async def test_tcp_timeout_and_closed_are_distinct(self) -> None:
        ping = PingProbeResult("PASS", 2, (1.0, 2.0))
        for tcp, expected in (
            (TcpProbeResult("TIMEOUT", error_type="tcp_timeout"), "TIMEOUT"),
            (TcpProbeResult("CLOSED", error_type="connection_refused"), "FAIL"),
        ):
            with (
                patch.object(self.adapter, "_ping_device", new=AsyncMock(return_value=ping)),
                patch.object(self.adapter, "_test_tcp", new=AsyncMock(return_value=tcp)),
            ):
                result = await self.adapter.check_device(self.device)
            self.assertEqual(result.overall_status, expected)
            self.assertEqual(result.failure_stage, "TCP")

    async def test_network_only_does_not_open_tcp_connection(self) -> None:
        with (
            patch.object(
                self.adapter,
                "_ping_device",
                new=AsyncMock(return_value=PingProbeResult("PASS", 2, (1.0, 2.0))),
            ),
            patch.object(self.adapter, "_test_tcp", new=AsyncMock()) as test_tcp,
        ):
            result = await self.adapter.check_device(self.device, "network_only")

        test_tcp.assert_not_awaited()
        self.assertEqual(result.overall_status, "PASS")
        self.assertEqual(result.tcp_state, "NOT_TESTED")

    async def test_ping_failure_policy_skips_tcp_with_timeout_status(self) -> None:
        device = self.device.model_copy(update={"skip_when_ping_failed": True})
        with (
            patch.object(
                self.adapter,
                "_ping_device",
                new=AsyncMock(return_value=PingProbeResult("TIMEOUT", 0)),
            ),
            patch.object(self.adapter, "_test_tcp", new=AsyncMock()) as test_tcp,
        ):
            result = await self.adapter.check_device(device)

        test_tcp.assert_not_awaited()
        self.assertEqual(result.overall_status, "TIMEOUT")
        self.assertEqual(result.error_type, "network_timeout")

    async def test_cancelled_ping_kills_and_reaps_subprocess(self) -> None:
        process = SimpleNamespace(returncode=None, kill=Mock())
        calls = 0

        async def communicate() -> tuple[bytes, bytes]:
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.Event().wait()
            return b"", b""

        process.communicate = AsyncMock(side_effect=communicate)
        with patch("app.network_adapter.asyncio.create_subprocess_exec", return_value=process):
            task = asyncio.create_task(self.adapter._ping_device(self.device))
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        process.kill.assert_called_once()
        self.assertEqual(process.communicate.await_count, 2)

    async def test_ipv6_is_a_config_error_without_network_probes(self) -> None:
        device = DeviceConfig(name="PLC-v6", ip="::1")
        with (
            patch.object(self.adapter, "_ping_device", new=AsyncMock()) as ping,
            patch.object(self.adapter, "_test_tcp", new=AsyncMock()) as tcp,
        ):
            result = await self.adapter.check_device(device)

        ping.assert_not_awaited()
        tcp.assert_not_awaited()
        self.assertEqual(result.overall_status, "CONFIG_ERROR")
        self.assertEqual(result.failure_stage, "CONFIG")
        self.assertEqual(result.error_type, "ipv4_required")


class NetworkApiTests(unittest.TestCase):
    def test_single_device_endpoint_checks_only_configured_device_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SiteStore(Path(directory))
            store.save(
                SiteConfig(
                    site_name="Test",
                    devices=[DeviceConfig(name="PLC-01", ip="127.0.0.1")],
                )
            )
            with patch.object(main, "store", store):
                with self.assertRaises(HTTPException) as raised:
                    asyncio.run(main.check_network_device(NetworkCheckRequest(device_name="192.0.2.99")))

        self.assertEqual(raised.exception.status_code, 404)

    def test_single_device_endpoint_returns_network_result(self) -> None:
        device_result = NetworkCheckResult(
            device_name="PLC-01",
            target_ip="127.0.0.1",
            timestamp="2026-09-27T00:00:00Z",
            mode="network_and_port",
            ping_state="PASS",
            ping_attempts=4,
            ping_success_count=4,
            ping_loss_percent=0,
            tcp_port=502,
            tcp_state="OPEN",
            overall_status="PASS",
        )
        fake_adapter = SimpleNamespace(check_device=AsyncMock(return_value=device_result))
        with tempfile.TemporaryDirectory() as directory:
            store = SiteStore(Path(directory))
            store.save(
                SiteConfig(
                    site_name="Test",
                    devices=[DeviceConfig(name="PLC-01", ip="127.0.0.1")],
                )
            )
            with patch.multiple(main, store=store, network_adapter=fake_adapter):
                result = asyncio.run(main.check_network_device(NetworkCheckRequest(device_name="PLC-01")))

        self.assertEqual(result.overall_status, "PASS")
        fake_adapter.check_device.assert_awaited_once()

    def test_full_stack_runs_modbus_after_tcp_and_reports_failure_stage(self) -> None:
        device_result = NetworkCheckResult(
            device_name="PLC-01",
            target_ip="127.0.0.1",
            timestamp="2026-09-27T00:00:00Z",
            mode="full_stack",
            ping_state="PASS",
            ping_attempts=4,
            ping_success_count=4,
            tcp_port=502,
            tcp_state="OPEN",
            overall_status="PASS",
        )
        network = SimpleNamespace(check_device=AsyncMock(return_value=device_result))
        modbus_checker = SimpleNamespace(
            check_device=Mock(
                return_value=SimpleNamespace(
                    status="FAIL",
                    error_type="modbus_exception",
                    error_message="Modbus exception",
                )
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            store = SiteStore(Path(directory))
            store.save(
                SiteConfig(
                    site_name="Test",
                    devices=[DeviceConfig(name="PLC-01", ip="127.0.0.1")],
                )
            )
            services = SimpleNamespace(adapter=modbus_checker)
            with patch.multiple(
                main,
                store=store,
                network_adapter=network,
                check_service=services,
            ):
                result = asyncio.run(
                    main.check_network_device(
                        NetworkCheckRequest(device_name="PLC-01", mode="full_stack")
                    )
                )

        modbus_checker.check_device.assert_called_once()
        self.assertEqual(result.overall_status, "FAIL")
        self.assertEqual(result.failure_stage, "MODBUS")
        self.assertEqual(result.modbus_error_type, "modbus_exception")

    def test_profile_endpoint_does_not_run_modbus_for_ping_device(self) -> None:
        device_result = NetworkCheckResult(
            device_name="PLC-01",
            target_ip="127.0.0.1",
            timestamp="2026-09-27T00:00:00Z",
            mode="network_only",
            check_profile="ping",
            ping_state="PASS",
            ping_attempts=4,
            ping_success_count=4,
            ping_loss_percent=0,
            tcp_state="NOT_TESTED",
            overall_status="PASS",
        )
        network = SimpleNamespace(check_device=AsyncMock(return_value=device_result))
        modbus_checker = SimpleNamespace(check_device=Mock())
        with tempfile.TemporaryDirectory() as directory:
            store = SiteStore(Path(directory))
            store.save(
                SiteConfig(
                    site_name="Test",
                    devices=[DeviceConfig(name="PLC-01", ip="127.0.0.1", check_profile="ping")],
                )
            )
            services = SimpleNamespace(adapter=modbus_checker)
            with patch.multiple(
                main,
                store=store,
                network_adapter=network,
                check_service=services,
            ):
                result = asyncio.run(main.check_device_by_profile("PLC-01"))

        modbus_checker.check_device.assert_not_called()
        self.assertEqual(result.check_profile, "ping")
        self.assertIsNone(result.modbus_status)


if __name__ == "__main__":
    unittest.main()
