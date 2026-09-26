import type { DeviceStatus } from "../api/mappers";

export const statusMeta: Record<DeviceStatus, { label: string; color: string }> = {
  PASS: { label: "正常", color: "success" },
  FAIL: { label: "失敗", color: "error" },
  TIMEOUT: { label: "逾時", color: "warning" },
  CONFIG_ERROR: { label: "設定錯誤", color: "error" },
  UNKNOWN: { label: "未檢查", color: "default" },
};
