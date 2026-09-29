import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, App as AntApp, Button, Col, Collapse, Input, InputNumber, Row, Segmented, Select, Space, Statistic, Switch, Table, Tag, Tooltip, Typography } from "antd";
import type { FormInstance, TableColumnsType } from "antd";
import { DeleteOutlined, EditOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  api,
  type DeviceConfig,
  type NetworkCheckResult,
  type NetworkCheckStatus,
} from "../api/client";
import type { Device } from "../api/mappers";
import { DeviceEditor } from "./DeviceEditor";
import { BatchAddPanel } from "./BatchAddPanel";

const statusMeta: Record<NetworkCheckStatus, { label: string; color: string; priority: number }> = {
  CONFIG_ERROR: { label: "設定錯誤", color: "error", priority: 0 },
  TIMEOUT: { label: "逾時", color: "warning", priority: 1 },
  FAIL: { label: "失敗", color: "error", priority: 2 },
  PARTIAL: { label: "部分正常", color: "processing", priority: 3 },
  PASS: { label: "正常", color: "success", priority: 4 },
  UNKNOWN: { label: "未知", color: "default", priority: 5 },
};
const profileLabels: Record<Device["check_profile"], string> = {
  ping: "Ping",
  ping_tcp: "Ping + TCP",
  full_stack: "完整檢查",
};
const pingLabels: Record<NetworkCheckResult["ping_state"], string> = {
  PASS: "回應",
  TIMEOUT: "逾時",
  UNREACHABLE: "無法到達",
  NOT_SUPPORTED: "未執行",
  UNKNOWN: "未知",
};
const tcpLabels: Record<NetworkCheckResult["tcp_state"], string> = {
  OPEN: "開啟",
  CLOSED: "關閉",
  TIMEOUT: "逾時",
  UNREACHABLE: "無法到達",
  NOT_TESTED: "未測試",
};

function formatLatency(value: number | null) {
  return value === null ? "—" : `${value.toFixed(1)} ms`;
}

type NetworkPanelProps = {
  siteName: string;
  devices: Device[];
  form: FormInstance<DeviceConfig>;
  editing: Device | null;
  onEdit: (device: Device) => void;
  onRemove: (device: Device) => void;
  onSubmit: () => void | Promise<void>;
  onBatchAdded: (added: DeviceConfig[]) => void | Promise<void>;
};

export function NetworkPanel({ siteName, devices, form, editing, onEdit, onRemove, onSubmit, onBatchAdded }: NetworkPanelProps) {
  const { message } = AntApp.useApp();
  const [addMode, setAddMode] = useState<"single" | "batch">("single");
  const [maxConcurrency, setMaxConcurrency] = useState(20);
  const [checkingAll, setCheckingAll] = useState(false);
  const [checkingDevice, setCheckingDevice] = useState<string | null>(null);
  const [singleResults, setSingleResults] = useState<Record<string, NetworkCheckResult>>({});
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<NetworkCheckStatus | "ALL">("ALL");
  const [autoCheck, setAutoCheck] = useState(false);
  const [autoIntervalMs, setAutoIntervalMs] = useState(600000);
  const [autoChecking, setAutoChecking] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{ batchId: string; completed: number; total: number } | null>(null);
  const autoCheckRef = useRef(false);
  const batchPollRef = useRef<number | undefined>(undefined);

  const availableDevices = devices.filter((device) => device.enabled);

  const resultByDevice = useMemo(() => {
    const results = new Map<string, NetworkCheckResult>();
    for (const [deviceName, result] of Object.entries(singleResults)) {
      results.set(deviceName, result);
    }
    return results;
  }, [singleResults]);

  const resultRows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return availableDevices
      .filter((device) => !needle || `${device.name} ${device.ip}`.toLocaleLowerCase().includes(needle))
      .map((device) => ({ device, result: resultByDevice.get(device.name) }))
      .filter(({ result }) => statusFilter === "ALL" || result?.overall_status === statusFilter)
      .sort((left, right) => {
        const leftPriority = left.result ? statusMeta[left.result.overall_status].priority : 6;
        const rightPriority = right.result ? statusMeta[right.result.overall_status].priority : 6;
        return leftPriority - rightPriority || left.device.name.localeCompare(right.device.name);
      });
  }, [availableDevices, resultByDevice, search, statusFilter]);

  const checkedResults = Array.from(resultByDevice.values());
  const onlineCount = checkedResults.filter((result) => result.overall_status === "PASS").length;
  const attentionCount = checkedResults.filter((result) =>
    ["FAIL", "TIMEOUT", "CONFIG_ERROR", "PARTIAL"].includes(result.overall_status),
  ).length;

  /** 方案 C：Modbus 檢查一律手動，autoCheck 僅涵蓋 ping / ping_tcp 設備 */
  const autoCheckDevices = useMemo(
    () => availableDevices.filter((device) => device.check_profile !== "full_stack"),
    [availableDevices],
  );

  /** 方案 A：建立批次 + 每 2 秒輪詢，逐步將已完成結果寫入 singleResults */
  const runBatchCheck = async (targets: Device[]): Promise<boolean> => {
    if (!targets.length) return false;
    setCheckingAll(true);
    const batchId = await api.createDeviceCheckBatch(siteName, Math.max(1, Math.min(50, maxConcurrency)))
      .then((batch) => batch.id)
      .catch((error: unknown) => {
        message.error(error instanceof Error ? error.message : "批次建立失敗");
        return null;
      });
    if (!batchId) {
      setCheckingAll(false);
      return false;
    }
    setBatchProgress({ batchId, completed: 0, total: targets.length });
    const targetNames = new Set(targets.map((device) => device.name));
    const seen = new Set<string>();
    try {
      for (;;) {
        const detail = await api.getDeviceCheckBatch(batchId);
        for (const record of detail.results) {
          if (!targetNames.has(record.result.device_name) || seen.has(record.result.device_name)) continue;
          seen.add(record.result.device_name);
          setSingleResults((current) => ({ ...current, [record.result.device_name]: record.result }));
        }
        setBatchProgress({ batchId, completed: detail.batch.completed_device_count, total: targets.length });
        if (detail.batch.status !== "pending" && detail.batch.status !== "running") {
          if (detail.batch.status === "completed") message.success(`設備檢查完成（${detail.batch.completed_device_count} 台）`);
          else if (detail.batch.status === "cancelled") message.info("設備檢查已取消");
          else message.error(detail.batch.error_message || "設備檢查批次失敗");
          return detail.batch.status === "completed";
        }
        await new Promise<void>((resolve) => {
          batchPollRef.current = window.setTimeout(resolve, 2000);
        });
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "批次輪詢失敗");
      return false;
    } finally {
      setCheckingAll(false);
      setBatchProgress(null);
    }
  };

  const checkAll = async () => {
    if (!availableDevices.length) return;
    await runBatchCheck(availableDevices);
  };

  const cancelBatch = async () => {
    if (!batchProgress) return;
    try {
      await api.cancelDeviceCheckBatch(batchProgress.batchId);
      message.info("取消中…");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "取消批次失敗");
    }
  };

  const checkOne = async (device: Device) => {
    setCheckingDevice(device.name);
    try {
      const result = await api.checkDevice(device.name);
      setSingleResults((current) => ({ ...current, [device.name]: result }));
      message.success(`${device.name} 網路測試完成`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "單台網路測試失敗");
    } finally {
      setCheckingDevice(null);
    }
  };

  const runAutoCheck = async () => {
    if (autoChecking) return;
    setAutoChecking(true);
    try {
      await runBatchCheck(autoCheckDevices);
    } finally {
      setAutoChecking(false);
    }
  };

  useEffect(() => {
    autoCheckRef.current = autoCheck;
  }, [autoCheck]);

  useEffect(() => {
    if (!autoCheck) return;
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      if (cancelled) return;
      await runAutoCheck();
      if (cancelled || !autoCheckRef.current) return;
      timer = window.setTimeout(() => void tick(), autoIntervalMs);
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoCheck, autoIntervalMs, siteName, devices.length]);

  const columns: TableColumnsType<Device> = [
    {
      title: "設備",
      key: "device",
      sorter: (a, b) => a.name.localeCompare(b.name, "zh-Hant"),
      render: (_: unknown, device) => (
        <div className="device-name">
          <strong>{device.name}</strong>
          <span>{device.ip}</span>
        </div>
      ),
    },
    {
      title: "檢查流程",
      key: "profile",
      render: (_: unknown, device) => profileLabels[device.check_profile],
    },
    {
      title: "Ping",
      key: "ping",
      render: (_: unknown, device) => {
        const result = resultByDevice.get(device.name);
        return result ? (
          <div className="network-cell">
            <strong>{pingLabels[result.ping_state]}</strong>
            <span>{formatLatency(result.ping_avg_ms)}</span>
          </div>
        ) : "—";
      },
    },
    {
      title: "封包遺失",
      key: "loss",
      render: (_: unknown, device) => {
        const loss = resultByDevice.get(device.name)?.ping_loss_percent;
        return loss === null || loss === undefined ? "—" : `${loss.toFixed(0)}%`;
      },
    },
    {
      title: "TCP Port",
      key: "tcp",
      render: (_: unknown, device) => {
        const result = resultByDevice.get(device.name);
        return result ? (
          <div className="network-cell">
            <strong>{result.tcp_port ?? "—"} · {tcpLabels[result.tcp_state]}</strong>
            <span>{formatLatency(result.tcp_connect_ms)}</span>
          </div>
        ) : "—";
      },
    },
    {
      title: "失敗階段",
      dataIndex: "name",
      key: "failure",
      render: (_: string, device) => resultByDevice.get(device.name)?.failure_stage ?? "—",
    },
    {
      title: "Modbus",
      key: "modbus",
      render: (_: unknown, device) => {
        if (device.check_profile !== "full_stack") return "不適用";
        return resultByDevice.get(device.name)?.modbus_status ?? "—";
      },
    },
    {
      title: "總狀態",
      key: "status",
      render: (_: unknown, device) => {
        const result = resultByDevice.get(device.name);
        return result ? <Tag color={statusMeta[result.overall_status].color}>{statusMeta[result.overall_status].label}</Tag> : <Tag>未檢查</Tag>;
      },
    },
    {
      title: "診斷",
      key: "diagnosis",
      render: (_: unknown, device) => {
        const result = resultByDevice.get(device.name);
        if (!result) return "—";
        return (
          <Tooltip
            title={[
              result.error_message,
              ...(result.diagnosis_suggestions ?? []),
            ].filter(Boolean).join("；")}
          >
            <div className="network-cell network-diagnosis">
              <strong>{result.diagnosis_summary ?? result.error_message ?? "—"}</strong>
              {(result.threshold_violations ?? []).map((violation) => (
                <span key={violation}>{violation}</span>
              ))}
            </div>
          </Tooltip>
        );
      },
    },
    {
      title: "操作",
      key: "actions",
      align: "right",
      render: (_: unknown, device) => (
        <Space size={2}>
          <Tooltip title={device.check_profile === "full_stack" ? "測試（會建立 Modbus 連線，可能與樓控系統互相干擾）" : `測試 ${device.name}`}>
            <Button
              type="text"
              icon={<ReloadOutlined />}
              aria-label={`重測 ${device.name}`}
              loading={checkingDevice === device.name}
              disabled={checkingDevice !== null || checkingAll}
              onClick={() => void checkOne(device)}
            />
          </Tooltip>
          <Button type="text" icon={<EditOutlined />} aria-label={`編輯 ${device.name}`} onClick={() => onEdit(device)} />
          <Button type="text" danger icon={<DeleteOutlined />} aria-label={`刪除 ${device.name}`} onClick={() => onRemove(device)} />
        </Space>
      ),
    },
  ];

  return (
    <div className="network-panel">
      <section className="intro network-intro">
        <div>
          <span className="section-kicker">03 / DEVICE CHECKS</span>
          <Typography.Title>設備檢查</Typography.Title>
          <Typography.Paragraph>依每台設備的預設流程檢查 Ping、TCP 或 Modbus，不使用全域覆蓋模式。</Typography.Paragraph>
        </div>
      </section>

      <section className="network-controls" aria-label="網路健檢設定">
        {batchProgress && (
          <Alert
            type="info"
            showIcon
            title={`批次檢查進行中：${batchProgress.completed} / ${batchProgress.total} 台`}
            description="結果會逐步顯示於下方列表。"
            style={{ marginBottom: 12 }}
          />
        )}
        {autoCheck && (
          <Alert
            type="warning"
            showIcon
            title="自動檢查僅涵蓋 Ping / TCP 設備"
            description="完整檢查（Modbus）設備不會被自動檢查，以避免干擾現場樓控系統；如需 Modbus 檢查請手動執行。"
            style={{ marginBottom: 12 }}
          />
        )}
        <div className="network-control-field">
          <label htmlFor="network-concurrency">最大並行數</label>
          <InputNumber
            id="network-concurrency"
            min={1}
            max={50}
            value={maxConcurrency}
            onChange={(value) => setMaxConcurrency(value ?? 1)}
            addonAfter="台"
          />
        </div>
        <div className="network-control-field">
          <label htmlFor="network-auto-interval">自動檢查間隔</label>
          <Select
            id="network-auto-interval"
            value={autoIntervalMs}
            onChange={(value) => setAutoIntervalMs(value)}
            options={[
              { value: 60000, label: "60 秒" },
              { value: 300000, label: "5 分鐘" },
              { value: 600000, label: "10 分鐘" },
            ]}
            style={{ width: 120 }}
            disabled={autoCheck}
          />
        </div>
        <div className="network-control-field">
          <label htmlFor="network-auto">自動定時檢查</label>
          <Space>
            <Switch
              id="network-auto"
              checked={autoCheck}
              loading={autoChecking}
              onChange={setAutoCheck}
              checkedChildren="自動"
              unCheckedChildren="手動"
            />
            <span className="muted-label">{autoCheck ? "即時更新中" : "已停止"}</span>
          </Space>
        </div>
        <div className="network-control-actions">
          {batchProgress && (
            <Button danger icon={<ReloadOutlined />} onClick={() => void cancelBatch()}>
              取消檢查（{batchProgress.completed}/{batchProgress.total}）
            </Button>
          )}
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={checkingAll}
            disabled={!availableDevices.length || checkingAll}
            onClick={() => void checkAll()}
          >
            開始設備檢查
          </Button>
        </div>
      </section>

      <Collapse
        className="network-collapse"
        defaultActiveKey={["results"]}
        items={[
          {
            key: "editor",
            label: (
              <div className="network-collapse-label">
                <span className="section-kicker">DEVICE SETUP</span>
                <h2>{editing ? "編輯設備" : "新增設備"}</h2>
              </div>
            ),
            children: (
              <>
                <Segmented
                  block
                  value={addMode}
                  onChange={(value) => setAddMode(value as "single" | "batch")}
                  options={[
                    { value: "single", label: "單筆新增" },
                    { value: "batch", label: "批次新增" },
                  ]}
                  style={{ marginBottom: 16 }}
                />
                {addMode === "single" ? (
                  <DeviceEditor form={form} editing={editing} onSubmit={onSubmit} />
                ) : (
                  <BatchAddPanel existingDevices={devices} onBatchAdded={onBatchAdded} />
                )}
              </>
            ),
          },
          {
            key: "results",
            label: (
              <div className="network-collapse-label">
                <span className="section-kicker">DEVICE RESULTS</span>
                <h2>檢查結果列表</h2>
              </div>
            ),
            children: (
              <>
                <Row gutter={[12, 12]} className="network-metrics">
                  <Col xs={12} md={6}><Statistic title="納入設備" value={availableDevices.length} suffix="台" /></Col>
                  <Col xs={12} md={6}><Statistic title="正常" value={onlineCount} suffix="台" /></Col>
                  <Col xs={12} md={6}><Statistic title="異常 / 部分" value={attentionCount} suffix="台" /></Col>
                  <Col xs={12} md={6}><Statistic title="已取得結果" value={checkedResults.length} suffix="台" /></Col>
                </Row>

                <Alert
                  type="info"
                  showIcon
                  title="即時檢查不寫入歷史"
                  description="此處僅顯示最新一次檢查結果；需要保留紀錄與基準比較，請使用「回歸測試」。"
                  style={{ marginBottom: 16 }}
                />

                <div className="network-section-heading">
                  <Space wrap>
                    <Input.Search aria-label="搜尋設備" placeholder="搜尋名稱或 IP" allowClear value={search} onChange={(event) => setSearch(event.target.value)} />
                    <Select
                      aria-label="依狀態篩選"
                      value={statusFilter}
                      onChange={setStatusFilter}
                      options={[
                        { value: "ALL", label: "全部狀態" },
                        ...Object.entries(statusMeta).map(([value, meta]) => ({ value, label: meta.label })),
                      ]}
                      style={{ width: 140 }}
                    />
                  </Space>
                </div>
                <Table<Device>
                  rowKey="name"
                  columns={columns}
                  dataSource={resultRows.map(({ device }) => device)}
                  pagination={{ pageSize: 50, hideOnSinglePage: true, showSizeChanger: false }}
                  scroll={{ x: 980 }}
                  locale={{ emptyText: availableDevices.length ? "沒有符合條件的設備" : "目前沒有啟用的設備" }}
                />
              </>
            ),
          },
        ]}
      />
    </div>
  );
}
