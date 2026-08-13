import { useEffect, useState, type FormEvent } from 'react'
import { api, type VaultEntry } from '../lib/api'
import { decryptSecret, encryptSecret, type VaultSecret } from '../lib/crypto'

type DecryptedRow = VaultEntry & { plaintext?: VaultSecret; error?: string }

export function VaultPage() {
  const [passphrase, setPassphrase] = useState('')
  const [unlocked, setUnlocked] = useState(false)
  const [salt, setSalt] = useState('')
  const [entries, setEntries] = useState<DecryptedRow[]>([])
  const [title, setTitle] = useState('')
  const [secret, setSecret] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')

  async function refresh(currentPass?: string) {
    const res = await api.vault()
    setSalt(res.vaultSalt)
    if (!currentPass) {
      setEntries(res.entries)
      return
    }
    const decoded = await Promise.all(
      res.entries.map(async (entry) => {
        try {
          const plaintext = await decryptSecret(
            currentPass,
            res.vaultSalt,
            entry.ciphertext,
            entry.iv,
          )
          return { ...entry, plaintext }
        } catch {
          return { ...entry, error: 'Could not decrypt with this passphrase' }
        }
      }),
    )
    setEntries(decoded)
  }

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message))
  }, [])

  async function unlock(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      await refresh(passphrase)
      setUnlocked(true)
      setStatus('Vault unlocked locally. Keys never leave this browser.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unlock failed')
    }
  }

  async function saveSecret(event: FormEvent) {
    event.preventDefault()
    if (!passphrase) return
    setError('')
    try {
      const sealed = await encryptSecret(passphrase, salt, { title, secret, notes })
      await api.saveVault(sealed)
      setTitle('')
      setSecret('')
      setNotes('')
      setStatus('Encrypted entry stored as ciphertext.')
      await refresh(passphrase)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    }
  }

  async function remove(id: number) {
    await api.deleteVault(id)
    await refresh(passphrase || undefined)
  }

  return (
    <div>
      <h1 className="page-title">Zero-knowledge vault</h1>
      <p className="page-sub">
        Encryption uses PBKDF2 + AES-GCM in your browser. Lockwell servers only
        receive ciphertext and IVs.
      </p>

      {!unlocked ? (
        <form className="form-stack panel vault-unlock" onSubmit={unlock}>
          <label>
            Vault passphrase
            <input
              type="password"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              minLength={10}
              required
              placeholder="Separate from your account password"
            />
          </label>
          <button className="btn btn-primary" type="submit">
            Unlock vault
          </button>
        </form>
      ) : (
        <>
          <form className="form-stack panel" onSubmit={saveSecret}>
            <label>
              Title
              <input value={title} onChange={(e) => setTitle(e.target.value)} required />
            </label>
            <label>
              Secret
              <input
                type="password"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                required
              />
            </label>
            <label>
              Notes
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
            </label>
            <button className="btn btn-primary" type="submit">
              Encrypt & store
            </button>
          </form>

          <div className="stack" style={{ marginTop: '1.5rem' }}>
            {entries.map((entry) => (
              <article key={entry.id} className="list-row">
                <header>
                  <h3>{entry.plaintext?.title || `Entry #${entry.id}`}</h3>
                  <button className="btn btn-danger" onClick={() => void remove(entry.id)}>
                    Delete
                  </button>
                </header>
                {entry.plaintext ? (
                  <div className="secret-preview">
                    <div>
                      <strong>Secret:</strong> {entry.plaintext.secret}
                    </div>
                    {entry.plaintext.notes && (
                      <div>
                        <strong>Notes:</strong> {entry.plaintext.notes}
                      </div>
                    )}
                  </div>
                ) : (
                  <p>{entry.error || 'Encrypted blob stored on server'}</p>
                )}
              </article>
            ))}
          </div>
        </>
      )}

      {status && <p style={{ marginTop: '1rem', color: 'var(--ok)' }}>{status}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  )
}
