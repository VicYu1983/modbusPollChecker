import type { DeviceConfig } from "../api/client";
import { deviceDefaults } from "../components/formDefaults";

export type RowIssue =
  | "OK"
  | "DUPLICATE_NAME"
  | "INVALID_IP"
  | "INVALID_VALUE"
  | "MISSING_REQUIRED";

export type ParsedRow = {
  /** 來源行號，1-based（含標題列計數） */
  lineNumber: number;
  /** 依標題對應後、套用預設值完成的設備設定 */
  device: DeviceConfig;
  /** 驗證狀態 */
  issue: RowIssue;
  /** 錯誤說明，issue 非 OK 時提供 */
  detail?: string;
};

export type ParseResult = {
  rows: ParsedRow[];
  /** 已辨識的 schema 欄位名稱 */
  recognizedColumns: string[];
  /** 未知標題，將被忽略 */
  unknownColumns: string[];
  /** 缺少的必填欄位 */
  missingRequired: string[];
};

export type Delimiter = "\t" | "," | ";";

const IPV4_PATTERN =
  /^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$/;

const PROFILE_VALUES = new Set(["ping", "ping_tcp", "full_stack"]);
const FUNCTION_VALUES = new Set(["01", "02", "03", "04"]);
const ADDRESS_MODE_VALUES = new Set(["dec", "hex"]);

const BOOL_TRUE = new Set(["true", "1", "是"]);
const BOOL_FALSE = new Set(["false", "0", "否"]);

/** 標題 → DeviceConfig 欄位名稱（正規化後比對） */
const FIELD_ALIASES: Record<string, keyof DeviceConfig> = (() => {
  const keys: Array<keyof DeviceConfig> = [
    "name",
    "ip",
    "port",
    "unit_id",
    "address",
    "quantity",
    "function",
    "expected",
    "address_mode",
    "connect_timeout_ms",
    "response_timeout_ms",
    "scan_rate_ms",
    "delay_between_polls_ms",
    "enabled",
    "check_profile",
    "ping_enabled",
    "ping_attempts",
    "ping_timeout_ms",
    "ping_interval_ms",
    "tcp_check_enabled",
    "tcp_port",
    "tcp_timeout_ms",
    "skip_when_ping_failed",
    "max_latency_ms",
    "max_loss_percent",
  ];
  const map: Record<string, keyof DeviceConfig> = {};
  for (const key of keys) map[key.toLowerCase()] = key;
  return map;
})();

const REQUIRED_FIELDS: Array<keyof DeviceConfig> = ["name", "ip"];

/** 偵測分隔符：Tab > 逗號 > 分號 */
export function detectDelimiter(text: string): Delimiter {
  const firstLine = text.split(/\r?\n/, 1)[0] ?? "";
  const counts: Array<[Delimiter, number]> = [
    ["\t", (firstLine.match(/\t/g) ?? []).length],
    [",", (firstLine.match(/,/g) ?? []).length],
    [";", (firstLine.match(/;/g) ?? []).length],
  ];
  counts.sort((a, b) => b[1] - a[1]);
  return counts[0][1] > 0 ? counts[0][0] : ",";
}

function parseBool(raw: string): boolean | null {
  const value = raw.trim().toLowerCase();
  if (BOOL_TRUE.has(value)) return true;
  if (BOOL_FALSE.has(value)) return false;
  return null;
}

function parseIntField(raw: string): number | null {
  const value = raw.trim();
  if (!/^-?\d+$/.test(value)) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

function parseIntOrNull(raw: string): number | null {
  const value = raw.trim();
  if (!value) return null;
  return parseIntField(value);
}

type FieldParser = (raw: string) => { value: unknown } | { error: string };

const FIELD_PARSERS: Partial<Record<keyof DeviceConfig, FieldParser>> = {
  port: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 1 || value > 65535)
      return { error: "port 必須為 1–65535 的整數" };
    return { value };
  },
  unit_id: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 0 || value > 247)
      return { error: "unit_id 必須為 0–247 的整數" };
    return { value };
  },
  address: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 0)
      return { error: "address 必須為 ≥ 0 的整數" };
    return { value };
  },
  quantity: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 1 || value > 2000)
      return { error: "quantity 必須為 1–2000 的整數" };
    return { value };
  },
  function: (raw) => {
    const value = raw.trim();
    if (!FUNCTION_VALUES.has(value))
      return { error: "function 必須為 01 / 02 / 03 / 04" };
    return { value };
  },
  address_mode: (raw) => {
    const value = raw.trim().toLowerCase();
    if (!ADDRESS_MODE_VALUES.has(value))
      return { error: "address_mode 必須為 dec 或 hex" };
    return { value };
  },
  check_profile: (raw) => {
    const value = raw.trim().toLowerCase();
    if (!PROFILE_VALUES.has(value))
      return { error: "check_profile 必須為 ping / ping_tcp / full_stack" };
    return { value };
  },
  connect_timeout_ms: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 1)
      return { error: "connect_timeout_ms 必須為 ≥ 1 的整數" };
    return { value };
  },
  response_timeout_ms: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 1)
      return { error: "response_timeout_ms 必須為 ≥ 1 的整數" };
    return { value };
  },
  scan_rate_ms: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 0)
      return { error: "scan_rate_ms 必須為 ≥ 0 的整數" };
    return { value };
  },
  delay_between_polls_ms: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 0)
      return { error: "delay_between_polls_ms 必須為 ≥ 0 的整數" };
    return { value };
  },
  enabled: (raw) => {
    const value = parseBool(raw);
    if (value === null) return { error: "enabled 必須為 true/false/1/0/是/否" };
    return { value };
  },
  ping_enabled: (raw) => {
    const value = parseBool(raw);
    if (value === null) return { error: "ping_enabled 必須為 true/false/1/0/是/否" };
    return { value };
  },
  ping_attempts: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 1)
      return { error: "ping_attempts 必須為 ≥ 1 的整數" };
    return { value };
  },
  ping_timeout_ms: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 1)
      return { error: "ping_timeout_ms 必須為 ≥ 1 的整數" };
    return { value };
  },
  ping_interval_ms: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 0)
      return { error: "ping_interval_ms 必須為 ≥ 0 的整數" };
    return { value };
  },
  tcp_check_enabled: (raw) => {
    const value = parseBool(raw);
    if (value === null) return { error: "tcp_check_enabled 必須為 true/false/1/0/是/否" };
    return { value };
  },
  tcp_port: (raw) => {
    const value = parseIntOrNull(raw);
    if (value === null) return { value: null };
    if (value < 1 || value > 65535)
      return { error: "tcp_port 必須為 1–65535 的整數或留空" };
    return { value };
  },
  tcp_timeout_ms: (raw) => {
    const value = parseIntField(raw);
    if (value === null || value < 1)
      return { error: "tcp_timeout_ms 必須為 ≥ 1 的整數" };
    return { value };
  },
  skip_when_ping_failed: (raw) => {
    const value = parseBool(raw);
    if (value === null) return { error: "skip_when_ping_failed 必須為 true/false/1/0/是/否" };
    return { value };
  },
  max_latency_ms: (raw) => {
    const value = parseIntOrNull(raw);
    if (value === null) return { value: null };
    if (value < 0) return { error: "max_latency_ms 必須為 ≥ 0 的整數或留空" };
    return { value };
  },
  max_loss_percent: (raw) => {
    const value = parseIntOrNull(raw);
    if (value === null) return { value: null };
    if (value < 0 || value > 100)
      return { error: "max_loss_percent 必須為 0–100 的整數或留空" };
    return { value };
  },
};

function splitLine(line: string, delimiter: Delimiter): string[] {
  return line.split(delimiter).map((cell) => cell.trim());
}

/** 解析多行文字為 ParseResult（第一列固定為標題列） */
export function parseBatchText(
  text: string,
  options?: {
    delimiter?: Delimiter | "auto";
    existingNames?: string[];
  },
): ParseResult {
  const lines = text
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0);
  if (lines.length === 0) {
    return {
      rows: [],
      recognizedColumns: [],
      unknownColumns: [],
      missingRequired: ["name", "ip"],
    };
  }

  const delimiter =
    !options?.delimiter || options.delimiter === "auto"
      ? detectDelimiter(text)
      : options.delimiter;

  const headers = splitLine(lines[0], delimiter);
  const recognizedColumns: string[] = [];
  const unknownColumns: string[] = [];
  const columnFields: Array<keyof DeviceConfig | null> = headers.map(
    (header) => {
      const field = FIELD_ALIASES[header.toLowerCase()];
      if (field) recognizedColumns.push(field);
      else unknownColumns.push(header);
      return field ?? null;
    },
  );

  const missingRequired = REQUIRED_FIELDS.filter(
    (field) => !recognizedColumns.includes(field),
  );

  const existingNames = new Set(options?.existingNames ?? []);
  const rows: ParsedRow[] = [];

  for (let index = 1; index < lines.length; index += 1) {
    const lineNumber = index + 1;
    const cells = splitLine(lines[index], delimiter);
    const device: DeviceConfig = { ...deviceDefaults };
    let issue: RowIssue = "OK";
    let detail: string | undefined;

    columnFields.forEach((field, columnIndex) => {
      if (!field) return;
      const raw = cells[columnIndex] ?? "";
      if (field === "name") {
        device.name = raw;
        return;
      }
      if (field === "ip") {
        device.ip = raw;
        return;
      }
      if (field === "expected") {
        device.expected = raw || null;
        return;
      }
      if (!raw) return; // 空值套用預設
      const parser = FIELD_PARSERS[field];
      if (!parser) return;
      const result = parser(raw);
      if ("error" in result) {
        issue = "INVALID_VALUE";
        detail = detail ?? `第 ${columnIndex + 1} 欄（${field}）：${result.error}`;
        return;
      }
      (device as Record<string, unknown>)[field] = result.value;
    });

    if (issue === "OK") {
      if (!device.name) {
        issue = "MISSING_REQUIRED";
        detail = "name 不可空白";
      } else if (!device.ip || !IPV4_PATTERN.test(device.ip)) {
        issue = "INVALID_IP";
        detail = `IP 格式錯誤：${device.ip || "(空白)"}`;
      } else if (existingNames.has(device.name)) {
        issue = "DUPLICATE_NAME";
        detail = `名稱重複：${device.name}`;
      } else {
        existingNames.add(device.name);
      }
    }

    rows.push({ lineNumber, device, issue, detail });
  }

  return { rows, recognizedColumns, unknownColumns, missingRequired };
}