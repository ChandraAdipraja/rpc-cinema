/**
 * Identitas idempotency client untuk satu tindakan booking/cancellation.
 *
 * Aturan:
 * - Satu tindakan logis = satu request_id (bukan satu klik/percobaan HTTP).
 * - Retry dari tindakan yang sama MEMAKAI ID YANG SAMA; pembuatan ID baru
 *   hanya dilakukan saat mulai tindakan berbeda.
 * - TIDAK memakai Math.random() atau timestamp sebagai pengganti UUID.
 *
 * ID yang dibuat dikirim sebagai field `request_id` pada POST /api/pesan
 * dan POST /api/batal; backend mengikatnya dengan fingerprint SHA-256
 * dari payload, sehingga request identik dengan ID sama dibalas hasil
 * yang sama (cache in-memory, TTL 24 jam).
 *
 * Fallback tidak menurunkan kualitas acak: tetap crypto.getRandomValues
 * (bukan Math.random), hanya formatnya UUIDv4 manual.
 */
export function newRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID()
  }

  if (typeof crypto === "undefined" || typeof crypto.getRandomValues !== "function") {
    throw new Error("Web Crypto tidak tersedia; tidak dapat membuat request_id yang aman")
  }

  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40 // versi 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80 // varian RFC 4122
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
