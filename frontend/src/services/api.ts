import type { BookingResult, Jadwal, Reservation, Seat } from "../types"

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

export class ApiError extends Error {}

/**
 * Network error: request mungkin sudah dieksekusi backend atau belum —
 * HASIL TIDAK DIKETAHUI. Caller boleh mengulang dengan request_id yang sama
 * (idempotency), TIDAK dengan request_id baru.
 */
export class NetworkError extends ApiError {}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    // FastAPI 422 mengirim detail sebagai array; tampilkan pesan yang dakamati,
    // bukan "[object Object]".
    if (response.status === 422 && body.detail) {
      return "Data yang dikirim tidak valid (HTTP 422). Muat ulang halaman, lalu coba lagi."
    }
    if (typeof body.detail === "string" && body.detail) return body.detail
  } catch {
    // body bukan JSON, pakai status text
  }
  return `Gagal memanggil gateway (HTTP ${response.status})`
}

export async function fetchJadwals(): Promise<Jadwal[]> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/api/jadwal`)
  } catch {
    throw new ApiError("Gateway tidak dapat dijangkau. Pastikan server & gateway berjalan.")
  }
  if (!response.ok) throw new ApiError(await parseErrorDetail(response))
  return (await response.json()) as Jadwal[]
}

export async function fetchSeats(scheduleId: string): Promise<Seat[]> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/api/kursi?schedule_id=${encodeURIComponent(scheduleId)}`)
  } catch {
    throw new ApiError("Gateway tidak dapat dijangkau. Pastikan server & gateway berjalan.")
  }
  if (!response.ok) throw new ApiError(await parseErrorDetail(response))
  return (await response.json()) as Seat[]
}

/**
 * Reservasi kursi. `requestId` WAJIB berasal dari identitas tindakan
 * booking (lihat callers) — bukan UUID yang dibuat baru setiap HTTP attempt;
 * retry tindakan yang sama memakai requestId + payload yang sama.
 */
export async function reserveSeats(
  scheduleId: string,
  seatIds: string[],
  requestId: string,
): Promise<BookingResult> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/api/pesan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schedule_id: scheduleId, seat_ids: seatIds, request_id: requestId }),
    })
  } catch {
    return {
      success: false,
      message: "Gateway tidak dapat dijangkau. Coba lagi sebentar.",
      unknownResult: true,
    }
  }
  if (!response.ok) {
    return { success: false, message: await parseErrorDetail(response) }
  }
  return (await response.json()) as BookingResult
}

export async function fetchReservation(reservationId: string): Promise<Reservation> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/api/pesanan/${encodeURIComponent(reservationId)}`)
  } catch {
    throw new ApiError("Gateway tidak dapat dijangkau. Pastikan server & gateway berjalan.")
  }
  if (!response.ok) {
    if (response.status === 404) {
      throw new ApiError("Reservasi tidak ditemukan. Periksa kembali ID reservasi.")
    }
    throw new ApiError(await parseErrorDetail(response))
  }
  return (await response.json()) as Reservation
}

/**
 * Batalkan reservasi. `requestId` berasal dari identitas tindakan pembatalan;
 * retry yang hasilnya belum diketahui memakai requestId yang sama.
 */
export async function cancelReservation(reservationId: string, requestId: string): Promise<Reservation> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/api/batal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reservation_id: reservationId, request_id: requestId }),
    })
  } catch {
    throw new NetworkError("Gateway tidak dapat dijangkau. Hasil pembatalan belum diketahui — coba lagi sebentar.")
  }
  if (!response.ok) throw new ApiError(await parseErrorDetail(response))
  const body = (await response.json()) as { reservasi: Reservation }
  return body.reservasi
}
