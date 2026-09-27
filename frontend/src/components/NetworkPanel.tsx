import { useEffect, useMemo, useState } from "react";
import { App as AntApp, Button, Col, Input, InputNumber, Pagination, Progress, Row, Select, Space, Statistic, Table, Tag, Tooltip, Typography } from "antd";
import type { TableColumnsType } from "antd";
import { DownloadOutlined, EyeOutlined, PlayCircleOutlined, ReloadOutlined, StopOutlined } from "@ant-design/icons";
import {
  api,
  type NetworkBatch,
  type NetworkBatchDetail,
  type NetworkBatchStatus,
  type NetworkCheckResult,
  type NetworkCheckStatus,
  type NetworkMode,
} from "../api/client";
import type { Device } from "../api/mappers";

const pageSize = 10;
const statusMeta: Record<NetworkCheckStatus, { label: string; color: string; priority: number }> = {
  CONFIG_ERROR: { label: "設定錯誤", color: "error", priority: 0 },
  TIMEOUT: { label: "逾時", color: "warning", priority: 1 },
  FAIL: { label: "失敗", color: "error", priority: 2 },
  PARTIAL: { label: "部分正常", color: "processing", priority: 3 },
  PASS: { label: "正常", color: "success", priority: 4 },
  UNKNOWN: { label: "未知", color: "default", priority: 5 },
};
const batchStatusMeta: Record<NetworkBatchStatus, { label: string; color: string }> = {
  pending: { label: "排隊中", color: "default" },
  running: { label: "執行中", color: "processing" },
  completed: { label: "完成", color: "success" },
  failed: { label: "批次失敗", color: "error" },
  cancelled: { label: "已取消", color: "default" },
};
const modeLabels: Record<NetworkMode, string> = {
  network_only: "僅 Ping",
  network_and_port: "Ping + TCP Port",
  full_stack: "完整檢查（含 Modbus）",
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

function isActive(status: NetworkBatchStatus) {
  return status === "pending" || status === "running";
}

type NetworkPanelProps = {
  siteName: string;
  devices: Device[];
};

export function NetworkPanel({ siteName, devices }: NetworkPanelProps) {
  const { message } = AntApp.useApp();
  const [mode, setMode] = useState<NetworkMode>("network_and_port");
  const [maxConcurrency, setMaxConcurrency] = useState(20);
  const [batchStarting, setBatchStarting] = useState(false);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [batchDetail, setBatchDetail] = useState<NetworkBatchDetail | null>(null);
  const [batches, setBatches] = useState<NetworkBatch[]>([]);
  const [batchTotal, setBatchTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [checkingDevice, setCheckingDevice] = useState<string | null>(null);
  const [singleResults, setSingleResults] = useState<Record<string, NetworkCheckResult>>({});
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<NetworkCheckStatus | "ALL">("ALL");

  const availableDevices = devices.filter(
    (device) => device.enabled && device.network_check_enabled !== false,
  );

  useEffect(() => {
    let cancelled = false;
    api
      .listNetworkBatches(siteName, (historyPage - 1) * pageSize, pageSize)
      .then((response) => {
        if (cancelled) return;
        setBatches(response.items);
        setBatchTotal(response.total);
        const activeBatch = response.items.find((batch) => isActive(batch.status));
        if (activeBatch) {
          setActiveBatchId((current) => current ?? activeBatch.id);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          message.error(error instanceof Error ? error.message : "網路批次歷史讀取失敗");
        }
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [historyPage, message, siteName]);

  useEffect(() => {
    if (!activeBatchId) return;
    let cancelled = false;
    let timer: number | undefined;
    const refresh = async () => {
      try {
        const detail = await api.getNetworkBatch(activeBatchId);
        if (cancelled) return;
        setBatchDetail(detail);
        if (!isActive(detail.batch.status)) {
          setActiveBatchId(null);
          const history = await api.listNetworkBatches(
            siteName,
            (historyPage - 1) * pageSize,
            pageSize,
          );
          if (cancelled) return;
          setBatches(history.items);
          setBatchTotal(history.total);
          return;
        }
      } catch (error) {
        if (!cancelled) {
          setActiveBatchId(null);
          message.error(error instanceof Error ? error.message : "網路批次狀態讀取失敗");
        }
        return;
      }
      timer = window.setTimeout(() => void refresh(), 1000);
    };
    void refresh();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeBatchId, historyPage, message, siteName]);

  const resultByDevice = useMemo(() => {
    const results = new Map<string, NetworkCheckResult>();
    for (const record of batchDetail?.results ?? []) {
      results.set(record.result.device_name, record.result);
    }
    for (const [deviceName, result] of Object.entries(singleResults)) {
      results.set(deviceName, result);
    }
    return results;
  }, [batchDetail, singleResults]);

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

  const startBatch = async () => {
    setBatchStarting(true);
    try {
      const batch = await api.createNetworkBatch(siteName, mode, maxConcurrency);
      setSingleResults({});
      setBatchDetail({ batch, results: [], completed_device_count: 0 });
      setActiveBatchId(batch.id);
      setHistoryPage(1);
      setBatches((current) => [batch, ...current.filter((item) => item.id !== batch.id)]);
      setBatchTotal((total) => total + 1);
      message.success("網路健檢批次已啟動");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "網路健檢啟動失敗");
    } finally {
      setBatchStarting(false);
    }
  };

  const checkOne = async (device: Device) => {
    setCheckingDevice(device.name);
    try {
      const result = await api.checkNetworkDevice(device.name, mode);
      setSingleResults((current) => ({ ...current, [device.name]: result }));
      message.success(`${device.name} 網路測試完成`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "單台網路測試失敗");
    } finally {
      setCheckingDevice(null);
    }
  };

  const cancelBatch = async (batch: NetworkBatch) => {
    setCancelling(true);
    try {
      const updated = await api.cancelNetworkBatch(batch.id);
      setBatches((current) => current.map((item) => item.id === updated.id ? updated : item));
      message.info("已送出取消要求");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "取消網路批次失敗");
    } finally {
      setCancelling(false);
    }
  };

  const openBatch = async (batch: NetworkBatch) => {
    try {
      const detail = await api.getNetworkBatch(batch.id);
      setBatchDetail(detail);
      setSingleResults({});
      setActiveBatchId(isActive(detail.batch.status) ? detail.batch.id : null);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "網路批次結果讀取失敗");
    }
  };

  const downloadCsv = async (batch: NetworkBatch) => {
    try {
      const detail = batchDetail?.batch.id === batch.id
        ? batchDetail
        : await api.getNetworkBatch(batch.id);
      const headers = [
        "設備", "IP", "測試時間", "模式", "Ping 狀態", "Ping 次數", "成功次數",
        "封包遺失率(%)", "Ping 平均延遲(ms)", "TCP Port", "TCP 狀態",
        "TCP 連線時間(ms)", "失敗階段", "總狀態", "錯誤類型", "診斷",
      ];
      const rows = detail.results.map(({ result }) => [
        result.device_name,
        result.target_ip,
        result.timestamp,
        modeLabels[result.mode],
        pingLabels[result.ping_state],
        result.ping_attempts,
        result.ping_success_count,
        result.ping_loss_percent,
        result.ping_avg_ms,
        result.tcp_port,
        tcpLabels[result.tcp_state],
        result.tcp_connect_ms,
        result.failure_stage,
        statusMeta[result.overall_status].label,
        result.error_type,
        result.error_message,
      ]);
      const csvCell = (value: string | number | null) => {
        const text = String(value ?? "");
        const safeText = /^[\s]*[=+\-@]/.test(text) ? `'${text}` : text;
        return `"${safeText.replaceAll('"', '""')}"`;
      };
      const csv = [headers, ...rows]
        .map((row) => row.map(csvCell).join(","))
        .join("\r\n");
      const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${batch.id}.csv`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "網路報告下載失敗");
    }
  };

  const columns: TableColumnsType<Device> = [
    {
      title: "設備",
      key: "device",
      render: (_: unknown, device) => (
        <div className="device-name">
          <strong>{device.name}</strong>
          <span>{device.ip}</span>
        </div>
      ),
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
      render: (_: unknown, device) => resultByDevice.get(device.name)?.error_message ?? "—",
    },
    {
      title: "操作",
      key: "actions",
      align: "right",
      render: (_: unknown, device) => (
        <Tooltip title={`測試 ${device.name}`}>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            aria-label={`重測 ${device.name}`}
            loading={checkingDevice === device.name}
            disabled={checkingDevice !== null || activeBatchId !== null}
            onClick={() => void checkOne(device)}
          />
        </Tooltip>
      ),
    },
  ];

  const historyColumns: TableColumnsType<NetworkBatch> = [
    {
      title: "開始時間",
      dataIndex: "started_at",
      key: "started_at",
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: "模式",
      dataIndex: "mode",
      key: "mode",
      render: (value: NetworkMode) => modeLabels[value],
    },
    {
      title: "進度",
      key: "progress",
      render: (_: unknown, batch) => `${batch.completed_device_count} / ${batch.device_names.length}`,
    },
    {
      title: "結果",
      key: "summary",
      render: (_: unknown, batch) => `${batch.pass_count} 通過 · ${batch.fail_count + batch.timeout_count + batch.config_error_count + batch.partial_count} 異常`,
    },
    {
      title: "狀態",
      dataIndex: "status",
      key: "status",
      render: (status: NetworkBatchStatus) => <Tag color={batchStatusMeta[status].color}>{batchStatusMeta[status].label}</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      align: "right",
      render: (_: unknown, batch) => (
        <Space size={4}>
          <Tooltip title="查看批次結果">
            <Button type="text" icon={<EyeOutlined />} aria-label={`查看批次 ${batch.id}`} onClick={() => void openBatch(batch)} />
          </Tooltip>
          {isActive(batch.status) && (
            <Tooltip title="取消批次">
              <Button type="text" danger icon={<StopOutlined />} aria-label={`取消批次 ${batch.id}`} loading={cancelling && activeBatchId === batch.id} onClick={() => void cancelBatch(batch)} />
            </Tooltip>
          )}
          <Tooltip title="下載 CSV 報告">
            <Button type="text" icon={<DownloadOutlined />} aria-label={`下載批次報告 ${batch.id}`} disabled={batch.completed_device_count === 0} onClick={() => void downloadCsv(batch)} />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const currentProgress = batchDetail
    ? Math.round(batchDetail.completed_device_count / Math.max(1, batchDetail.batch.device_names.length) * 100)
    : 0;

  return (
    <div className="network-panel">
      <section className="intro network-intro">
        <div>
          <span className="section-kicker">03 / SITE CONNECTIVITY</span>
          <Typography.Title>網路健檢</Typography.Title>
          <Typography.Paragraph>先確認 IP 可達性，再檢查服務 Port；需要時接續 Modbus 驗證。</Typography.Paragraph>
        </div>
      </section>

      <section className="network-controls" aria-label="網路健檢設定">
        <div className="network-control-field">
          <label htmlFor="network-mode">測試模式</label>
          <Select
            id="network-mode"
            value={mode}
            onChange={setMode}
            options={Object.entries(modeLabels).map(([value, label]) => ({ value, label }))}
            style={{ minWidth: 190 }}
          />
        </div>
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
        <div className="network-control-actions">
          {batchDetail && isActive(batchDetail.batch.status) ? (
            <Button danger icon={<StopOutlined />} loading={cancelling} onClick={() => void cancelBatch(batchDetail.batch)}>
              取消批次
            </Button>
          ) : null}
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={batchStarting}
            disabled={!availableDevices.length || activeBatchId !== null}
            onClick={() => void startBatch()}
          >
            開始網路健檢
          </Button>
        </div>
      </section>

      <Row gutter={[12, 12]} className="network-metrics">
        <Col xs={12} md={6}><Statistic title="納入設備" value={availableDevices.length} suffix="台" /></Col>
        <Col xs={12} md={6}><Statistic title="正常" value={onlineCount} suffix="台" /></Col>
        <Col xs={12} md={6}><Statistic title="異常 / 部分" value={attentionCount} suffix="台" /></Col>
        <Col xs={12} md={6}><Statistic title="已取得結果" value={checkedResults.length} suffix="台" /></Col>
      </Row>

      {batchDetail && (
        <section className="network-progress" aria-live="polite">
          <div className="regression-progress-heading">
            <strong>
              {isActive(batchDetail.batch.status)
                ? `批次執行中 · ${batchDetail.batch.id}`
                : `批次${batchStatusMeta[batchDetail.batch.status].label} · ${batchDetail.batch.id}`}
            </strong>
            <span>{batchDetail.completed_device_count} / {batchDetail.batch.device_names.length} 台</span>
          </div>
          <Progress percent={currentProgress} status={batchDetail.batch.status === "failed" ? "exception" : "normal"} />
        </section>
      )}

      <section className="network-results">
        <div className="network-section-heading">
          <div>
            <span className="section-kicker">DEVICE RESULTS</span>
            <h2>設備結果</h2>
          </div>
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
          locale={{ emptyText: availableDevices.length ? "沒有符合條件的設備" : "目前沒有啟用網路健檢的設備" }}
        />
      </section>

      <section className="network-history">
        <div className="network-section-heading">
          <div>
            <span className="section-kicker">BATCH HISTORY</span>
            <h2>批次歷史</h2>
          </div>
          <Button icon={<ReloadOutlined />} aria-label="重新整理網路批次歷史" loading={historyLoading} onClick={() => {
            setHistoryLoading(true);
            void api.listNetworkBatches(siteName, (historyPage - 1) * pageSize, pageSize)
              .then((response) => {
                setBatches(response.items);
                setBatchTotal(response.total);
              })
              .catch((error: unknown) => message.error(error instanceof Error ? error.message : "網路批次歷史讀取失敗"))
              .finally(() => setHistoryLoading(false));
          }} />
        </div>
        <Table<NetworkBatch>
          rowKey="id"
          columns={historyColumns}
          dataSource={batches}
          loading={historyLoading}
          pagination={false}
          scroll={{ x: 760 }}
          locale={{ emptyText: "尚無網路健檢批次" }}
        />
        {batchTotal > pageSize && (
          <div className="network-pagination">
            <Pagination
              current={historyPage}
              pageSize={pageSize}
              total={batchTotal}
              showSizeChanger={false}
              onChange={(page) => {
                setHistoryLoading(true);
                setHistoryPage(page);
              }}
            />
          </div>
        )}
      </section>
    </div>
  );
}
