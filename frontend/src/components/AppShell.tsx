import { NavLink } from 'react-router-dom'
import { useAuth } from '../auth'

const links = [
  { to: '/app', label: 'Overview', end: true },
  { to: '/app/alerts', label: 'Alerts' },
  { to: '/app/vault', label: 'Vault' },
  { to: '/app/monitor', label: 'Monitoring' },
  { to: '/app/devices', label: 'Devices' },
  { to: '/app/audit', label: 'Audit log' },
]

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()

  return (
    <div className="app-shell">
      <aside className="side-nav">
        <div className="brand-mark">Lockwell</div>
        <div style={{ color: 'var(--ink-soft)', fontSize: '0.92rem' }}>
          {user?.displayName}
        </div>
        <nav>
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end}>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <button className="btn btn-ghost logout" onClick={() => void logout()}>
          Sign out
        </button>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  )
}
