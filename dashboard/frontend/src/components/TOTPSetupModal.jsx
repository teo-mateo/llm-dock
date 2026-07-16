import { useState, useCallback, useEffect, useRef } from 'react'
import { fetchAPI } from '../api'

function TOTPSetupModal({ onClose }) {
  const [step, setStep] = useState('initial')
  const [secret, setSecret] = useState(null)
  const [qrCode, setQrCode] = useState(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const modalRef = useRef(null)

  useEffect(() => {
    checkStatus()
  }, [])

  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const checkStatus = async () => {
    try {
      const data = await fetchAPI('/totp/status')
      if (data.enabled) setStep('enabled')
    } catch { /* non-fatal */ }
  }

  const handleSetup = useCallback(async () => {
    try {
      setBusy(true)
      setError('')
      const data = await fetchAPI('/totp/setup', { method: 'POST' })
      setSecret(data.secret)
      setQrCode(data.qr_code)
      setStep('scan')
    } catch (err) {
      setError(err.message || 'Failed to generate setup data')
    } finally {
      setBusy(false)
    }
  }, [])

  const handleVerify = useCallback(async (e) => {
    e.preventDefault()
    if (code.length !== 6) return
    setBusy(true)
    setError('')
    try {
      await fetchAPI('/totp/verify', {
        method: 'POST',
        body: JSON.stringify({ totp_code: code, totp_secret: secret })
      })
      setStep('enabled')
    } catch (err) {
      setError(err.message || 'Verification failed')
    } finally {
      setBusy(false)
    }
  }, [code, secret])

  const handleDisable = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      await fetchAPI('/totp/disable', { method: 'POST' })
      setStep('initial')
    } catch (err) {
      setError(err.message || 'Failed to disable TOTP')
    } finally {
      setBusy(false)
    }
  }, [])

  const handleClickOutside = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={handleClickOutside}
      ref={modalRef}
    >
      <div className="w-full max-w-md rounded-lg border border-border-strong bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-border-subtle px-6 py-4">
          <h2 className="text-lg font-medium text-fg">
            {step === 'enabled' ? 'Authenticator' : 'Two-Factor Authentication'}
          </h2>
          <button
            onClick={onClose}
            className="text-fg-subtle hover:text-fg-muted transition-colors"
            aria-label="Close"
          >
            <i className="fa-solid fa-xmark text-lg"></i>
          </button>
        </div>

        <div className="px-6 py-5">
          {error && (
            <div className="mb-4 rounded-md border border-danger/30 bg-danger/10 p-3 text-sm text-danger-fg">
              {error}
            </div>
          )}

          {step === 'initial' && (
            <div className="text-center">
              <i className="fa-solid fa-mobile-screen-button mb-4 inline-block text-3xl text-fg-muted"></i>
              <p className="mb-5 text-sm text-fg-muted">
                Add an authenticator app as a secondary login method alongside your
                dashboard token.
              </p>
              <button
                onClick={handleSetup}
                disabled={busy}
                className="rounded-md bg-accent-strong px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? 'Generating...' : 'Set Up Authenticator'}
              </button>
            </div>
          )}

          {step === 'scan' && (
            <div className="text-center">
              <p className="mb-4 text-sm text-fg-muted">
                Scan this QR code with your authenticator app, then enter the 6-digit
                code it shows.
              </p>
              {qrCode && (
                <img
                  src={`data:image/png;base64,${qrCode}`}
                  alt="TOTP QR Code"
                  className="mx-auto mb-4 rounded border border-border-muted"
                  style={{ maxWidth: 200, height: 'auto' }}
                />
              )}
              <form onSubmit={handleVerify}>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  pattern="[0-9]{6}"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="123456"
                  className="mr-2 w-28 rounded-md border border-border-strong bg-app px-3 py-2 text-center text-lg tracking-[0.5em] text-fg placeholder:tracking-normal placeholder:text-fg-subtle focus:border-accent-strong focus:outline-none"
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={busy || code.length !== 6}
                  className="rounded-md bg-accent-strong px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {busy ? 'Verifying...' : 'Verify'}
                </button>
              </form>
            </div>
          )}

          {step === 'enabled' && (
            <div className="text-center">
              <i className="fa-solid fa-circle-check mb-4 inline-block text-3xl text-success-fg"></i>
              <p className="mb-5 text-sm text-fg-muted">
                Your authenticator app is set up. You can now log in with the
                6-digit code from your phone instead of your dashboard token.
              </p>
              <button
                onClick={handleDisable}
                disabled={busy}
                className="rounded-md border border-danger/30 px-4 py-2 text-sm font-medium text-danger-fg hover:bg-danger/10 disabled:opacity-50"
              >
                {busy ? 'Disabling...' : 'Disable Authenticator'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default TOTPSetupModal