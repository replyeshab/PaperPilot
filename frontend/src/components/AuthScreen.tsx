import { useState, type FormEvent } from 'react'
import { LoaderCircle, Sparkles } from 'lucide-react'
import { api, type AuthResult } from '../services/api'

type Props = { onAuthenticated: (result: AuthResult) => void; notice?: string }

export function AuthScreen({ onAuthenticated, notice }: Props) {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const result = mode === 'signup' ? await api.signup(email.trim(), password) : await api.login(email.trim(), password)
      onAuthenticated(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const isSignup = mode === 'signup'
  return (
    <main className="auth">
      <section className="auth-card" aria-labelledby="auth-title">
        <div className="brand-mark auth-mark" aria-hidden="true"><Sparkles size={18} strokeWidth={2.3} /></div>
        <h1 id="auth-title">{isSignup ? 'Create your account' : 'Welcome back'}</h1>
        <p className="auth-lede">
          {isSignup ? 'Your conversations and library are saved to your account.' : 'Sign in to pick up where you left off.'}
        </p>

        {(error || notice) && <div className="inline-error" role="alert">{error || notice}</div>}

        <form onSubmit={submit} className="auth-form">
          <label htmlFor="auth-email">Email</label>
          <input id="auth-email" type="email" autoComplete="email" required value={email}
            onChange={event => setEmail(event.target.value)} disabled={busy} />

          <label htmlFor="auth-password">Password</label>
          <input id="auth-password" type="password" required minLength={isSignup ? 8 : 1}
            autoComplete={isSignup ? 'new-password' : 'current-password'} value={password}
            onChange={event => setPassword(event.target.value)} disabled={busy} />
          {isSignup && <small className="field-hint">At least 8 characters.</small>}

          <button className="btn btn-primary auth-submit" type="submit" disabled={busy || !email || !password}>
            {busy && <LoaderCircle size={15} className="spin" />}
            {isSignup ? 'Create account' : 'Sign in'}
          </button>
        </form>

        <button className="link-button auth-switch" onClick={() => { setMode(isSignup ? 'signin' : 'signup'); setError('') }}>
          {isSignup ? 'Already have an account? Sign in' : 'New here? Create an account'}
        </button>
      </section>
    </main>
  )
}
