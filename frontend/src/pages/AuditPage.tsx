import { useEffect, useState } from 'react'
import { api, type AuditEvent } from '../lib/api'

export function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .audit()
      .then((res) => setEvents(res.events))
      .catch((err: Error) => setError(err.message))
  }, [])

  return (
    <div>
      <h1 className="page-title">Audit log</h1>
      <p className="page-sub">
        Every sensitive action is recorded so you can verify what Lockwell did on
        your account.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="stack">
        {events.map((event) => (
          <article key={event.id} className="list-row">
            <header>
              <h3>{event.action}</h3>
              <span>{new Date(event.createdAt).toLocaleString()}</span>
            </header>
            <p>{event.detail}</p>
          </article>
        ))}
      </div>
    </div>
  )
}
