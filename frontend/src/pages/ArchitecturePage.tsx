import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

export function ArchitecturePage() {
  const [principles, setPrinciples] = useState<string[]>([])
  const [limits, setLimits] = useState<string[]>([])

  useEffect(() => {
    api
      .architecture()
      .then((res) => {
        setPrinciples(res.principles)
        setLimits(res.mvpLimits)
      })
      .catch(() => {
        setPrinciples([
          'Zero-knowledge vault: encryption keys never leave the browser',
          'Hashed monitoring: raw identity values are not stored in plaintext',
          'Transparent audit trail for every sensitive account action',
          'Least privilege API tokens scoped to a single session',
          'Defense-in-depth device posture scoring',
          'Network Guard sits on the edge gateway to drop hostile packets before LAN forward',
        ])
        setLimits([
          'Breach and dark-web alerts are simulated for the demo corpus',
          'Credit bureau feeds and insurance require licensed partners',
          'Device antivirus/VPN toggles are posture controls, not full endpoint agents',
          'True packet blocking requires deploying the agent on a gateway/firewall host',
          'Demo mode uses synthetic packet metadata; enforce mode needs nftables privileges',
        ])
      })
  }, [])

  return (
    <div className="arch-page">
      <div className="panel wide">
        <Link to="/" className="brand-mark">
          Lockwell
        </Link>
        <h1>Security architecture</h1>
        <p>
          How Lockwell aims to be stricter than typical identity-protection
          dashboards—especially around vault secrecy and accountability.
        </p>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem' }}>
          Design principles
        </h2>
        <ul className="feature-list">
          {principles.map((item) => (
            <li key={item}>
              <p>{item}</p>
            </li>
          ))}
        </ul>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem' }}>
          Honest MVP limits
        </h2>
        <ul className="feature-list">
          {limits.map((item) => (
            <li key={item}>
              <p>{item}</p>
            </li>
          ))}
        </ul>
        <div style={{ marginTop: '1.25rem' }}>
          <Link className="btn btn-primary" to="/auth">
            Try the demo
          </Link>
        </div>
      </div>
    </div>
  )
}
