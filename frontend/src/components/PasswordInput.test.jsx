import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PasswordInput from './PasswordInput'

describe('PasswordInput', () => {
  it('starts masked (type="password")', () => {
    render(<PasswordInput value="secret123" onChange={() => {}} />)
    expect(screen.getByDisplayValue('secret123')).toHaveAttribute('type', 'password')
  })

  it('reveals the password as plain text when the toggle is clicked', async () => {
    render(<PasswordInput value="secret123" onChange={() => {}} />)
    const toggle = screen.getByRole('button', { name: /show password/i })

    await userEvent.click(toggle)

    expect(screen.getByDisplayValue('secret123')).toHaveAttribute('type', 'text')
    expect(screen.getByRole('button', { name: /hide password/i })).toBeInTheDocument()
  })

  it('masks it again when toggled a second time', async () => {
    render(<PasswordInput value="secret123" onChange={() => {}} />)
    const toggle = screen.getByRole('button', { name: /show password/i })

    await userEvent.click(toggle)
    await userEvent.click(screen.getByRole('button', { name: /hide password/i }))

    expect(screen.getByDisplayValue('secret123')).toHaveAttribute('type', 'password')
  })

  it('forwards required/minLength props through to the underlying input', () => {
    render(<PasswordInput value="" onChange={() => {}} required minLength={8} />)
    const input = screen.getByDisplayValue('')
    expect(input).toBeRequired()
    expect(input).toHaveAttribute('minLength', '8')
  })
})
