import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { AppShell } from './components/AppShell'
import { AlertsPage } from './pages/AlertsPage'
import { ArchitecturePage } from './pages/ArchitecturePage'
import { AuditPage } from './pages/AuditPage'
import { AuthPage } from './pages/AuthPage'
import { DashboardPage } from './pages/DashboardPage'
import { DevicesPage } from './pages/DevicesPage'
import { LandingPage } from './pages/LandingPage'
import { MonitorPage } from './pages/MonitorPage'
import { NetworkGuardPage } from './pages/NetworkGuardPage'
import { VaultPage } from './pages/VaultPage'

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="loading-screen">Opening Lockwell…</div>
  if (!user) return <Navigate to="/auth" replace />
  return <AppShell>{children}</AppShell>
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/auth" element={<AuthPage />} />
      <Route path="/architecture" element={<ArchitecturePage />} />
      <Route
        path="/app"
        element={
          <Protected>
            <DashboardPage />
          </Protected>
        }
      />
      <Route
        path="/app/alerts"
        element={
          <Protected>
            <AlertsPage />
          </Protected>
        }
      />
      <Route
        path="/app/vault"
        element={
          <Protected>
            <VaultPage />
          </Protected>
        }
      />
      <Route
        path="/app/monitor"
        element={
          <Protected>
            <MonitorPage />
          </Protected>
        }
      />
      <Route
        path="/app/devices"
        element={
          <Protected>
            <DevicesPage />
          </Protected>
        }
      />
      <Route
        path="/app/network"
        element={
          <Protected>
            <NetworkGuardPage />
          </Protected>
        }
      />
      <Route
        path="/app/audit"
        element={
          <Protected>
            <AuditPage />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
