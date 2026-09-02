import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthProvider, useAuth } from '../context/AuthContext'

// Mock the whole api module — these tests are about AuthContext's own
// logic (what it does with the responses), not about axios or the
// network. Each test configures the mocked functions' return values.
vi.mock('../api', () => ({
  getMe: vi.fn(),
  loginUser: vi.fn(),
  registerUser: vi.fn(),
  logoutUser: vi.fn(),
  refreshSession: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  setCsrfToken: vi.fn(),
  clearCsrfToken: vi.fn(),
}))

import {
  getMe, loginUser, logoutUser, refreshSession,
  setAccessToken, clearAccessToken, setCsrfToken, clearCsrfToken,
} from '../api'

// A minimal consumer component that exposes AuthContext's state/actions
// as text/buttons, so tests can assert on rendered output rather than
// reaching into React internals.
function Probe() {
  const { user, loading, login, logout } = useAuth()
  if (loading) return <div>loading</div>
  return (
    <div>
      <div>{user ? `logged in as ${user.email}` : 'logged out'}</div>
      <button onClick={() => login('test@acme.com', 'password123')}>do-login</button>
      <button onClick={() => logout().catch(() => {})}>do-logout</button>
    </div>
  )
}

function renderWithProvider() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AuthContext — silent refresh on mount', () => {
  it('logs the user in automatically when a valid refresh cookie exists', async () => {
    refreshSession.mockResolvedValue({ data: { access_token: 'at-1', csrf_token: 'csrf-1' } })
    getMe.mockResolvedValue({ data: { email: 'returning@acme.com' } })

    renderWithProvider()

    expect(screen.getByText('loading')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('logged in as returning@acme.com')).toBeInTheDocument()
    })

    expect(setAccessToken).toHaveBeenCalledWith('at-1')
    expect(setCsrfToken).toHaveBeenCalledWith('csrf-1')
  })

  it('shows logged-out state and clears tokens when there is no valid session', async () => {
    // This mirrors the real 403 a fresh browser gets from /api/auth/refresh
    // (Phase 1) — refreshSession rejects, and the app should recover
    // gracefully into a logged-out state rather than get stuck loading.
    refreshSession.mockRejectedValue({ response: { status: 403 } })

    renderWithProvider()

    await waitFor(() => {
      expect(screen.getByText('logged out')).toBeInTheDocument()
    })

    expect(clearAccessToken).toHaveBeenCalled()
    expect(clearCsrfToken).toHaveBeenCalled()
  })
})

describe('AuthContext — login', () => {
  it('stores the access token and CSRF token, then loads the user', async () => {
    refreshSession.mockRejectedValue({ response: { status: 403 } })
    loginUser.mockResolvedValue({ data: { access_token: 'at-2', csrf_token: 'csrf-2' } })
    getMe.mockResolvedValue({ data: { email: 'test@acme.com' } })

    renderWithProvider()
    await waitFor(() => expect(screen.getByText('logged out')).toBeInTheDocument())

    await userEvent.click(screen.getByText('do-login'))

    await waitFor(() => {
      expect(screen.getByText('logged in as test@acme.com')).toBeInTheDocument()
    })
    expect(setAccessToken).toHaveBeenCalledWith('at-2')
    expect(setCsrfToken).toHaveBeenCalledWith('csrf-2')
  })
})

describe('AuthContext — logout', () => {
  it('clears both tokens and the user even if the logout request fails', async () => {
    // Mirrors app/routers/auth.py's logout endpoint requiring a valid
    // CSRF header (Phase 1) — if that request somehow fails, the
    // frontend should still clear local state rather than leave the UI
    // showing a "logged in" user who can no longer do anything.
    refreshSession.mockResolvedValue({ data: { access_token: 'at-3', csrf_token: 'csrf-3' } })
    getMe.mockResolvedValue({ data: { email: 'test@acme.com' } })
    logoutUser.mockRejectedValue(new Error('network error'))

    renderWithProvider()
    await waitFor(() => expect(screen.getByText('logged in as test@acme.com')).toBeInTheDocument())

    await act(async () => {
      await userEvent.click(screen.getByText('do-logout'))
    })

    await waitFor(() => {
      expect(screen.getByText('logged out')).toBeInTheDocument()
    })
    expect(clearAccessToken).toHaveBeenCalled()
    expect(clearCsrfToken).toHaveBeenCalled()
  })
})
