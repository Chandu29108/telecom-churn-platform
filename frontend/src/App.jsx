import { Routes, Route } from 'react-router-dom'
import { useState } from 'react'
import Sidebar from './components/Sidebar'
import ProtectedRoute from './components/ProtectedRoute'
import CopilotChat from './components/CopilotChat'
import { AnalysisProvider } from './context/AnalysisContext'
import { AuthProvider, useAuth } from './context/AuthContext'
import { resendVerification } from './api'
import Home from './pages/Home'
import UploadPage from './pages/Upload'
import Dashboard from './pages/Dashboard'
import Insights from './pages/Insights'
import Recommendations from './pages/Recommendations'
import Prediction from './pages/Prediction'
import Login from './pages/Login'
import RegisterChoice from './pages/RegisterChoice'
import RegisterPersonal from './pages/RegisterPersonal'
import RegisterOrganization from './pages/RegisterOrganization'
import Team from './pages/Team'
import VerifyEmail from './pages/VerifyEmail'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'

function UnverifiedBanner() {
  const { user } = useAuth()
  const [sent, setSent] = useState(false)
  if (!user || user.is_verified) return null

  const resend = async () => {
    await resendVerification(user.email)
    setSent(true)
  }

  return (
    <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-xs px-6 py-2 flex items-center justify-between">
      <span>Please verify your email address ({user.email}) to secure your account.</span>
      {sent ? (
        <span className="font-medium">Verification email sent.</span>
      ) : (
        <button onClick={resend} className="font-medium underline underline-offset-2">
          Resend verification email
        </button>
      )}
    </div>
  )
}

function AppLayout() {
  return (
    <ProtectedRoute>
      <div className="flex min-h-screen flex-col">
        <UnverifiedBanner />
        <div className="flex flex-1">
          <Sidebar />
          <main className="flex-1 px-8 py-8 max-w-6xl">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/insights" element={<Insights />} />
              <Route path="/recommendations" element={<Recommendations />} />
              <Route path="/prediction" element={<Prediction />} />
              <Route path="/team" element={<Team />} />
            </Routes>
          </main>
          <CopilotChat />
        </div>
      </div>
    </ProtectedRoute>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AnalysisProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<RegisterChoice />} />
          <Route path="/register/personal" element={<RegisterPersonal />} />
          <Route path="/register/organization" element={<RegisterOrganization />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/*" element={<AppLayout />} />
        </Routes>
      </AnalysisProvider>
    </AuthProvider>
  )
}
