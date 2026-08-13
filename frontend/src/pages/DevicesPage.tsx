import { useEffect, useState } from 'react'
import { api, type Device } from '../lib/api'

export function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [error, setError] = useState('')

  async function load() {
    const res = await api.devices()
    setDevices(res.devices)
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message))
  }, [])

  async function toggle(device: Device, field: keyof Device, value: boolean) {
    const payload: Record<string, boolean> = {
      [String(field)]: value,
    }
    await api.updateDevice(device.id, payload)
    await load()
  }

  return (
    <div>
      <h1 className="page-title">Device protection</h1>
      <p className="page-sub">
        Posture controls for enrolled devices. This MVP tracks protection state;
        a production build would ship OS agents and a managed VPN.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="stack">
        {devices.map((device) => (
          <article key={device.id} className="list-row">
            <header>
              <h3>
                {device.name} · {device.platform}
              </h3>
              <span className="badge low">
                checked {new Date(device.lastCheckIn).toLocaleString()}
              </span>
            </header>
            <div className="toggle-grid">
              {(
                [
                  ['vpnEnabled', 'VPN tunnel'],
                  ['antivirusEnabled', 'Antivirus'],
                  ['screenLockEnabled', 'Screen lock'],
                  ['updatesCurrent', 'Updates current'],
                ] as const
              ).map(([field, label]) => (
                <label key={field}>
                  <span>{label}</span>
                  <input
                    type="checkbox"
                    checked={Boolean(device[field])}
                    onChange={(e) => void toggle(device, field, e.target.checked)}
                  />
                </label>
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
