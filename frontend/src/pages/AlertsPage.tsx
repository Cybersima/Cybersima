import { useEffect, useState } from 'react'
import { api, type Alert } from '../lib/api'

export function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [error, setError] = useState('')

  async function load() {
    const res = await api.alerts()
    setAlerts(res.alerts)
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message))
  }, [])

  async function acknowledge(id: number) {
    await api.ackAlert(id)
    await load()
  }

  return (
    <div>
      <h1 className="page-title">Alerts</h1>
      <p className="page-sub">
        Breach, exposure, and device signals. Demo feeds are simulated; production
        would plug into licensed monitoring partners.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="stack">
        {alerts.map((alert) => (
          <article key={alert.id} className="list-row">
            <header>
              <h3>{alert.title}</h3>
              <span className={`badge ${alert.severity}`}>{alert.severity}</span>
            </header>
            <p>{alert.detail}</p>
            <p>
              {alert.source} · {new Date(alert.createdAt).toLocaleString()}
              {alert.acknowledged ? ' · acknowledged' : ''}
            </p>
            {!alert.acknowledged && (
              <div>
                <button className="btn btn-ghost" onClick={() => void acknowledge(alert.id)}>
                  Acknowledge
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  )
}
