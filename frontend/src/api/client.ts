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
}
