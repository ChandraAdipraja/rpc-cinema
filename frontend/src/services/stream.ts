import type { SeatStreamEvent } from "../types"
import { API_URL } from "./api"

/**
 * Berlangganan pembaruan status kursi PER JADWAL via SSE gateway.
 * Return fungsi cleanup untuk berhenti berlangganan.
 */
export function subscribeSeats(
  scheduleId: string,
  onUpdate: (update: { id: string; status: string }) => void,
  onError?: (error: Event) => void,
): () => void {
  const source = new EventSource(`${API_URL}/api/stream/kursi?schedule_id=${encodeURIComponent(scheduleId)}`)
  source.onmessage = (event: MessageEvent<string>) => {
    try {
      const payload = JSON.parse(event.data) as SeatStreamEvent
      onUpdate({ id: payload.kursi.id, status: payload.kursi.status })
    } catch {
      // event tidak valid, abaikan
    }
  }
  if (onError) source.onerror = onError
  return () => source.close()
}
