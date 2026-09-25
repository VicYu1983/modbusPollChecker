from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

from pymodbus.client import ModbusTcpClient

from .schemas import CheckResult, DeviceConfig


class ModbusTcpAdapter:
    def check_device(self, device: DeviceConfig) -> CheckResult:
        started = perf_counter()
        values: list[int | bool] = []
        status = "FAIL"
        error_type: str | None = None
        error_message: str | None = None
        client = ModbusTcpClient(
            str(device.ip),
            port=device.port,
            timeout=device.response_timeout_ms / 1000,
        )
        try:
            if not client.connect():
                error_type = "CONNECTION_FAILED"
                error_message = "connection failed"
            else:
                if device.function == "01":
                    response = client.read_coils(
                        address=device.address,
                        count=device.quantity,
                        device_id=device.unit_id,
                    )
                elif device.function == "02":
                    response = client.read_discrete_inputs(
                        address=device.address,
                        count=device.quantity,
                        device_id=device.unit_id,
                    )
                elif device.function == "03":
                    response = client.read_holding_registers(
                        address=device.address,
                        count=device.quantity,
                        device_id=device.unit_id,
                    )
                else:
                    response = client.read_input_registers(
                        address=device.address,
                        count=device.quantity,
                        device_id=device.unit_id,
                    )
                if response.isError():
                    error_type = "MODBUS_EXCEPTION"
                    error_message = str(response)
                else:
                    values = (
                        list(response.bits[:device.quantity])
                        if device.function in {"01", "02"}
                        else list(response.registers)
                    )
                    status = "PASS" if self._matches_expected(values, device.expected) else "FAIL"
                    if status == "FAIL" and device.expected:
                        error_type = "UNEXPECTED_VALUE"
                        error_message = f"expected {device.expected}"
        except TimeoutError as error:
            status = "TIMEOUT"
            error_type = "TIMEOUT"
            error_message = str(error) or "Modbus response timeout"
        except Exception as error:  # pymodbus transport errors vary by version.
            error_type = "MODBUS_ERROR"
            error_message = str(error)
        finally:
            client.close()

        return CheckResult(
            device_name=device.name,
            timestamp=datetime.now(timezone.utc),
            status=status,
            ip=device.ip,
            port=device.port,
            unit_id=device.unit_id,
            function=device.function,
            address=device.address,
            plc_address=self._plc_address(device),
            quantity=device.quantity,
            values=values,
            elapsed_ms=round((perf_counter() - started) * 1000),
            error_type=error_type,
            error_message=error_message,
        )

    @staticmethod
    def _plc_address(device: DeviceConfig) -> int:
        base_addresses = {"01": 1, "02": 10001, "03": 40001, "04": 30001}
        return base_addresses[device.function] + device.address

    @staticmethod
    def _matches_expected(values: list[int | bool], expected: str | None) -> bool:
        if not expected:
            return True
        expected = expected.strip()
        if values and all(isinstance(value, bool) for value in values):
            expected_values = [value.strip().lower() for value in expected.split(",")]
            return values == [value in {"true", "1", "on"} for value in expected_values]
        if ".." in expected:
            lower, upper = (int(value.strip()) for value in expected.split("..", 1))
            return all(lower <= value <= upper for value in values)
        return values == [int(value.strip()) for value in expected.split(",")]
