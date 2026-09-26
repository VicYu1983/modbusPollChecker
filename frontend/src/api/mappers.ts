import type { CheckResult, DeviceConfig } from "./client";

export type DeviceStatus = "PASS" | "FAIL" | "TIMEOUT" | "CONFIG_ERROR" | "UNKNOWN";

export type Device = DeviceConfig & {
  status: DeviceStatus;
  lastChecked: string;
  values?: Array<number | boolean>;
  elapsedMs?: number;
  error?: string;
};

export function toDevice(device: DeviceConfig, result?: CheckResult): Device {
  return {
    ...device,
    status: result?.status ?? "UNKNOWN",
    lastChecked: result
      ? new Date(result.timestamp).toLocaleString()
      : "尚未檢查",
    values: result?.values,
    elapsedMs: result?.elapsed_ms,
    error: result?.error_message ?? undefined,
  };
}

export function toConfig(device: Device): DeviceConfig {
  const config = { ...device } as Partial<Device>;
  delete config.status;
  delete config.lastChecked;
  delete config.values;
  delete config.elapsedMs;
  delete config.error;
  return config as DeviceConfig;
}
