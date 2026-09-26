import { DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Input,
  Progress,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
} from "antd";
import { api, type BatchDetail, type CheckBatch, type ComparisonStatus } from "../api/client";
import type { DeviceStatus } from "../api/mappers";
import { statusMeta } from "./deviceMeta";

const comparisonMeta: Record<ComparisonStatus, { label: string; color: string }> = {
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
const regressionPriority: Partial<Record<ComparisonStatus, number>> = {
  NEW_FAILURE: 0,
  LATENCY_DEGRADED: 1,
  VALUE_CHANGED: 2,
  CONFIG_CHANGED: 3,
};

type RegressionPanelProps = {
  batches: CheckBatch[];
  batchTotal: number;
  batchPage: number;
  batchPageSize: number;
  baseline: { baseline_batch_id: string; updated_at: string } | null;
  batchDetail: BatchDetail | null;
  activeBatchId: string | null;
  batchStarting: boolean;
  batchNote: string;
  selectedBatchIds: string[];
  cancellingBatchId: string | null;
  comparisonLoadingId: string | null;
  enabledDeviceCount: number;
  onBatchNoteChange: (note: string) => void;
  onStartBatch: () => void;
  onClearBaseline: () => void;
  onCancelBatch: (batch: CheckBatch) => void;
  onCompareBatch: (batch: CheckBatch) => void;
  onSetBaseline: (batch: CheckBatch) => void;
  onDeleteBatches: (batchIds: string[]) => void;
  onSelectionChange: (ids: string[]) => void;
  onPageChange: (page: number) => void;
};

export function RegressionPanel({
  batches,
  batchTotal,
  batchPage,
  batchPageSize,
  baseline,
  batchDetail,
  activeBatchId,
  batchStarting,
  batchNote,
  selectedBatchIds,
  cancellingBatchId,
  comparisonLoadingId,
  enabledDeviceCount,
  onBatchNoteChange,
  onStartBatch,
  onClearBaseline,
  onCancelBatch,
  onCompareBatch,
  onSetBaseline,
  onDeleteBatches,
  onSelectionChange,
  onPageChange,
}: RegressionPanelProps) {
  const batchColumns = [
    {
      title: "檢查時間",
      dataIndex: "started_at",
      key: "started_at",
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: "結果",
      key: "summary",
      render: (_: unknown, batch: CheckBatch) =>
        `${batch.pass_count}/${batch.device_names.length} 通過 · ${batch.fail_count + batch.timeout_count + batch.config_error_count} 異常`,
    },
    {
      title: "狀態",
      dataIndex: "status",
      key: "status",
      render: (status: CheckBatch["status"]) => {
        const labels: Record<CheckBatch["status"], string> = {
          pending: "排隊中",
          running: "執行中",
          completed: "完成",
          failed: "失敗",
          cancelled: "已取消",
        };
        const color = status === "completed" ? "success" : status === "failed" ? "error" : status === "cancelled" ? "default" : "processing";
        return <Tag color={color}>{labels[status]}</Tag>;
      },
    },
    {
      title: "備註",
      dataIndex: "note",
      key: "note",
      render: (note: string | null) => note || "—",
    },
    {
      title: "基準",
      key: "baseline",
      render: (_: unknown, batch: CheckBatch) =>
        baseline?.baseline_batch_id === batch.id ? <Tag color="processing">目前基準</Tag> : null,
    },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, batch: CheckBatch) => (
        <Space size={4}>
          {(batch.status === "pending" || batch.status === "running") && (
            <Button
              type="link"
              danger
              loading={cancellingBatchId === batch.id}
              onClick={() => onCancelBatch(batch)}
            >
              取消
            </Button>
          )}
          <Button
            type="link"
            disabled={batch.status !== "completed"}
            loading={comparisonLoadingId === batch.id}
            onClick={() => onCompareBatch(batch)}
          >
            比較基準
          </Button>
          <Button
            type="link"
            disabled={batch.status !== "completed" || batch.mode !== "full"}
            onClick={() => onSetBaseline(batch)}
          >
            設為基準
          </Button>
          <Button type="link" disabled={batch.status !== "completed"} href={api.getReportUrl(batch.id, "csv")}>
            CSV
          </Button>
          <Button type="link" disabled={batch.status !== "completed"} href={api.getReportUrl(batch.id, "html")}>
            HTML
          </Button>
          <Tooltip
            title={
              baseline?.baseline_batch_id === batch.id
                ? "請先清除案場基準"
                : batch.status === "pending" || batch.status === "running"
                  ? "執行中的批次不可刪除"
                  : "刪除批次及檢查結果"
            }
          >
            <Button
              type="text"
              danger
              aria-label={`刪除批次 ${batch.id}`}
              icon={<DeleteOutlined />}
              disabled={
                batch.status === "pending" ||
                batch.status === "running" ||
                baseline?.baseline_batch_id === batch.id
              }
              onClick={() => onDeleteBatches([batch.id])}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const anomalyRecords = (batchDetail?.records ?? [])
    .filter((record) =>
      record.result.status !== "PASS" ||
      (record.comparison_status !== null && record.comparison_status in regressionPriority)
    )
    .sort((left, right) => {
      const leftRank = left.comparison_status ? regressionPriority[left.comparison_status] ?? 4 : 0;
      const rightRank = right.comparison_status ? regressionPriority[right.comparison_status] ?? 4 : 0;
      return leftRank - rightRank;
    });
  const anomalyColumns = [
    {
      title: "設備",
      dataIndex: "result",
      key: "device",
      render: (result: BatchDetail["records"][number]["result"]) => result.device_name,
    },
    {
      title: "本次狀態",
      dataIndex: "result",
      key: "result_status",
      render: (result: BatchDetail["records"][number]["result"]) => {
        const status = result.status as DeviceStatus;
        return <Tag color={statusMeta[status].color}>{statusMeta[status].label}</Tag>;
      },
    },
    {
      title: "回歸差異",
      dataIndex: "comparison_status",
      key: "comparison_status",
      render: (status: ComparisonStatus | null) =>
        status ? <Tag color={comparisonMeta[status].color}>{comparisonMeta[status].label}</Tag> : "—",
    },
    {
      title: "診斷摘要",
      dataIndex: "diagnosis",
      key: "diagnosis",
      render: (diagnosis: NonNullable<BatchDetail["records"][number]["diagnosis"]> | null) =>
        diagnosis?.summary ?? "尚無診斷資料",
    },
  ];

  return (
    <section className="batch-history">
      <Card
        variant="borderless"
        title={
          <div>
            <span className="section-kicker">FIELD REGRESSION</span>
            <h2>回歸檢查批次</h2>
          </div>
        }
        extra={
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={batchStarting || activeBatchId !== null}
            disabled={enabledDeviceCount === 0}
            onClick={onStartBatch}
          >
            開始回歸檢查
          </Button>
        }
      >
        <Input.TextArea
          aria-label="本次檢查備註"
          value={batchNote}
          onChange={(event) => onBatchNoteChange(event.target.value)}
          maxLength={500}
          showCount
          placeholder="本次變更或檢查備註（選填）"
          autoSize={{ minRows: 2, maxRows: 4 }}
          style={{ marginBottom: 16 }}
        />
        <Alert
          type={baseline ? "success" : "warning"}
          showIcon
          title={baseline ? `目前基準：${new Date(baseline.updated_at).toLocaleString()}` : "尚未設定案場基準"}
          description={baseline ? `基準批次 ${baseline.baseline_batch_id}；檢查完成後可比較本次結果。` : "先完成一次全案場檢查，再從批次歷史將合格批次設為基準。"}
          action={baseline ? <Button size="small" onClick={onClearBaseline}>清除基準</Button> : null}
          style={{ marginBottom: 16 }}
        />
        {batchDetail && (
          <div className="regression-progress">
            <div className="regression-progress-heading">
              <strong>
                {batchDetail.batch.status === "completed" ? "最近批次已完成" : batchDetail.batch.status === "failed" ? "最近批次失敗" : batchDetail.batch.status === "cancelled" ? "最近批次已取消" : "回歸檢查執行中"}
              </strong>
              <span>{batchDetail.completed_device_count} / {batchDetail.batch.device_names.length} 台設備</span>
            </div>
            <Progress
              percent={batchDetail.batch.device_names.length ? Math.round(batchDetail.completed_device_count / batchDetail.batch.device_names.length * 100) : 0}
              status={batchDetail.batch.status === "failed" ? "exception" : "normal"}
            />
          </div>
        )}
        {batchDetail && (
          <Row gutter={[12, 12]} className="health-summary">
            <Col xs={12} md={6}><Statistic title="檢查設備" value={batchDetail.health_summary.device_count} suffix="台" /></Col>
            <Col xs={12} md={6}><Statistic title="通過率" value={Math.round(batchDetail.health_summary.pass_rate * 100)} suffix="%" /></Col>
            <Col xs={12} md={6}><Statistic title="通過" value={batchDetail.health_summary.pass_count} /></Col>
            <Col xs={12} md={6}><Statistic title="新增異常" value={batchDetail.health_summary.new_failure_count} /></Col>
            <Col xs={12} md={6}><Statistic title="平均回應" value={batchDetail.health_summary.avg_elapsed_ms === null ? "—" : Math.round(batchDetail.health_summary.avg_elapsed_ms)} suffix={batchDetail.health_summary.avg_elapsed_ms === null ? "" : "ms"} /></Col>
            <Col xs={12} md={6}><Statistic title="失敗" value={batchDetail.health_summary.fail_count} /></Col>
            <Col xs={12} md={6}><Statistic title="逾時" value={batchDetail.health_summary.timeout_count} /></Col>
            <Col xs={12} md={6}><Statistic title="設定錯誤" value={batchDetail.health_summary.config_error_count} /></Col>
            <Col xs={12} md={6}><Statistic title="最慢設備" value={batchDetail.health_summary.slowest_device ?? "—"} suffix={batchDetail.health_summary.slowest_elapsed_ms === null ? "" : `${batchDetail.health_summary.slowest_elapsed_ms} ms`} /></Col>
          </Row>
        )}
        {batchDetail?.batch.status === "failed" && <Alert type="error" showIcon title="回歸檢查批次失敗" description={batchDetail.batch.error_message || "批次執行失敗，請稍後重試。"} style={{ marginBottom: 16 }} />}
        {batchDetail?.batch.status === "cancelled" && <Alert type="warning" showIcon title="回歸檢查已取消" description="已停止尚未開始的設備檢查；取消前已完成或正在執行的結果仍會保留在批次中。" style={{ marginBottom: 16 }} />}
        {anomalyRecords.length > 0 && (
          <div className="priority-anomalies">
            <Divider>優先處理設備</Divider>
            <Table
              rowKey={(record) => record.result.device_name}
              columns={anomalyColumns}
              dataSource={anomalyRecords}
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              expandable={{
                expandedRowRender: (record) => (
                  <ul className="diagnosis-suggestions">
                    {(record.diagnosis?.suggestions ?? []).map((suggestion) => <li key={suggestion}>{suggestion}</li>)}
                  </ul>
                ),
                rowExpandable: (record) => Boolean(record.diagnosis?.suggestions.length),
              }}
              size="small"
              scroll={{ x: 700 }}
            />
          </div>
        )}
        <Space style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
          <Button danger icon={<DeleteOutlined />} disabled={!selectedBatchIds.length} onClick={() => onDeleteBatches(selectedBatchIds)}>
            刪除所選 ({selectedBatchIds.length})
          </Button>
        </Space>
        <Table
          rowKey="id"
          columns={batchColumns}
          dataSource={batches}
          rowSelection={{
            selectedRowKeys: selectedBatchIds,
            onChange: (keys) => onSelectionChange(keys.map(String)),
            getCheckboxProps: (batch) => ({
              disabled: batch.status === "pending" || batch.status === "running" || baseline?.baseline_batch_id === batch.id,
            }),
          }}
          pagination={{
            current: batchPage,
            pageSize: batchPageSize,
            total: batchTotal,
            hideOnSinglePage: true,
            onChange: onPageChange,
          }}
          size="small"
          scroll={{ x: 720 }}
          locale={{ emptyText: "尚無檢查批次" }}
        />
      </Card>
    </section>
  );
}
