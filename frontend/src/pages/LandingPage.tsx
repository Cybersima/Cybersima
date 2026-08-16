import { Link } from 'react-router-dom'
import { useAuth } from '../auth'

export function LandingPage() {
  const { user } = useAuth()

  return (
    <div>
      <header className="hero">
        <div className="hero-media" aria-hidden="true" />
        <nav className="site-nav">
          <div className="brand-mark">Lockwell</div>
          <div className="nav-actions">
            <Link to="/architecture">Architecture</Link>
            {user ? (
              <Link className="btn btn-light" to="/app">
                Open app
              </Link>
            ) : (
              <Link className="btn btn-light" to="/auth">
                Sign in
              </Link>
            )}
          </div>
        </nav>
        <div className="hero-content">
          <h1 className="hero-brand">Lockwell</h1>
          <p className="hero-copy">
            Identity protection built around a vault we cannot read and an audit
            trail you can.
          </p>
          <div className="hero-cta">
            <Link className="btn btn-primary" to={user ? '/app' : '/auth'}>
              {user ? 'Continue to dashboard' : 'Start protected'}
            </Link>
            <Link className="btn btn-ghost" to="/architecture">
              See the security model
            </Link>
          </div>
        </div>
      </header>

      <section className="section">
        <div className="section-narrow">
          <h2>Stronger by design</h2>
          <p className="lead">
            Lockwell focuses on controls most identity apps treat as optional:
            client-side encryption, hashed monitoring, and a transparent action
            history.
          </p>
          <ul className="feature-list">
            <li>
              <h3>Zero-knowledge vault</h3>
              <p>
                Passwords and notes are encrypted in your browser with AES-GCM.
                The API stores ciphertext only.
              </p>
            </li>
            <li>
              <h3>Hashed identity monitoring</h3>
              <p>
                Monitored values are peppered and hashed before storage, with
                masked display values for the dashboard.
              </p>
            </li>
            <li>
              <h3>Device posture + alerts</h3>
              <p>
                Track VPN, antivirus, screen lock, and update status beside
                breach-style alerts in one place.
              </p>
            </li>
            <li>
              <h3>Network Guard at the edge</h3>
              <p>
                A gateway agent watches for scan/flood/bad-actor patterns and can
                drop them before they forward into the home or business LAN.
              </p>
            </li>
          </ul>
        </div>
      </section>
    </div>
  )
}
