export type DeviceConfig = {
  name: string
  ip: string
  port: number
  unit_id: number
  address: number
  quantity: number
  function: '03' | '04'
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
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `API request failed (${response.status})`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  getSite: () => request<SiteConfig>('/api/site'),
  importSite: (config: SiteConfig) => request<SiteConfig>('/api/site/import', { method: 'POST', body: JSON.stringify(config) }),
  addDevice: (device: DeviceConfig) => request<DeviceConfig>('/api/devices', { method: 'POST', body: JSON.stringify(device) }),
  updateDevice: (name: string, device: DeviceConfig) => request<DeviceConfig>(`/api/devices/${encodeURIComponent(name)}`, { method: 'PUT', body: JSON.stringify(device) }),
  deleteDevice: (name: string) => request<void>(`/api/devices/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  check: (deviceName?: string) => request<CheckResult[]>('/api/check', { method: 'POST', body: JSON.stringify(deviceName ? { device_name: deviceName } : {}) }),
  getStatus: () => request<CheckResult[]>('/api/status'),
  startPolling: () => request<{ started: boolean; status: PollingStatus }>('/api/polling/start', { method: 'POST' }),
  stopPolling: () => request<{ stopped: boolean; status: PollingStatus }>('/api/polling/stop', { method: 'POST' }),
  getPollingStatus: () => request<PollingStatus>('/api/polling/status'),
}
