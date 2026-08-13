export type User = {
  id: number
  email: string
  displayName: string
  vaultSalt: string
  createdAt: string
}

export type Alert = {
  id: number
  category: string
  severity: string
  title: string
  detail: string
  source: string
  acknowledged: boolean
  createdAt: string
}

export type MonitoredItem = {
  id: number
  kind: string
  label: string
  displayMask: string
  status: string
  createdAt: string
}

export type VaultEntry = {
  id: number
  ciphertext: string
  iv: string
  createdAt: string
  updatedAt: string
}

export type Device = {
  id: number
  name: string
  platform: string
  vpnEnabled: boolean
  antivirusEnabled: boolean
  screenLockEnabled: boolean
  updatesCurrent: boolean
  lastCheckIn: string
}

export type AuditEvent = {
  id: number
  action: string
  detail: string
  createdAt: string
}

const TOKEN_KEY = 'lockwell_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(path, { ...init, headers })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`)
  }
  return data as T
}

export const api = {
  register: (body: { email: string; password: string; displayName: string }) =>
    request<{ token: string; user: User }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  login: (body: { email: string; password: string }) =>
    request<{ token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  me: () => request<{ user: User }>('/api/me'),
  dashboard: () =>
    request<{
      summary: {
        openAlerts: number
        highSeverity: number
        monitoredItems: number
        deviceProtectionScore: number
        vaultMode: string
      }
      recentAlerts: Alert[]
      devices: Device[]
    }>('/api/dashboard'),
  alerts: () => request<{ alerts: Alert[] }>('/api/alerts'),
  ackAlert: (id: number) =>
    request<{ alert: Alert }>(`/api/alerts/${id}/ack`, { method: 'POST' }),
  monitored: () => request<{ items: MonitoredItem[] }>('/api/monitored'),
  addMonitored: (body: { kind: string; label: string; value: string }) =>
    request<{ item: MonitoredItem }>('/api/monitored', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  vault: () => request<{ vaultSalt: string; entries: VaultEntry[] }>('/api/vault'),
  saveVault: (body: { id?: number; ciphertext: string; iv: string }) =>
    request<{ entry: VaultEntry }>('/api/vault', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteVault: (id: number) =>
    request<{ ok: boolean }>(`/api/vault/${id}`, { method: 'DELETE' }),
  devices: () => request<{ devices: Device[] }>('/api/devices'),
  updateDevice: (id: number, body: Record<string, boolean>) =>
    request<{ device: Device }>(`/api/devices/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  audit: () => request<{ events: AuditEvent[] }>('/api/audit'),
  architecture: () =>
    request<{ product: string; principles: string[]; mvpLimits: string[] }>(
      '/api/architecture',
    ),
}
