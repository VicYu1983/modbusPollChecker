import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import {
  App as AntApp,
  Alert,
  Button,
  Card,
  Col,
  Form,
  Layout,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Tabs,
  Tooltip,
  Typography,
} from "antd";
import {
  DeleteOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  api,
  type BatchDetail,
  type CheckBatch,
  type DeviceConfig,
  type SiteBaseline,
} from "./api/client";
import { toConfig, toDevice, type Device } from "./api/mappers";
import { DeviceEditor } from "./components/DeviceEditor";
import { DeviceTable } from "./components/DeviceTable";
import { deviceDefaults } from "./components/formDefaults";
import { NetworkPanel } from "./components/NetworkPanel";
import { RegressionPanel } from "./components/RegressionPanel";
import { SiteHeader } from "./components/SiteHeader";
import "./App.css";

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
  const [selectedBatchIds, setSelectedBatchIds] = useState<string[]>([]);
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
  const deleteBatches = (batchIds: string[]) => {
    if (!batchIds.length) return;
    Modal.confirm({
      title: batchIds.length === 1 ? "刪除檢查批次" : "清理歷史批次",
      content: `確定刪除 ${batchIds.length} 個批次及其檢查結果？此操作無法復原。`,
      okText: "刪除",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        const results = await Promise.allSettled(
          batchIds.map((id) => api.deleteBatch(id))
        );
        const deletedIds = batchIds.filter(
          (_, index) => results[index].status === "fulfilled"
        );
        const failedCount = results.length - deletedIds.length;
        setSelectedBatchIds([]);
        if (deletedIds.length) {
          setBatchDetail((current) =>
            current && deletedIds.includes(current.batch.id) ? null : current
          );
          const nextPage =
            batches.length <= deletedIds.length && batchPage > 1
              ? batchPage - 1
              : batchPage;
          if (nextPage !== batchPage) {
            setBatchPage(nextPage);
          } else {
            try {
              const history = await api.listBatches(
                siteName,
                (batchPage - 1) * batchPageSize,
                batchPageSize
              );
              setBatches(history.items);
              setBatchTotal(history.total);
            } catch {
              setBatches((current) =>
                current.filter((batch) => !deletedIds.includes(batch.id))
              );
              setBatchTotal((total) => Math.max(0, total - deletedIds.length));
            }
          }
        }
        if (failedCount) {
          message.error(
            `${deletedIds.length} 個批次已刪除，${failedCount} 個刪除失敗；基準批次請先清除基準。`
          );
        } else {
          message.success(`已刪除 ${deletedIds.length} 個批次及其檢查結果`);
        }
      },
    });
  };
  const clearCurrentBaseline = () => {
    if (!baseline) return;
    Modal.confirm({
      title: "清除案場基準",
      content: "清除基準不會刪除批次資料；之後可重新指定基準。",
      okText: "清除基準",
      cancelText: "取消",
      onOk: async () => {
        try {
          await api.clearBaseline(siteName);
          setBaseline(null);
          setSelectedBatchIds((current) =>
            current.filter((id) => id !== baseline.baseline_batch_id)
          );
          message.success("案場基準已清除");
        } catch (error) {
          message.error(error instanceof Error ? error.message : "基準清除失敗");
          throw error;
        }
      },
    });
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
            form.setFieldsValue(deviceDefaults);
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
          form.setFieldsValue(deviceDefaults);
          message.success("案場設定已清空");
        } catch (error) {
          message.error(
            error instanceof Error ? error.message : "案場設定清空失敗"
          );
        }
      },
    });
  return (
    <Layout className="app-shell">
      <SiteHeader
        siteName={siteName}
        onSiteNameChange={setSiteName}
        onSiteNameSave={saveSiteName}
        onSaveConfig={saveConfig}
        onReadConfig={readConfig}
        onClearConfig={clearCurrentConfig}
      />
      <main className="workspace">
        <Tabs
          className="module-tabs"
          activeKey={activeModule}
          onChange={setActiveModule}
          items={[
            { key: "device", label: "設備檢查" },
            { key: "regression", label: "回歸測試" },
          ]}
        />
        {activeModule === "device" && (
          <NetworkPanel
            siteName={siteName}
            devices={devices}
            form={form}
            editing={editing}
            onEdit={openEdit}
            onRemove={remove}
            onSubmit={() => form.submit()}
          />
        )}
        {activeModule === "legacy_connection" && (
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
            <Card variant="borderless">
              <Statistic
                title="已登錄設備"
                value={counts.total}
                suffix="台"
                prefix={<span className="metric-icon">◉</span>}
              />
            </Card>
          </Col>
          <Col xs={8}>
            <Card variant="borderless">
              <Statistic
                title="目前正常"
                value={counts.healthy}
                suffix="台"
                prefix={<span className="metric-icon good">↗</span>}
              />
            </Card>
          </Col>
          <Col xs={8}>
            <Card variant="borderless">
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
            variant="borderless"
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
              title={pollingActive ? "自動檢查中" : "目前為本機模式"}
              description="檢查請求會由本機 Python API 轉送至現場設備。"
            />
            <DeviceTable
              devices={devices}
              checking={checking}
              onCheck={(device) => void runCheck(device)}
              onEdit={openEdit}
              onRemove={remove}
            />
          </Card>
          <Card
            className="quick-panel"
            variant="borderless"
            title={
              <div>
                <span className="section-kicker">QUICK SETUP</span>
                <h2>{editing ? "編輯連線" : "新增連線"}</h2>
              </div>
            }
          >
            <DeviceEditor form={form} editing={editing} onSubmit={submit} />
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
        <RegressionPanel
          batches={batches}
          batchTotal={batchTotal}
          batchPage={batchPage}
          batchPageSize={batchPageSize}
          baseline={baseline}
          batchDetail={batchDetail}
          activeBatchId={activeBatchId}
          batchStarting={batchStarting}
          batchNote={batchNote}
          selectedBatchIds={selectedBatchIds}
          cancellingBatchId={cancellingBatchId}
          comparisonLoadingId={comparisonLoadingId}
          enabledDeviceCount={devices.filter((device) => device.enabled && device.network_check_enabled !== false && device.check_profile === "full_stack").length}
          onBatchNoteChange={setBatchNote}
          onStartBatch={() => void startRegressionBatch()}
          onClearBaseline={clearCurrentBaseline}
          onCancelBatch={(batch) => void cancelBatch(batch)}
          onCompareBatch={(batch) => void compareBatch(batch)}
          onSetBaseline={setBatchAsBaseline}
          onDeleteBatches={deleteBatches}
          onSelectionChange={(ids) => setSelectedBatchIds(ids)}
          onPageChange={(page) => {
            setSelectedBatchIds([]);
            setBatchPage(page);
          }}
        />
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
