import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Alert, type Device } from '../lib/api'

export function DashboardPage() {
  const [summary, setSummary] = useState({
    openAlerts: 0,
    highSeverity: 0,
    monitoredItems: 0,
    deviceProtectionScore: 0,
    vaultMode: 'zero-knowledge',
  })
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .dashboard()
      .then((res) => {
        setSummary(res.summary)
        setAlerts(res.recentAlerts)
        setDevices(res.devices)
      })
      .catch((err: Error) => setError(err.message))
  }, [])

  return (
    <div>
      <h1 className="page-title">Protection overview</h1>
      <p className="page-sub">
        Live posture across alerts, monitored identifiers, and enrolled devices.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="metric-row">
        <div className="metric">
          <span>Open alerts</span>
          <strong>{summary.openAlerts}</strong>
        </div>
        <div className="metric">
          <span>High severity</span>
          <strong>{summary.highSeverity}</strong>
        </div>
        <div className="metric">
          <span>Monitored items</span>
          <strong>{summary.monitoredItems}</strong>
        </div>
        <div className="metric">
          <span>Device score</span>
          <strong>{summary.deviceProtectionScore}%</strong>
        </div>
      </div>

      <section className="stack">
        <header className="list-row" style={{ borderBottom: 0, paddingBottom: 0 }}>
          <h2 style={{ margin: 0, fontFamily: 'var(--font-display)' }}>Recent alerts</h2>
          <Link to="/app/alerts">View all</Link>
        </header>
        {alerts.map((alert) => (
          <article key={alert.id} className="list-row">
            <header>
              <h3>{alert.title}</h3>
              <span className={`badge ${alert.severity}`}>{alert.severity}</span>
            </header>
            <p>{alert.detail}</p>
          </article>
        ))}
      </section>

      <section className="stack" style={{ marginTop: '2rem' }}>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-display)' }}>Devices</h2>
        {devices.map((device) => (
          <article key={device.id} className="list-row">
            <header>
              <h3>
                {device.name} · {device.platform}
              </h3>
              <Link to="/app/devices">Manage</Link>
            </header>
            <p>
              VPN {device.vpnEnabled ? 'on' : 'off'} · Antivirus{' '}
              {device.antivirusEnabled ? 'on' : 'off'} · Updates{' '}
              {device.updatesCurrent ? 'current' : 'behind'}
            </p>
          </article>
        ))}
      </section>
    </div>
  )
}
