"""Check multiple Modbus TCP devices from a CSV file."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pymodbus.client import ModbusTcpClient


FUNCTIONS = {"03": "holding", "3": "holding", "04": "input", "4": "input"}


@dataclass
class Device:
    name: str
    ip: str
    port: int
    unit_id: int
    address: int
    quantity: int
    function: str
    expected: str
    timeout_ms: int


@dataclass
class CheckResult:
    timestamp: str
    name: str
    ip: str
    port: int
    unit_id: int
    function: str
    address: int
    quantity: int
    status: str
    values: list[Any]
    elapsed_ms: int
    error: str = ""


def parse_bool(value: str, field_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n", ""}:
        return False
    raise ValueError(f"{field_name} must be true or false")


def parse_address(value: str, function: str) -> int:
    address = int(value.strip())
    if address < 0:
        raise ValueError("address must be non-negative")

    # Accept both Modbus Poll notation (40001/30001) and zero-based addresses.
    if function in {"03", "3"} and 40001 <= address <= 49999:
        return address - 40001
    if function in {"04", "4"} and 30001 <= address <= 39999:
        return address - 30001
    return address


def load_devices(path: Path) -> list[Device]:
    required = {
        "name", "ip", "port", "unit_id", "address", "quantity", "function",
        "expected", "timeout_ms", "enabled",
    }
    devices: list[Device] = []

    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            missing = sorted(required - set(reader.fieldnames or []))
            raise ValueError(f"missing CSV columns: {', '.join(missing)}")

        for line_number, row in enumerate(reader, start=2):
            try:
                function = row["function"].strip()
                if function not in FUNCTIONS:
                    raise ValueError("function must be 03 or 04")
                if not parse_bool(row["enabled"], "enabled"):
                    continue

                device = Device(
                    name=row["name"].strip(),
                    ip=row["ip"].strip(),
                    port=int(row["port"] or 502),
                    unit_id=int(row["unit_id"]),
                    address=parse_address(row["address"], function),
                    quantity=int(row["quantity"]),
                    function=function,
                    expected=row["expected"].strip(),
                    timeout_ms=int(row["timeout_ms"] or 2000),
                )
                if not device.name or not device.ip:
                    raise ValueError("name and ip are required")
                if not 1 <= device.port <= 65535:
                    raise ValueError("port must be between 1 and 65535")
                if not 0 <= device.unit_id <= 247:
                    raise ValueError("unit_id must be between 0 and 247")
                if not 1 <= device.quantity <= 125:
                    raise ValueError("quantity must be between 1 and 125")
                if device.timeout_ms <= 0:
                    raise ValueError("timeout_ms must be positive")
                devices.append(device)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"CSV line {line_number}: {error}") from error

    if not devices:
        raise ValueError("no enabled devices found")
    return devices


def expected_matches(values: list[int], expected: str) -> bool:
    if not expected:
        return True
    expected = expected.strip()
    if ".." in expected:
        lower, upper = (int(value.strip()) for value in expected.split("..", 1))
        return all(lower <= value <= upper for value in values)
    expected_values = [int(value.strip()) for value in expected.split(",")]
    return values == expected_values


def check_device(device: Device) -> CheckResult:
    started = time.perf_counter()
    client = ModbusTcpClient(device.ip, port=device.port, timeout=device.timeout_ms / 1000)
    values: list[Any] = []
    status = "FAIL"
    error = ""

    try:
        if not client.connect():
            status = "FAIL"
            error = "connection failed"
        else:
            if FUNCTIONS[device.function] == "holding":
                response = client.read_holding_registers(
                    address=device.address, count=device.quantity, device_id=device.unit_id
                )
            else:
                response = client.read_input_registers(
                    address=device.address, count=device.quantity, device_id=device.unit_id
                )

            if response.isError():
                error = str(response)
            else:
                values = list(response.registers)
                status = "PASS" if expected_matches(values, device.expected) else "FAIL"
                if status == "FAIL" and device.expected:
                    error = f"expected {device.expected}"
    except Exception as exception:  # Library errors vary by pymodbus transport.
        error = str(exception)
    finally:
        client.close()

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return CheckResult(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        name=device.name,
        ip=device.ip,
        port=device.port,
        unit_id=device.unit_id,
        function=device.function,
        address=device.address,
        quantity=device.quantity,
        status=status,
        values=values,
        elapsed_ms=elapsed_ms,
        error=error,
    )


def write_results(results: list[CheckResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".json":
        output_path.write_text(
            json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return

    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check multiple Modbus TCP devices.")
    parser.add_argument("-i", "--input", type=Path, default=Path("devices.csv"))
    parser.add_argument("-o", "--output", type=Path, default=Path("results.json"))
    parser.add_argument("-c", "--concurrency", type=int, default=10)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.concurrency < 1:
        print("concurrency must be positive", file=sys.stderr)
        return 2

    try:
        devices = load_devices(args.input)
    except (OSError, ValueError) as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2

    results: list[CheckResult] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(check_device, device) for device in devices]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            detail = f" - {result.error}" if result.error else ""
            print(f"[{result.status:<12}] {result.name} ({result.ip}) {result.elapsed_ms} ms{detail}")

    results.sort(key=lambda result: result.name)
    try:
        write_results(results, args.output)
    except OSError as error:
        print(f"output error: {error}", file=sys.stderr)
        return 3

    print(f"saved {len(results)} result(s) to {args.output}")
    return 0 if all(result.status == "PASS" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())