import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

/**
 * Drop-in replacement for <input type="password" ...> with a show/hide
 * toggle. Accepts the same props (value, onChange, required, minLength,
 * etc.) and forwards anything else via ...rest, so existing call sites
 * only need their <input> swapped for <PasswordInput>, same props.
 */
export default function PasswordInput({ className, ...rest }) {
  const [visible, setVisible] = useState(false)

  return (
    <div className="relative">
      <input
        type={visible ? 'text' : 'password'}
        className={
          className ||
          'w-full border border-black/10 rounded-lg pl-3 pr-10 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-signal'
        }
        {...rest}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        tabIndex={-1}
        aria-label={visible ? 'Hide password' : 'Show password'}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  )
}
