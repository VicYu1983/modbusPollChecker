import { useEffect, useMemo, useState } from "react";
import { Alert, App as AntApp, Button, Card, Col, Input, Progress, Row, Space, Statistic, Table, Tag, Tooltip } from "antd";
import type { TableColumnsType } from "antd";
import { DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  api,
  type DeviceCheckBaseline,
  type DeviceCheckBatchComparison,
  type DeviceComparisonStatus,
  type NetworkBatch,
  type NetworkBatchDetail,
  type NetworkBatchStatus,
} from "../api/client";
import type { Device } from "../api/mappers";

const pageSize = 25;

const comparisonMeta: Record<DeviceComparisonStatus, { label: string; color: string }> = {
  UNCHANGED_PASS: { label: "維持正常", color: "success" },
  UNCHANGED_FAILURE: { label: "異常仍存在", color: "error" },
  NEW_FAILURE: { label: "新增異常", color: "error" },
  RECOVERED: { label: "已恢復", color: "success" },
  VALUE_CHANGED: { label: "回傳值變更", color: "warning" },
  LATENCY_DEGRADED: { label: "回應變慢", color: "warning" },
  CONFIG_CHANGED: { label: "通訊設定變更", color: "processing" },
  BASELINE_ONLY: { label: "本次未檢查", color: "default" },
  NEW_DEVICE: { label: "新增設備", color: "processing" },
  NO_BASELINE: { label: "尚無基準", color: "default" },
};

const batchStatusMeta: Record<NetworkBatchStatus, { label: string; color: string }> = {
  pending: { label: "排隊中", color: "default" },
  running: { label: "執行中", color: "processing" },
  completed: { label: "完成", color: "success" },
  failed: { label: "失敗", color: "error" },
  cancelled: { label: "已取消", color: "default" },
};

const priority: Partial<Record<DeviceComparisonStatus, number>> = {
  NEW_FAILURE: 0,
  LATENCY_DEGRADED: 1,
  VALUE_CHANGED: 2,
  CONFIG_CHANGED: 3,
};

function isActive(status: NetworkBatchStatus) {
  return status === "pending" || status === "running";
}

type DeviceRegressionPanelProps = {
  siteName: string;
  devices: Device[];
};

export function DeviceRegressionPanel({ siteName, devices }: DeviceRegressionPanelProps) {
  const { message } = AntApp.useApp();
  const [batches, setBatches] = useState<NetworkBatch[]>([]);
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchPage, setBatchPage] = useState(1);
  const [baseline, setBaseline] = useState<DeviceCheckBaseline | null>(null);
  const [detail, setDetail] = useState<NetworkBatchDetail | null>(null);
  const [comparison, setComparison] = useState<DeviceCheckBatchComparison | null>(null);
  const [starting, setStarting] = useState(false);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const eligibleDevices = devices.filter((device) => device.enabled);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.listDeviceCheckBatches(siteName, (batchPage - 1) * pageSize, pageSize).catch(() => null),
      api.getDeviceCheckBaseline(siteName).catch(() => null),
    ]).then(([history, currentBaseline]) => {
      if (cancelled) return;
      setBatches(history?.items ?? []);
      setBatchTotal(history?.total ?? 0);
      setBaseline(currentBaseline);
    });
    return () => {
      cancelled = true;
    };
  }, [batchPage, siteName]);

  useEffect(() => {
    if (!activeBatchId) return;
    let cancelled = false;
    let timer: number | undefined;
    const refresh = async () => {
      try {
        const current = await api.getDeviceCheckBatch(activeBatchId);
        if (cancelled) return;
        setDetail(current);
        if (!isActive(current.batch.status)) {
          const history = await api.listDeviceCheckBatches(
            siteName,
            (batchPage - 1) * pageSize,
            pageSize,
          );
          if (cancelled) return;
          setBatches(history.items);
          setBatchTotal(history.total);
          setActiveBatchId(null);
          return;
        }
      } catch {
        if (!cancelled) setActiveBatchId(null);
        return;
      }
      timer = window.setTimeout(() => void refresh(), 1000);
    };
    void refresh();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeBatchId, batchPage, siteName]);

  const startBatch = async () => {
    setStarting(true);
    try {
      const batch = await api.createDeviceCheckBatch(siteName, 20);
      setDetail({ batch, results: [], completed_device_count: 0, comparison: null });
      setComparison(null);
      setNote("");
      setBatchPage(1);
      setBatches((current) => [batch, ...current.filter((item) => item.id !== batch.id)]);
      setBatchTotal((total) => total + 1);
      setActiveBatchId(batch.id);
      message.info("設備回歸檢查已開始");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "設備回歸檢查啟動失敗");
    } finally {
      setStarting(false);
    }
  };

  const openBatch = async (batch: NetworkBatch) => {
    try {
      const current = await api.getDeviceCheckBatch(batch.id);
      setDetail(current);
      setComparison(current.comparison);
      setActiveBatchId(isActive(current.batch.status) ? current.batch.id : null);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "批次結果讀取失敗");
    }
  };

  const setAsBaseline = async (batch: NetworkBatch) => {
    try {
      const saved = await api.setDeviceCheckBaseline(siteName, batch.id);
      setBaseline(saved);
      message.success("設備回歸基準已更新");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "基準設定失敗");
    }
  };

  const clearBaseline = async () => {
    try {
      await api.clearDeviceCheckBaseline(siteName);
      setBaseline(null);
      message.success("設備回歸基準已清除");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "基準清除失敗");
    }
  };

  const compareBatch = async (batch: NetworkBatch) => {
    try {
      setComparison(await api.compareDeviceCheckBatch(batch.id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "批次比較失敗");
    }
  };

  const cancelBatch = async (batch: NetworkBatch) => {
    try {
      const updated = await api.cancelDeviceCheckBatch(batch.id);
      setBatches((current) => current.map((item) => item.id === updated.id ? updated : item));
      message.info("已送出取消要求");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "取消批次失敗");
    }
  };

  const deleteBatches = async (ids: string[]) => {
    if (!ids.length) return;
    const results = await Promise.allSettled(ids.map((id) => api.deleteDeviceCheckBatch(id)));
    const deleted = ids.filter((_, index) => results[index].status === "fulfilled");
    setSelectedIds([]);
    setBatches((current) => current.filter((batch) => !deleted.includes(batch.id)));
    setBatchTotal((total) => Math.max(0, total - deleted.length));
    if (deleted.length) message.success(`已刪除 ${deleted.length} 個批次`);
    if (deleted.length < ids.length) message.error("部分批次刪除失敗");
  };

  const anomalyRows = useMemo(
    () =>
      (comparison?.comparisons ?? [])
        .filter((item) => item.status !== "UNCHANGED_PASS")
        .sort((left, right) => (priority[left.status] ?? 4) - (priority[right.status] ?? 4)),
    [comparison],
  );

  const batchColumns: TableColumnsType<NetworkBatch> = [
    {
      title: "檢查時間",
      dataIndex: "started_at",
      key: "started_at",
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: "結果",
      key: "summary",
      render: (_: unknown, batch) =>
        `${batch.pass_count}/${batch.device_names.length} 通過 · ${batch.fail_count + batch.timeout_count + batch.config_error_count + batch.partial_count} 異常`,
    },
    {
      title: "狀態",
      dataIndex: "status",
      key: "status",
      render: (status: NetworkBatchStatus) => (
        <Tag color={batchStatusMeta[status].color}>{batchStatusMeta[status].label}</Tag>
      ),
    },
    {
      title: "基準",
      key: "baseline",
      render: (_: unknown, batch) =>
        baseline?.baseline_batch_id === batch.id ? <Tag color="processing">目前基準</Tag> : null,
    },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, batch) => (
        <Space size={4}>
          {isActive(batch.status) && (
            <Button type="link" danger onClick={() => void cancelBatch(batch)}>取消</Button>
          )}
          <Button type="link" disabled={batch.status !== "completed"} onClick={() => void openBatch(batch)}>查看</Button>
          <Button type="link" disabled={batch.status !== "completed"} onClick={() => void compareBatch(batch)}>比較基準</Button>
          <Button type="link" disabled={batch.status !== "completed"} onClick={() => void setAsBaseline(batch)}>設為基準</Button>
          <Tooltip title={baseline?.baseline_batch_id === batch.id ? "請先清除基準" : "刪除批次"}>
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              disabled={isActive(batch.status) || baseline?.baseline_batch_id === batch.id}
              onClick={() => void deleteBatches([batch.id])}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const anomalyColumns: TableColumnsType<DeviceCheckBatchComparison["comparisons"][number]> = [
    { title: "設備", dataIndex: "device_name", key: "device_name" },
    {
      title: "本次狀態",
      dataIndex: "current_status",
      key: "current_status",
      render: (value: string | null) => value ?? "—",
    },
    {
      title: "回歸差異",
      dataIndex: "status",
      key: "status",
      render: (status: DeviceComparisonStatus) => (
        <Tag color={comparisonMeta[status].color}>{comparisonMeta[status].label}</Tag>
      ),
    },
    {
      title: "延遲差",
      dataIndex: "latency_delta_ms",
      key: "latency_delta_ms",
      render: (value: number | null) => value === null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)} ms`,
    },
    {
      title: "封包遺失差",
      dataIndex: "loss_delta_percent",
      key: "loss_delta_percent",
      render: (value: number | null) => value === null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)} 個百分點`,
    },
  ];

  const progress = detail
    ? Math.round(detail.completed_device_count / Math.max(1, detail.batch.device_names.length) * 100)
    : 0;

  return (
    <section className="batch-history">
      <Card
        variant="borderless"
        title={
          <div>
            <span className="section-kicker">FIELD REGRESSION</span>
            <h2>設備回歸檢查</h2>
          </div>
        }
        extra={
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={starting || activeBatchId !== null}
            disabled={eligibleDevices.length === 0}
            onClick={() => void startBatch()}
          >
            開始回歸檢查
          </Button>
        }
      >
        <Alert
          type="info"
          showIcon
          title="回歸檢查涵蓋所有啟用設備"
          description="依每台設備的預設檢查流程執行；完整檢查設備會同時比較 Modbus 狀態與暫存器數值。"
          style={{ marginBottom: 16 }}
        />
        <Input.TextArea
          aria-label="本次檢查備註"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={500}
          showCount
          placeholder="本次變更或檢查備註（選填）"
          autoSize={{ minRows: 2, maxRows: 4 }}
          style={{ marginBottom: 16 }}
        />
        <Alert
          type={baseline ? "success" : "warning"}
          showIcon
          title={baseline ? `目前基準批次：${baseline.baseline_batch_id}` : "尚未設定設備回歸基準"}
          description={baseline ? "檢查完成後可比較本次結果與基準差異。" : "先完成一次設備檢查，再從批次歷史將合格批次設為基準。"}
          action={baseline ? <Button size="small" onClick={() => void clearBaseline()}>清除基準</Button> : null}
          style={{ marginBottom: 16 }}
        />
        {detail && (
          <div className="regression-progress">
            <div className="regression-progress-heading">
              <strong>
                {isActive(detail.batch.status)
                  ? "回歸檢查執行中"
                  : `最近批次${batchStatusMeta[detail.batch.status].label}`}
              </strong>
              <span>{detail.completed_device_count} / {detail.batch.device_names.length} 台設備</span>
            </div>
            <Progress percent={progress} status={detail.batch.status === "failed" ? "exception" : "normal"} />
          </div>
        )}
        {detail && (
          <Row gutter={[12, 12]} className="health-summary">
            <Col xs={12} md={6}><Statistic title="檢查設備" value={detail.batch.device_names.length} suffix="台" /></Col>
            <Col xs={12} md={6}><Statistic title="通過" value={detail.batch.pass_count} /></Col>
            <Col xs={12} md={6}><Statistic title="部分正常" value={detail.batch.partial_count} /></Col>
            <Col xs={12} md={6}><Statistic title="失敗" value={detail.batch.fail_count} /></Col>
            <Col xs={12} md={6}><Statistic title="逾時" value={detail.batch.timeout_count} /></Col>
            <Col xs={12} md={6}><Statistic title="設定錯誤" value={detail.batch.config_error_count} /></Col>
            <Col xs={12} md={6}><Statistic title="新增異常" value={anomalyRows.filter((item) => item.status === "NEW_FAILURE").length} /></Col>
          </Row>
        )}
        {anomalyRows.length > 0 && (
          <div className="priority-anomalies">
            <Table
              rowKey="device_name"
              columns={anomalyColumns}
              dataSource={anomalyRows}
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              size="small"
              scroll={{ x: 700 }}
            />
          </div>
        )}
        <Space style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
          <Button danger icon={<DeleteOutlined />} disabled={!selectedIds.length} onClick={() => void deleteBatches(selectedIds)}>
            刪除所選 ({selectedIds.length})
          </Button>
        </Space>
        <Table<NetworkBatch>
          rowKey="id"
          columns={batchColumns}
          dataSource={batches}
          rowSelection={{
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys.map(String)),
            getCheckboxProps: (batch) => ({
              disabled: isActive(batch.status) || baseline?.baseline_batch_id === batch.id,
            }),
          }}
          pagination={{
            current: batchPage,
            pageSize,
            total: batchTotal,
            hideOnSinglePage: true,
            onChange: setBatchPage,
          }}
          size="small"
          scroll={{ x: 760 }}
          locale={{ emptyText: "尚無設備回歸批次" }}
        />
      </Card>
    </section>
  );
}
