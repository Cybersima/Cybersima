import { useEffect, useState, type FormEvent } from 'react'
import { api, type MonitoredItem } from '../lib/api'

export function MonitorPage() {
  const [items, setItems] = useState<MonitoredItem[]>([])
  const [kind, setKind] = useState('email')
  const [label, setLabel] = useState('')
  const [value, setValue] = useState('')
  const [error, setError] = useState('')

  async function load() {
    const res = await api.monitored()
    setItems(res.items)
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message))
  }, [])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      await api.addMonitored({ kind, label, value })
      setLabel('')
      setValue('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add item')
    }
  }

  return (
    <div>
      <h1 className="page-title">Identity monitoring</h1>
      <p className="page-sub">
        Values are hashed with a server pepper before storage. The UI only shows a
        mask, never the original secret again.
      </p>

      <form className="form-stack panel" onSubmit={onSubmit}>
        <label>
          Type
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="email">Email</option>
            <option value="phone">Phone</option>
            <option value="card">Card</option>
            <option value="ssn">SSN</option>
            <option value="bank">Bank</option>
            <option value="passport">Passport</option>
            <option value="license">License</option>
          </select>
        </label>
        <label>
          Label
          <input value={label} onChange={(e) => setLabel(e.target.value)} required />
        </label>
        <label>
          Value
          <input value={value} onChange={(e) => setValue(e.target.value)} required />
        </label>
        <button className="btn btn-primary" type="submit">
          Add monitor
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      <div className="stack" style={{ marginTop: '1.5rem' }}>
        {items.map((item) => (
          <article key={item.id} className="list-row">
            <header>
              <h3>
                {item.label} · {item.kind}
              </h3>
              <span className="badge low">{item.status}</span>
            </header>
            <p>{item.displayMask}</p>
          </article>
        ))}
      </div>
    </div>
  )
}
