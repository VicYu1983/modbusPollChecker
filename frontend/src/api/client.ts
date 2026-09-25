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
}

export type PollingStatus = {
  active: boolean
  started_at: string | null
  last_poll_at: string | null
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
}
