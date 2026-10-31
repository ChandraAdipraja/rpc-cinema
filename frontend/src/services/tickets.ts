const STORAGE_KEY = "cinema-rpc:my-ticket-ids"

/**
 * My Ticket disimpan lokal di perangkat (localStorage). Riwayat reservasi
 * server TIDAK tersimpan lintas restart (state in-memory), jadi list ini
 * hanya menyimpan reservation_id yang pernah dibuat dari browser ini.
 */
export function getTicketIds(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.filter((value): value is string => typeof value === "string")
  } catch {
    return []
  }
}

export function addTicketId(reservationId: string): void {
  const ids = getTicketIds()
  if (ids.includes(reservationId)) return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([reservationId, ...ids]))
  } catch {
    // storage bisa penuh / diblokir mode privat; MyTicketsPage tetap
    // punya jalur input ID manual untuk mengecek tiket.
  }
}
