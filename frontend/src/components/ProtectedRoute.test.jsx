import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ProtectedRoute from './ProtectedRoute'

// ProtectedRoute's entire job is reading useAuth() and deciding what to
// render — mock the hook directly rather than the whole AuthContext
// module, so each test can control { user, loading } precisely.
const mockUseAuth = vi.fn()
vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

function renderProtected() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route path="/login" element={<div>login page</div>} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <div>secret dashboard content</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>
  )
}

describe('ProtectedRoute', () => {
  it('shows a loading state while auth is still resolving', () => {
    mockUseAuth.mockReturnValue({ user: null, loading: true })
    renderProtected()
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
    expect(screen.queryByText('secret dashboard content')).not.toBeInTheDocument()
  })

  it('redirects to /login when there is no logged-in user', () => {
    mockUseAuth.mockReturnValue({ user: null, loading: false })
    renderProtected()
    expect(screen.getByText('login page')).toBeInTheDocument()
    expect(screen.queryByText('secret dashboard content')).not.toBeInTheDocument()
  })

  it('renders the protected content when a user is logged in', () => {
    mockUseAuth.mockReturnValue({ user: { email: 'test@acme.com' }, loading: false })
    renderProtected()
    expect(screen.getByText('secret dashboard content')).toBeInTheDocument()
  })
})
