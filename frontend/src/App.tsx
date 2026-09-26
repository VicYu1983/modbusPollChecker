import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import {
  App as AntApp,
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Layout,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Tabs,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  api,
  type BatchDetail,
  type CheckBatch,
  type CheckResult,
  type ComparisonStatus,
  type DeviceConfig,
  type SiteBaseline,
} from "./api/client";
import "./App.css";

type DeviceStatus = "PASS" | "FAIL" | "TIMEOUT" | "CONFIG_ERROR" | "UNKNOWN";
type Device = DeviceConfig & {
  status: DeviceStatus;
  lastChecked: string;
  values?: Array<number | boolean>;
  elapsedMs?: number;
  error?: string;
};
const statusMeta: Record<DeviceStatus, { label: string; color: string }> = {
  PASS: { label: "正常", color: "success" },
  FAIL: { label: "失敗", color: "error" },
  TIMEOUT: { label: "逾時", color: "warning" },
  CONFIG_ERROR: { label: "設定錯誤", color: "error" },
  UNKNOWN: { label: "未檢查", color: "default" },
};
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
const defaults = {
  name: "",
  ip: "",
  port: 502,
  unit_id: 1,
  address: 0,
  quantity: 10,
  function: "03" as const,
  expected: "",
  address_mode: "dec" as const,
  connect_timeout_ms: 3000,
  response_timeout_ms: 1000,
  scan_rate_ms: 1000,
  delay_between_polls_ms: 20,
  enabled: true,
};

function DeleteSavedSiteButton() {
  const container = useSyncExternalStore(
    (onStoreChange) => {
      const frame = window.requestAnimationFrame(onStoreChange);
      return () => window.cancelAnimationFrame(frame);
    },
    () => document.querySelector(".header-actions"),
    () => null
  );
  const { message } = AntApp.useApp();
  const deleteSavedConfig = async () => {
    try {
      const sites = await api.listSites();
      if (!sites.length) {
        message.info("目前沒有已儲存的案場");
        return;
      }
      let selectedSite = sites[0];
      Modal.confirm({
        title: "刪除案場存檔",
        content: (
          <Select
            style={{ width: "100%" }}
            defaultValue={selectedSite}
            options={sites.map((site) => ({ value: site, label: site }))}
            onChange={(value) => {
              selectedSite = value;
            }}
          />
        ),
        okText: "刪除存檔",
        cancelText: "取消",
        okButtonProps: { danger: true },
        onOk: async () => {
          await api.deleteSite(selectedSite);
          message.success(`已刪除 ${selectedSite}`);
          window.location.reload();
        },
      });
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "案場存檔刪除失敗"
      );
    }
  };

  return container
    ? createPortal(
        <Tooltip title="刪除案場存檔">
          <Button
            danger
            aria-label="刪除案場存檔"
            icon={<DeleteOutlined />}
            onClick={() => void deleteSavedConfig()}
          />
        </Tooltip>,
        container
      )
    : null;
}

function Dashboard() {
  const batchPageSize = 25;
  const [activeModule, setActiveModule] = useState("connection");
  const [siteName, setSiteName] = useState("未命名案場");
  const [devices, setDevices] = useState<Device[]>([]);
  const [editing, setEditing] = useState<Device | null>(null);
  const [form] = Form.useForm();
  const [checking, setChecking] = useState(false);
  const [pollingActive, setPollingActive] = useState(false);
  const [batches, setBatches] = useState<CheckBatch[]>([]);
  const [batchPage, setBatchPage] = useState(1);
  const [batchTotal, setBatchTotal] = useState(0);
  const [baseline, setBaseline] = useState<SiteBaseline | null>(null);
  const [batchDetail, setBatchDetail] = useState<BatchDetail | null>(null);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [batchStarting, setBatchStarting] = useState(false);
  const [batchNote, setBatchNote] = useState("");
  const [cancellingBatchId, setCancellingBatchId] = useState<string | null>(null);
  const [comparisonLoadingId, setComparisonLoadingId] = useState<string | null>(null);
  const { message } = AntApp.useApp();
  const counts = useMemo(
    () => ({
      total: devices.length,
      healthy: devices.filter((d) => d.status === "PASS").length,
      attention: devices.filter((d) => d.status !== "PASS").length,
    }),
    [devices]
  );

  const toDevice = (device: DeviceConfig, result?: CheckResult): Device => ({
    ...device,
    status: result?.status ?? "UNKNOWN",
    lastChecked: result
      ? new Date(result.timestamp).toLocaleString()
      : "尚未檢查",
    values: result?.values,
    elapsedMs: result?.elapsed_ms,
    error: result?.error_message ?? undefined,
  });
  const toConfig = (device: Device): DeviceConfig => {
    const config = { ...device } as Partial<Device>;
    delete config.status;
    delete config.lastChecked;
    delete config.values;
    delete config.elapsedMs;
    delete config.error;
    return config as DeviceConfig;
  };
  const saveSiteName = async () => {
    const trimmed = siteName.trim();
    if (!trimmed) return;
    try {
      const saved = await api.saveSite({
        schema_version: 1,
        site_name: trimmed,
        devices: devices.map(toConfig),
      });
      setSiteName(saved.site_name);
      message.success("案場名稱已儲存");
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "案場名稱儲存失敗"
      );
    }
  };
  useEffect(() => {
    api
      .getSite()
      .then((site) => {
        setSiteName(site.site_name);
        setDevices(site.devices.map((device) => toDevice(device)));
      })
      .catch((error: unknown) =>
        message.error(
          error instanceof Error ? error.message : "案場設定讀取失敗"
        )
      );
  }, [message]);
  useEffect(() => {
    api
      .getPollingStatus()
      .then((status) => setPollingActive(status.active))
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.listBatches(siteName, (batchPage - 1) * batchPageSize, batchPageSize).catch(() => null),
      api.getBaseline(siteName).catch(() => null),
    ]).then(([history, currentBaseline]) => {
      if (cancelled) return;
      setBatches(history?.items ?? []);
      setBatchTotal(history?.total ?? 0);
      setBaseline(currentBaseline);
    });
    return () => {
      cancelled = true;
    };
  }, [batchPage, batchPageSize, siteName]);
  useEffect(() => {
    if (!activeBatchId) return;
    let cancelled = false;
    let timer: number | undefined;
    const refreshBatch = async () => {
      try {
        const detail = await api.getBatch(activeBatchId);
        if (cancelled) return;
        setBatchDetail(detail);
        if (["completed", "failed", "cancelled"].includes(detail.batch.status)) {
          const history = await api.listBatches(
            siteName,
            (batchPage - 1) * batchPageSize,
            batchPageSize,
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
      timer = window.setTimeout(() => void refreshBatch(), 1000);
    };
    void refreshBatch();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeBatchId, batchPage, batchPageSize, siteName]);
  useEffect(() => {
    if (!pollingActive) return;
    const refreshStatus = () => {
      api
        .getStatus()
        .then((results) =>
          setDevices((current) =>
            current.map((device) => {
              const result = results.find(
                (item) => item.device_name === device.name
              );
              return result ? toDevice(device, result) : device;
            })
          )
        )
        .catch(() => undefined);
      };
      refreshStatus();
      const timer = window.setInterval(refreshStatus, 1000);
    return () => window.clearInterval(timer);
  }, [pollingActive]);
  const runCheck = async (target?: Device) => {
    setChecking(true);
    try {
      const results = await api.check(target?.name);
      setDevices((current) =>
        current.map((device) => {
          const result = results.find(
            (item) => item.device_name === device.name
          );
          return result ? toDevice(device, result) : device;
        })
      );
      message.success(target ? `${target.name} 檢查完成` : "全部設備檢查完成");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "設備檢查失敗");
    } finally {
      setChecking(false);
    }
  };
  const togglePolling = async (active: boolean) => {
    try {
      const response = active
        ? await api.startPolling()
        : await api.stopPolling();
      setPollingActive(response.status.active);
      message.success(active ? "自動檢查已啟動" : "自動檢查已停止");
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "自動檢查設定失敗"
      );
    }
  };
  const startRegressionBatch = async () => {
    setBatchStarting(true);
    try {
      const batch = await api.createBatch(siteName, batchNote.trim());
      setBatchDetail({
        batch,
        records: [],
        completed_device_count: 0,
        health_summary: {
          device_count: 0,
          pass_count: 0,
          fail_count: 0,
          timeout_count: 0,
          config_error_count: 0,
          pass_rate: 0,
          avg_elapsed_ms: null,
          slowest_device: null,
          slowest_elapsed_ms: null,
          new_failure_count: 0,
        },
      });
      setBatchNote("");
      setBatchPage(1);
      setBatches((current) => [batch, ...current.filter((item) => item.id !== batch.id)]);
      setBatchTotal((total) => total + 1);
      setActiveBatchId(batch.id);
      message.info("回歸檢查已開始");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "回歸檢查啟動失敗");
    } finally {
      setBatchStarting(false);
    }
  };
  const setBatchAsBaseline = (batch: CheckBatch) => {
    const containsErrors =
      batch.fail_count + batch.timeout_count + batch.config_error_count > 0;
    Modal.confirm({
      title: "設為案場基準",
      content: containsErrors
        ? "這個批次含有失敗、逾時或設定錯誤。仍要強制設為比較基準嗎？"
        : `將 ${new Date(batch.started_at).toLocaleString()} 的完整檢查設為目前基準。`,
      okText: containsErrors ? "仍要設為基準" : "設為基準",
      cancelText: "取消",
      onOk: async () => {
        try {
          const saved = await api.setBaseline(siteName, batch.id, containsErrors);
          setBaseline(saved);
          message.success("案場基準已更新");
        } catch (error) {
          message.error(error instanceof Error ? error.message : "基準設定失敗");
          throw error;
        }
      },
    });
  };
  const compareBatch = async (batch: CheckBatch) => {
    setComparisonLoadingId(batch.id);
    try {
      setBatchDetail(await api.getBatch(batch.id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "批次比較失敗");
    } finally {
      setComparisonLoadingId(null);
    }
  };
  const cancelBatch = async (batch: CheckBatch) => {
    setCancellingBatchId(batch.id);
    try {
      const updated = await api.cancelBatch(batch.id);
      setBatches((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
      message.info("已送出取消要求；目前進行中的設備讀取會完成後停止後續檢查");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "取消批次失敗");
    } finally {
      setCancellingBatchId(null);
    }
  };
  const submit = async () => {
    const values = (await form.validateFields()) as DeviceConfig;
    const next = { ...values, expected: values.expected || null };
    try {
      if (editing) await api.updateDevice(editing.name, next);
      else await api.addDevice(next);
      setDevices((current) =>
        editing
          ? current.map((d) =>
              d.name === editing.name
                ? toDevice(
                    next,
                    d.status === "UNKNOWN"
                      ? undefined
                      : {
                          device_name: d.name,
                          timestamp: new Date().toISOString(),
                          status: d.status,
                          values: d.values ?? [],
                          elapsed_ms: d.elapsedMs ?? 0,
                          error_message: d.error ?? null,
                          error_type: null,
                        }
                  )
                : d
            )
          : [...current, toDevice(next)]
      );
      setEditing(null);
      form.resetFields();
      message.success(editing ? "連線設定已更新" : "連線已新增");
      await runCheck();
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "連線設定儲存失敗"
      );
    }
  };
  const openEdit = (device: Device) => {
    setEditing(device);
    form.setFieldsValue(device);
  };
  const remove = (device: Device) =>
    Modal.confirm({
      title: `刪除 ${device.name}？`,
      content: "刪除後仍可從案場 JSON 重新匯入。",
      okText: "刪除",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteDevice(device.name);
          setDevices((current) =>
            current.filter((d) => d.name !== device.name)
          );
          message.success("設備已刪除");
        } catch (error) {
          message.error(
            error instanceof Error ? error.message : "設備刪除失敗"
          );
        }
      },
    });
  const saveConfig = async () => {
    try {
      const saved = await api.saveSite({
        schema_version: 1,
        site_name: siteName.trim() || "未命名案場",
        devices: devices.map(toConfig),
      });
      setSiteName(saved.site_name);
      message.success("案場設定已儲存");
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "案場設定儲存失敗"
      );
    }
  };
  const readConfig = async () => {
    try {
      const sites = await api.listSites();
      if (!sites.length) {
        message.info("目前沒有已儲存的案場");
        return;
      }
      let selectedSite = sites.includes(siteName) ? siteName : sites[0];
      Modal.confirm({
        title: "讀取案場設定",
        content: (
          <Select
            style={{ width: "100%" }}
            defaultValue={selectedSite}
            options={sites.map((site) => ({ value: site, label: site }))}
            onChange={(value) => {
              selectedSite = value;
            }}
          />
        ),
        okText: "讀取",
        cancelText: "取消",
        onOk: async () => {
          try {
            const saved = await api.getSite(selectedSite);
            setSiteName(saved.site_name);
            setDevices(saved.devices.map((device) => toDevice(device)));
            setEditing(null);
            form.resetFields();
            form.setFieldsValue(defaults);
            message.success(`已讀取 ${saved.site_name}`);
          } catch (error) {
            message.error(
              error instanceof Error ? error.message : "案場設定讀取失敗"
            );
          }
        },
      });
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "案場清單讀取失敗"
      );
    }
  };
  const clearCurrentConfig = () =>
    Modal.confirm({
      title: "清空目前案場設定？",
      content: "目前的設備設定將被清除，且無法從畫面復原。",
      okText: "清空設定",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const saved = await api.saveSite({
            schema_version: 1,
            site_name: "未命名案場",
            devices: [],
          });
          setSiteName(saved.site_name);
          setDevices([]);
          setEditing(null);
          form.resetFields();
          form.setFieldsValue(defaults);
          message.success("案場設定已清空");
        } catch (error) {
          message.error(
            error instanceof Error ? error.message : "案場設定清空失敗"
          );
        }
      },
    });
  const columns = [
    {
      title: "設備",
      dataIndex: "name",
      key: "name",
      render: (name: string, d: Device) => (
        <div className="device-name">
          <strong>{name}</strong>
          <span>
            {d.ip}:{d.port}
          </span>
        </div>
      ),
    },
    {
      title: "讀取設定",
      key: "definition",
      render: (_: unknown, d: Device) => (
        <span className="definition">
          FC {d.function} · {d.address === 0 ? "40001" : d.address} ·{" "}
          {d.quantity} 筆
        </span>
      ),
    },
    {
      title: "Unit ID",
      dataIndex: "unit_id",
      key: "unit_id",
    },
    {
      title: "狀態",
      dataIndex: "status",
      key: "status",
      render: (status: DeviceStatus, d: Device) => (
        <div>
          <Tag color={statusMeta[status].color}>{statusMeta[status].label}</Tag>
          <span className="status-detail">{d.error || d.lastChecked}</span>
        </div>
      ),
    },
    {
      title: "值",
      dataIndex: "values",
      key: "values",
      render: (values?: Array<number | boolean>) =>
        values?.length ? values.join(", ") : "—",
    },
    {
      title: "耗時",
      dataIndex: "elapsedMs",
      key: "elapsedMs",
      render: (value?: number) => (value ? `${value} ms` : "—"),
    },
    {
      title: "",
      key: "actions",
      align: "right" as const,
      render: (_: unknown, d: Device) => (
        <Space size={4}>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            loading={checking}
            onClick={() => runCheck(d)}
            aria-label={`檢查 ${d.name}`}
          />
          <Button
            type="text"
            icon={<EditOutlined />}
            onClick={() => openEdit(d)}
            aria-label={`編輯 ${d.name}`}
          />
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            onClick={() => remove(d)}
            aria-label={`刪除 ${d.name}`}
          />
        </Space>
      ),
    },
  ];
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
              onClick={() => void cancelBatch(batch)}
            >
              取消
            </Button>
          )}
          <Button
            type="link"
            disabled={batch.status !== "completed"}
            loading={comparisonLoadingId === batch.id}
            onClick={() => void compareBatch(batch)}
          >
            比較基準
          </Button>
          <Button
            type="link"
            disabled={batch.status !== "completed" || batch.mode !== "full"}
            onClick={() => setBatchAsBaseline(batch)}
          >
            設為基準
          </Button>
          <Button
            type="link"
            disabled={batch.status !== "completed"}
            href={api.getReportUrl(batch.id, "csv")}
          >
            CSV
          </Button>
          <Button
            type="link"
            disabled={batch.status !== "completed"}
            href={api.getReportUrl(batch.id, "html")}
          >
            HTML
          </Button>
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
      const leftRank = left.comparison_status
        ? regressionPriority[left.comparison_status] ?? 4
        : 0;
      const rightRank = right.comparison_status
        ? regressionPriority[right.comparison_status] ?? 4
        : 0;
      return leftRank - rightRank;
    });
  const anomalyColumns = [
    {
      title: "設備",
      dataIndex: "result",
      key: "device",
      render: (result: CheckResult) => result.device_name,
    },
    {
      title: "本次狀態",
      dataIndex: "result",
      key: "result_status",
      render: (result: CheckResult) => (
        <Tag color={statusMeta[result.status].color}>{statusMeta[result.status].label}</Tag>
      ),
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
    <Layout className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <ThunderboltOutlined />
          </div>
          <div>
            <Typography.Title level={4}>MODBUS / POLL CHECKER</Typography.Title>
            <span className="eyebrow">FIELD CONNECTION CONSOLE</span>
          </div>
        </div>
        <div className="site-switcher">
          <span className="muted-label">目前案場</span>
          <Input
            value={siteName}
            onChange={(e) => setSiteName(e.target.value)}
            onBlur={saveSiteName}
            onPressEnter={saveSiteName}
            bordered={false}
          />
        </div>
        <div className="header-actions">
          <Space size={6}>
            <Tooltip title="儲存案場設定">
              <Button
                aria-label="儲存案場設定"
                icon={<SaveOutlined />}
                onClick={saveConfig}
              />
            </Tooltip>
            <Tooltip title="讀取案場設定">
              <Button
                aria-label="讀取案場設定"
                icon={<FolderOpenOutlined />}
                onClick={readConfig}
              />
            </Tooltip>
            <Tooltip title="清空目前設定">
              <Button
                danger
                aria-label="清空目前設定"
                icon={<DeleteOutlined />}
                onClick={clearCurrentConfig}
              />
            </Tooltip>
          </Space>
        </div>
        <div className="local-badge">
          <span className="pulse" /> LOCAL INSTANCE
        </div>
      </header>
      <main className="workspace">
        <Tabs
          className="module-tabs"
          activeKey={activeModule}
          onChange={setActiveModule}
          items={[
            { key: "connection", label: "連線狀況" },
            { key: "regression", label: "回歸測試" },
          ]}
        />
        {activeModule === "connection" && (
          <>
        <section className="intro">
          <div>
            <span className="section-kicker">01 / CONNECTION CONTROL</span>
            <Typography.Title>設備連線總覽</Typography.Title>
            <Typography.Paragraph>
              集中管理現場 Modbus TCP 設備，快速確認每一條連線的健康狀態。
            </Typography.Paragraph>
          </div>
        </section>
        <Row gutter={[16, 16]} className="metrics">
          <Col xs={8}>
            <Card bordered={false}>
              <Statistic
                title="已登錄設備"
                value={counts.total}
                suffix="台"
                prefix={<span className="metric-icon">◉</span>}
              />
            </Card>
          </Col>
          <Col xs={8}>
            <Card bordered={false}>
              <Statistic
                title="目前正常"
                value={counts.healthy}
                suffix="台"
                prefix={<span className="metric-icon good">↗</span>}
              />
            </Card>
          </Col>
          <Col xs={8}>
            <Card bordered={false}>
              <Statistic
                title="需要注意"
                value={counts.attention}
                suffix="台"
                prefix={<span className="metric-icon warn">!</span>}
              />
            </Card>
          </Col>
        </Row>
        <section className="content-grid">
          <Card
            className="status-panel"
            bordered={false}
            title={
              <div>
                <span className="section-kicker">LIVE STATUS</span>
                <h2>連線狀態</h2>
              </div>
            }
            extra={
              <Space>
                <Switch
                  checked={pollingActive}
                  onChange={togglePolling}
                  checkedChildren="自動"
                  unCheckedChildren="手動"
                />
                <Button
                  type="text"
                  icon={<ReloadOutlined />}
                  onClick={() => runCheck()}
                  loading={checking}
                >
                  全部檢查
                </Button>
              </Space>
            }
          >
            <Alert
              className="local-alert"
              type="info"
              showIcon
              message={pollingActive ? "自動檢查中" : "目前為本機模式"}
              description="檢查請求會由本機 Python API 轉送至現場設備。"
            />
            <Table
              rowKey="name"
              columns={columns}
              dataSource={devices}
              pagination={false}
              scroll={{ x: 700 }}
            />
          </Card>
          <Card
            className="quick-panel"
            bordered={false}
            title={
              <div>
                <span className="section-kicker">QUICK SETUP</span>
                <h2>{editing ? "編輯連線" : "新增連線"}</h2>
              </div>
            }
          >
            <Form
              form={form}
              layout="vertical"
              initialValues={defaults}
              onFinish={submit}
            >
              <Form.Item
                label="設備名稱"
                name="name"
                rules={[{ required: true, message: "請輸入設備名稱" }]}
              >
                <Input placeholder="例如 PLC-01" />
              </Form.Item>
              <Row gutter={12}>
                <Col span={15}>
                  <Form.Item
                    label="IP 位址"
                    name="ip"
                    rules={[
                      { required: true, message: "請輸入 IP 位址" },
                      {
                        pattern:
                          /^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$/,
                        message: "IP 格式不正確",
                      },
                    ]}
                  >
                    <Input placeholder="192.168.0.50" />
                  </Form.Item>
                </Col>
                <Col span={9}>
                  <Form.Item label="Port" name="port">
                    <InputNumber
                      min={1}
                      max={65535}
                      style={{ width: "100%" }}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item label="Unit ID" name="unit_id">
                    <InputNumber min={0} max={247} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="功能碼" name="function">
                    <Select
                      options={[
                        { value: "01", label: "01 · Coils" },
                        { value: "02", label: "02 · Discrete Inputs" },
                        { value: "03", label: "03 · Holding Registers" },
                        { value: "04", label: "04 · Input Registers" },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col span={14}>
                  <Form.Item label="起始位址" name="address">
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={10}>
                  <Form.Item label="讀取數量" name="quantity">
                    <InputNumber min={1} max={2000} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              <Divider />
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item label="連線逾時 (ms)" name="connect_timeout_ms">
                    <InputNumber min={1} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="回應逾時 (ms)" name="response_timeout_ms">
                    <InputNumber min={1} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item label="輪詢週期 (ms)" name="scan_rate_ms">
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    label="設備間隔 (ms)"
                    name="delay_between_polls_ms"
                  >
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item
                label="啟用輪詢"
                name="enabled"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Button
                block
                type="primary"
                htmlType="submit"
                icon={<PlusOutlined />}
              >
                儲存連線設定
              </Button>
            </Form>
          </Card>
        </section>
          </>
        )}
        {activeModule === "regression" && (
          <>
        <section className="intro">
          <div>
            <span className="section-kicker">02 / REGRESSION TESTING</span>
            <Typography.Title>回歸測試總覽</Typography.Title>
            <Typography.Paragraph>
              設定案場基準，追蹤每次檢查結果與設備狀態變化。
            </Typography.Paragraph>
          </div>
        </section>
        <section className="batch-history">
          <Card
            bordered={false}
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
                disabled={devices.filter((device) => device.enabled).length === 0}
                onClick={() => void startRegressionBatch()}
              >
                開始回歸檢查
              </Button>
            }
          >
            <Input.TextArea
              aria-label="本次檢查備註"
              value={batchNote}
              onChange={(event) => setBatchNote(event.target.value)}
              maxLength={500}
              showCount
              placeholder="本次變更或檢查備註（選填）"
              autoSize={{ minRows: 2, maxRows: 4 }}
              style={{ marginBottom: 16 }}
            />
            <Alert
              type={baseline ? "success" : "warning"}
              showIcon
              message={
                baseline
                  ? `目前基準：${new Date(baseline.updated_at).toLocaleString()}`
                  : "尚未設定案場基準"
              }
              description={
                baseline
                  ? `基準批次 ${baseline.baseline_batch_id}；檢查完成後可比較本次結果。`
                  : "先完成一次全案場檢查，再從批次歷史將合格批次設為基準。"
              }
              style={{ marginBottom: 16 }}
            />
            {batchDetail && (
              <div className="regression-progress">
                <div className="regression-progress-heading">
                  <strong>
                    {batchDetail.batch.status === "completed"
                      ? "最近批次已完成"
                      : batchDetail.batch.status === "failed"
                        ? "最近批次失敗"
                        : batchDetail.batch.status === "cancelled"
                          ? "最近批次已取消"
                          : "回歸檢查執行中"}
                  </strong>
                  <span>
                    {batchDetail.completed_device_count} / {batchDetail.batch.device_names.length} 台設備
                  </span>
                </div>
                <Progress
                  percent={batchDetail.batch.device_names.length
                    ? Math.round(batchDetail.completed_device_count / batchDetail.batch.device_names.length * 100)
                    : 0}
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
            {batchDetail?.batch.status === "failed" && (
              <Alert
                type="error"
                showIcon
                message="回歸檢查批次失敗"
                description={batchDetail.batch.error_message || "批次執行失敗，請稍後重試。"}
                style={{ marginBottom: 16 }}
              />
            )}
            {batchDetail?.batch.status === "cancelled" && (
              <Alert
                type="warning"
                showIcon
                message="回歸檢查已取消"
                description="已停止尚未開始的設備檢查；取消前已完成或正在執行的結果仍會保留在批次中。"
                style={{ marginBottom: 16 }}
              />
            )}
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
                        {(record.diagnosis?.suggestions ?? []).map((suggestion) => (
                          <li key={suggestion}>{suggestion}</li>
                        ))}
                      </ul>
                    ),
                    rowExpandable: (record) => Boolean(record.diagnosis?.suggestions.length),
                  }}
                  size="small"
                  scroll={{ x: 700 }}
                />
              </div>
            )}
            <Table
              rowKey="id"
              columns={batchColumns}
              dataSource={batches}
              pagination={{
                current: batchPage,
                pageSize: batchPageSize,
                total: batchTotal,
                hideOnSinglePage: true,
                onChange: (page) => setBatchPage(page),
              }}
              size="small"
              scroll={{ x: 720 }}
              locale={{ emptyText: "尚無檢查批次" }}
            />
          </Card>
        </section>
          </>
        )}
      </main>
    </Layout>
  );
}
export default function App() {
  return (
    <AntApp>
      <Dashboard />
      <DeleteSavedSiteButton />
    </AntApp>
  );
}
