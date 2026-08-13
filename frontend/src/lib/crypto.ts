const textEncoder = new TextEncoder()
const textDecoder = new TextDecoder()

function bufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  bytes.forEach((b) => {
    binary += String.fromCharCode(b)
  })
  return btoa(binary)
}

function base64ToBuffer(value: string): ArrayBuffer {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes.buffer
}

async function deriveKey(passphrase: string, saltHex: string): Promise<CryptoKey> {
  const salt = new Uint8Array(saltHex.match(/.{1,2}/g)!.map((byte) => parseInt(byte, 16)))
  const material = await crypto.subtle.importKey(
    'raw',
    textEncoder.encode(passphrase),
    'PBKDF2',
    false,
    ['deriveKey'],
  )
  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt,
      iterations: 210_000,
      hash: 'SHA-256',
    },
    material,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

export type VaultSecret = {
  title: string
  secret: string
  notes?: string
}

export async function encryptSecret(
  passphrase: string,
  saltHex: string,
  payload: VaultSecret,
): Promise<{ ciphertext: string; iv: string }> {
  const key = await deriveKey(passphrase, saltHex)
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const encrypted = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    textEncoder.encode(JSON.stringify(payload)),
  )
  return {
    ciphertext: bufferToBase64(encrypted),
    iv: bufferToBase64(iv.buffer),
  }
}

export async function decryptSecret(
  passphrase: string,
  saltHex: string,
  ciphertext: string,
  iv: string,
): Promise<VaultSecret> {
  const key = await deriveKey(passphrase, saltHex)
  const decrypted = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: new Uint8Array(base64ToBuffer(iv)) },
    key,
    base64ToBuffer(ciphertext),
  )
  return JSON.parse(textDecoder.decode(decrypted)) as VaultSecret
}
