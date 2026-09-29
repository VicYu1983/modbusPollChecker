import { useMemo, useState } from "react";
import {
  Alert,
  App as AntApp,
  Button,
  Input,
  Progress,
  Space,
  Table,
  Tag,
  Tooltip,
  Upload,
} from "antd";
import type { TableColumnsType, UploadProps } from "antd";
import { CheckCircleOutlined, UploadOutlined } from "@ant-design/icons";
import { api, type DeviceConfig } from "../api/client";
import type { Device } from "../api/mappers";
import {
  parseBatchText,
  type ParseResult,
  type ParsedRow,
  type RowIssue,
} from "../utils/batchParse";

const ISSUE_META: Record<RowIssue, { label: string; color: string }> = {
  OK: { label: "可新增", color: "success" },
  DUPLICATE_NAME: { label: "名稱重複", color: "warning" },
  INVALID_IP: { label: "IP 格式錯誤", color: "error" },
  INVALID_VALUE: { label: "欄位值錯誤", color: "error" },
  MISSING_REQUIRED: { label: "缺少必填", color: "error" },
};

type SubmitState = Record<string, "pending" | "success" | "failed" | undefined>;

type BatchAddPanelProps = {
  /** 現有設備，用於名稱重複檢查 */
  existingDevices: Device[];
  /** 批次新增完成後回呼，傳入成功新增的 DeviceConfig 陣列 */
  onBatchAdded: (added: DeviceConfig[]) => void | Promise<void>;
};

export function BatchAddPanel({ existingDevices, onBatchAdded }: BatchAddPanelProps) {
  const { message } = AntApp.useApp();
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitProgress, setSubmitProgress] = useState(0);
  const [submitState, setSubmitState] = useState<SubmitState>({});
  const [submitSummary, setSubmitSummary] = useState<{ ok: number; failed: number } | null>(null);

  const existingNames = useMemo(
    () => existingDevices.map((device) => device.name),
    [existingDevices],
  );

  const parseResult: ParseResult = useMemo(
    () => parseBatchText(text, { existingNames }),
    [text, existingNames],
  );

  const selectedRows = parseResult.rows.filter((row) => row.issue === "OK");
  const duplicateCount = parseResult.rows.filter(
    (row) => row.issue === "DUPLICATE_NAME",
  ).length;
  const errorCount = parseResult.rows.filter(
    (row) => ["INVALID_IP", "INVALID_VALUE", "MISSING_REQUIRED"].includes(row.issue),
  ).length;
  const canSubmit = selectedRows.length > 0 && !submitting;

  const columns: TableColumnsType<ParsedRow> = [
    {
      title: "行",
      dataIndex: "lineNumber",
      key: "lineNumber",
      width: 60,
    },
    {
      title: "name",
      key: "name",
      render: (_, row) => row.device.name || "(空白)",
    },
    {
      title: "ip",
      key: "ip",
      render: (_, row) => row.device.ip || "(空白)",
    },
    {
      title: "check_profile",
      key: "check_profile",
      width: 110,
      render: (_, row) => row.device.check_profile,
    },
    {
      title: "狀態",
      key: "issue",
      width: 150,
      render: (_, row) => {
        const state = submitState[row.device.name];
        if (state === "success")
          return <Tag color="success" icon={<CheckCircleOutlined />}>新增成功</Tag>;
        if (state === "failed")
          return <Tag color="error">新增失敗</Tag>;
        const meta = ISSUE_META[row.issue];
        return (
          <Tooltip title={row.detail}>
            <Tag color={meta.color}>{meta.label}</Tag>
          </Tooltip>
        );
      },
    },
    {
      title: "說明",
      key: "detail",
      ellipsis: true,
      render: (_, row) => {
        const state = submitState[row.device.name];
        if (state === "failed") return "後端拒絕此筆（詳見訊息）";
        return row.detail ?? "";
      },
    },
  ];

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitProgress(0);
    setSubmitState({});
    setSubmitSummary(null);

    const targets = [...selectedRows];
    const outcomes: Array<{ name: string; ok: boolean }> = [];
    let cursor = 0;
    const worker = async () => {
      while (cursor < targets.length) {
        const index = cursor;
        cursor += 1;
        const row = targets[index];
        try {
          await api.addDevice(row.device);
          outcomes.push({ name: row.device.name, ok: true });
          setSubmitState((current) => ({ ...current, [row.device.name]: "success" }));
        } catch {
          outcomes.push({ name: row.device.name, ok: false });
          setSubmitState((current) => ({ ...current, [row.device.name]: "failed" }));
        }
        setSubmitProgress(Math.round(((index + 1) / targets.length) * 100));
      }
    };
    const limit = Math.min(5, targets.length);
    await Promise.all(Array.from({ length: limit }, () => worker()));

    const okCount = outcomes.filter((outcome) => outcome.ok).length;
    const failedCount = outcomes.length - okCount;
    setSubmitSummary({ ok: okCount, failed: failedCount });
    setSubmitting(false);
    if (okCount > 0) {
      await onBatchAdded(
        targets
          .filter((row) => outcomes.find((o) => o.name === row.device.name)?.ok)
          .map((row) => row.device),
      );
    }
    if (failedCount > 0) message.warning(`${failedCount} 筆新增失敗`);
    else message.success(`成功新增 ${okCount} 筆設備`);
  };

  const uploadProps: UploadProps = {
    accept: ".csv,.txt",
    showUploadList: false,
    beforeUpload: (file) => {
      const reader = new FileReader();
      reader.onload = () => {
        setText(String(reader.result ?? ""));
        message.info("已載入檔案內容，請確認欄位辨識結果");
      };
      reader.readAsText(file);
      return false; // 攔截自動上傳，改由前端讀取內容
    },
  };

  return (
    <div>
      <Alert
        type="info"
        showIcon
        title="CSV 標題請使用設備欄位名稱"
        description={
          <>
            第一列為標題，欄位名稱需與設備 JSON 一致（如 <code>name, ip, port, check_profile</code>）。
            未提供的欄位將套用預設值；<code>check_profile</code> 決定檢查類型（ping / ping_tcp / full_stack）。
          </>
        }
        style={{ marginBottom: 12 }}
      />
      <Upload {...uploadProps}>
        <Button icon={<UploadOutlined />}>上傳 CSV 檔</Button>
      </Upload>
      <Input.TextArea
        aria-label="批次貼上資料"
        placeholder={"name,ip,check_profile\n門禁卡,192.168.1.201,ping\n消防閘道器,192.168.0.50,full_stack"}
        rows={8}
        value={text}
        onChange={(event) => setText(event.target.value)}
        style={{ marginTop: 12, fontFamily: "monospace" }}
      />

      {text.trim() && (
        <div style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 8 }}>
            <Space wrap>
              <Tag color="success">已辨識：{parseResult.recognizedColumns.join(", ") || "無"}</Tag>
              {parseResult.unknownColumns.length > 0 && (
                <Tag color="warning">未知標題（忽略）：{parseResult.unknownColumns.join(", ")}</Tag>
              )}
              {parseResult.missingRequired.length > 0 && (
                <Tag color="error">缺少必填：{parseResult.missingRequired.join(", ")}</Tag>
              )}
            </Space>
          </div>

          <Table<ParsedRow>
            rowKey="lineNumber"
            size="small"
            columns={columns}
            dataSource={parseResult.rows}
            pagination={parseResult.rows.length > 50 ? { pageSize: 50 } : false}
            scroll={{ x: 700 }}
          />

          <div style={{ marginTop: 8, marginBottom: 12 }}>
            共 {parseResult.rows.length} 筆 · 可新增 {selectedRows.length} · 重複 {duplicateCount} · 錯誤 {errorCount}
          </div>

          {submitting && <Progress percent={submitProgress} style={{ marginBottom: 12 }} />}
          {submitSummary && !submitting && (
            <Alert
              type={submitSummary.failed > 0 ? "warning" : "success"}
              showIcon
              title={`成功 ${submitSummary.ok} 筆、失敗 ${submitSummary.failed} 筆`}
              style={{ marginBottom: 12 }}
            />
          )}

          <Space>
            <Button type="primary" disabled={!canSubmit} onClick={() => void handleSubmit()}>
              確認新增 {selectedRows.length} 筆
            </Button>
            <Button
              disabled={submitting || !text}
              onClick={() => {
                setText("");
                setSubmitState({});
                setSubmitSummary(null);
              }}
            >
              清除
            </Button>
          </Space>
        </div>
      )}
    </div>
  );
}