export type DeviceConfig = {
  name: string
  ip: string
  port: number
  unit_id: number
  address: number
  quantity: number
  function: '01' | '02' | '03' | '04'
  expected: string | null
  address_mode: 'dec' | 'hex'
  connect_timeout_ms: number
  response_timeout_ms: number
  scan_rate_ms: number
  delay_between_polls_ms: number
  enabled: boolean
  check_profile: 'ping' | 'ping_tcp' | 'full_stack'
  network_check_enabled?: boolean
  ping_enabled?: boolean
  ping_attempts?: number
  ping_timeout_ms?: number
  ping_interval_ms?: number
  tcp_check_enabled?: boolean
  tcp_port?: number | null
  tcp_timeout_ms?: number
  skip_when_ping_failed?: boolean
  max_latency_ms?: number | null
  max_loss_percent?: number | null
}

export type SiteConfig = {
  schema_version: 1
  site_name: string
  devices: DeviceConfig[]
}

export type CheckResult = {
  device_name: string
  timestamp: string
  status: 'PASS' | 'FAIL' | 'TIMEOUT' | 'CONFIG_ERROR' | 'UNKNOWN'
  values: Array<number | boolean>
  elapsed_ms: number
  error_message: string | null
  error_type: string | null
}

export type PollingStatus = {
  active: boolean
  started_at: string | null
  last_poll_at: string | null
}

export type CheckBatch = {
  id: string
  site_name: string
  mode: 'single' | 'full'
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  device_names: string[]
  config_snapshot: SiteConfig
  note: string | null
  started_at: string
  completed_at: string | null
  pass_count: number
  fail_count: number
  timeout_count: number
  config_error_count: number
  unknown_count: number
  error_message: string | null
}

export type CheckRecord = {
  id: number | null
  batch_id: string
  result: CheckResult
  device_snapshot: DeviceConfig
  comparison_status: ComparisonStatus | null
  response_time_delta_ms: number | null
  diagnosis: Diagnosis | null
}

export type Diagnosis = {
  category: 'NETWORK' | 'MODBUS_TIMEOUT' | 'MODBUS_EXCEPTION' | 'DATA_MISMATCH' | 'LATENCY' | 'CONFIG'
  summary: string
  suggestions: string[]
}

export type HealthSummary = {
  device_count: number
  pass_count: number
  fail_count: number
  timeout_count: number
  config_error_count: number
  pass_rate: number
  avg_elapsed_ms: number | null
  slowest_device: string | null
  slowest_elapsed_ms: number | null
  new_failure_count: number
}

export type BatchDetail = {
  batch: CheckBatch
  records: CheckRecord[]
  completed_device_count: number
  health_summary: HealthSummary
}

export type SiteBaseline = {
  site_name: string
  baseline_batch_id: string
  updated_at: string
}

export type ComparisonStatus =
  | 'UNCHANGED_PASS'
  | 'UNCHANGED_FAILURE'
  | 'NEW_FAILURE'
  | 'RECOVERED'
  | 'VALUE_CHANGED'
  | 'LATENCY_DEGRADED'
  | 'CONFIG_CHANGED'
  | 'BASELINE_ONLY'
  | 'NEW_DEVICE'
  | 'NO_BASELINE'

export type NetworkMode = 'network_only' | 'network_and_port' | 'full_stack'
export type NetworkCheckStatus = 'PASS' | 'FAIL' | 'TIMEOUT' | 'CONFIG_ERROR' | 'PARTIAL' | 'UNKNOWN'

export type NetworkCheckResult = {
  device_name: string
  target_ip: string
  timestamp: string
  mode: NetworkMode
  check_profile: 'ping' | 'ping_tcp' | 'full_stack'
  ping_state: 'PASS' | 'TIMEOUT' | 'UNREACHABLE' | 'NOT_SUPPORTED' | 'UNKNOWN'
  ping_attempts: number
  ping_success_count: number
  ping_loss_percent: number | null
  ping_min_ms: number | null
  ping_avg_ms: number | null
  ping_max_ms: number | null
  tcp_port: number | null
  tcp_connect_ms: number | null
  tcp_state: 'OPEN' | 'CLOSED' | 'TIMEOUT' | 'UNREACHABLE' | 'NOT_TESTED'
  overall_status: NetworkCheckStatus
  failure_stage: 'CONFIG' | 'PING' | 'TCP' | 'MODBUS' | null
  error_type: string | null
  error_message: string | null
  modbus_status: CheckResult['status'] | null
  modbus_error_type: string | null
  modbus_error_message: string | null
  diagnosis_summary: string | null
  diagnosis_suggestions: string[]
  threshold_violations: string[]
}

export type NetworkBatchStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export type NetworkBatch = {
  id: string
  site_name: string
  mode: NetworkMode | 'mixed'
  status: NetworkBatchStatus
  device_names: string[]
  config_snapshot: SiteConfig
  max_concurrency: number
  started_at: string
  completed_at: string | null
  completed_device_count: number
  pass_count: number
  fail_count: number
  timeout_count: number
  config_error_count: number
  partial_count: number
  unknown_count: number
  error_message: string | null
}

export type NetworkCheckRecord = {
  id: number | null
  batch_id: string
  result: NetworkCheckResult
  device_snapshot: DeviceConfig
}

export type NetworkBatchDetail = {
  batch: NetworkBatch
  results: NetworkCheckRecord[]
  completed_device_count: number
}

export type NetworkDeviceTrend = {
  device_name: string
  current_status: NetworkCheckStatus
  sample_count: number
  historical_failure_count: number
  intermittent_disconnect: boolean
  previous_avg_latency_ms: number | null
  current_avg_latency_ms: number | null
  latency_delta_ms: number | null
  latency_degraded: boolean
  previous_avg_loss_percent: number | null
  current_loss_percent: number | null
  loss_delta_percent: number | null
  loss_degraded: boolean
  summary: string
}

export type NetworkBatchTrend = {
  batch_id: string
  site_name: string
  mode: NetworkMode | 'mixed'
  historical_batch_count: number
  latency_degraded_count: number
  loss_degraded_count: number
  intermittent_disconnect_count: number
  summary: string
  devices: NetworkDeviceTrend[]
  generated_at: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string; message?: string; details?: Array<{ field: string; message: string }> } | null
    const details = body?.details?.map((item) => `${item.field}: ${item.message}`).join('; ')
    throw new Error(details || body?.message || body?.detail || `API request failed (${response.status})`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  getSite: (siteName?: string) => request<SiteConfig>(siteName ? `/api/site?site_name=${encodeURIComponent(siteName)}` : '/api/site'),
  listSites: () => request<string[]>('/api/sites'),
  saveSite: (config: SiteConfig) => request<SiteConfig>('/api/site/save', { method: 'POST', body: JSON.stringify(config) }),
  deleteSite: (siteName: string) => request<void>(`/api/site/${encodeURIComponent(siteName)}`, { method: 'DELETE' }),
  addDevice: (device: DeviceConfig) => request<DeviceConfig>('/api/devices', { method: 'POST', body: JSON.stringify(device) }),
  updateDevice: (name: string, device: DeviceConfig) => request<DeviceConfig>(`/api/devices/${encodeURIComponent(name)}`, { method: 'PUT', body: JSON.stringify(device) }),
  deleteDevice: (name: string) => request<void>(`/api/devices/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  check: (deviceName?: string) => request<CheckResult[]>('/api/check', { method: 'POST', body: JSON.stringify(deviceName ? { device_name: deviceName } : {}) }),
  getStatus: () => request<CheckResult[]>('/api/status'),
  startPolling: () => request<{ started: boolean; status: PollingStatus }>('/api/polling/start', { method: 'POST' }),
  stopPolling: () => request<{ stopped: boolean; status: PollingStatus }>('/api/polling/stop', { method: 'POST' }),
  getPollingStatus: () => request<PollingStatus>('/api/polling/status'),
  createBatch: (siteName: string, note?: string) => request<CheckBatch>('/api/check/batches', {
    method: 'POST',
    body: JSON.stringify({ site_name: siteName, note: note || null }),
  }),
  listBatches: (siteName: string, offset = 0, limit = 25) => request<{ items: CheckBatch[]; total: number }>(
    `/api/check/batches?site_name=${encodeURIComponent(siteName)}&offset=${offset}&limit=${limit}`,
  ),
  getBatch: (batchId: string) => request<BatchDetail>(`/api/check/batches/${encodeURIComponent(batchId)}`),
  cancelBatch: (batchId: string) => request<CheckBatch>(
    `/api/check/batches/${encodeURIComponent(batchId)}/cancel`,
    { method: 'POST' },
  ),
  deleteBatch: (batchId: string) => request<void>(
    `/api/check/batches/${encodeURIComponent(batchId)}`,
    { method: 'DELETE' },
  ),
  getReportUrl: (batchId: string, format: 'csv' | 'html') =>
    `/api/check/batches/${encodeURIComponent(batchId)}/report?format=${format}`,
  getBaseline: (siteName: string) => request<SiteBaseline>(`/api/sites/${encodeURIComponent(siteName)}/baseline`),
  setBaseline: (siteName: string, batchId: string, force: boolean) => request<SiteBaseline>(
    `/api/sites/${encodeURIComponent(siteName)}/baseline`,
    { method: 'PUT', body: JSON.stringify({ batch_id: batchId, force }) },
  ),
  clearBaseline: (siteName: string) => request<void>(
    `/api/sites/${encodeURIComponent(siteName)}/baseline`,
    { method: 'DELETE' },
  ),
  checkNetworkDevice: (deviceName: string, mode: NetworkMode) => request<NetworkCheckResult>(
    '/api/network/check/one',
    { method: 'POST', body: JSON.stringify({ device_name: deviceName, mode }) },
  ),
  createNetworkBatch: (siteName: string, mode: NetworkMode, maxConcurrency: number) => request<NetworkBatch>(
    '/api/network/check',
    { method: 'POST', body: JSON.stringify({ site_name: siteName, mode, max_concurrency: maxConcurrency }) },
  ),
  listNetworkBatches: (siteName: string, offset = 0, limit = 10) => request<{ items: NetworkBatch[]; total: number }>(
    `/api/network/batches?site_name=${encodeURIComponent(siteName)}&offset=${offset}&limit=${limit}`,
  ),
  getNetworkBatch: (batchId: string) => request<NetworkBatchDetail>(
    `/api/network/batches/${encodeURIComponent(batchId)}`,
  ),
  cancelNetworkBatch: (batchId: string) => request<NetworkBatch>(
    `/api/network/batches/${encodeURIComponent(batchId)}/cancel`,
    { method: 'POST' },
  ),
  getNetworkTrend: (batchId: string) => request<NetworkBatchTrend>(
    `/api/network/batches/${encodeURIComponent(batchId)}/trend`,
  ),
  getNetworkReportUrl: (batchId: string, format: 'csv' | 'html') =>
    `/api/network/batches/${encodeURIComponent(batchId)}/report?format=${format}`,
  checkDevice: (deviceName: string) => request<NetworkCheckResult>(
    `/api/device-checks/${encodeURIComponent(deviceName)}`,
    { method: 'POST', body: JSON.stringify({}) },
  ),
  createDeviceCheckBatch: (siteName: string, maxConcurrency: number) => request<NetworkBatch>(
    '/api/device-checks/batches',
    { method: 'POST', body: JSON.stringify({ site_name: siteName, max_concurrency: maxConcurrency }) },
  ),
  listDeviceCheckBatches: (siteName: string, offset = 0, limit = 10) => request<{ items: NetworkBatch[]; total: number }>(
    `/api/device-checks/batches?site_name=${encodeURIComponent(siteName)}&offset=${offset}&limit=${limit}`,
  ),
  getDeviceCheckBatch: (batchId: string) => request<NetworkBatchDetail>(
    `/api/device-checks/batches/${encodeURIComponent(batchId)}`,
  ),
  cancelDeviceCheckBatch: (batchId: string) => request<NetworkBatch>(
    `/api/device-checks/batches/${encodeURIComponent(batchId)}/cancel`,
    { method: 'POST' },
  ),
}
