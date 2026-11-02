import { useCallback, useEffect, useRef, useState } from "react"
import type { Reservation } from "../types"
import { ApiError, NetworkError, cancelReservation, fetchReservation } from "../services/api"
import { newRequestId } from "../services/requestId"

interface UseReservationResult {
  reservation: Reservation | null
  isLoading: boolean
  error: string | null
  notFound: boolean
  cancelling: boolean
  cancel: () => Promise<void>
  /** true bila hasil pembatalan belum diketahui (network error); retry memakai request_id yang sama. */
  unknownCancelResult: boolean
}

export function useReservation(reservationId: string | undefined): UseReservationResult {
  const [reservation, setReservation] = useState<Reservation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [cancelling, setCancelling] = useState(false)

  /**
   * Identitas tindakan pembatalan yang belum selesai (request_id idempotency):
   * - Cancel baru -> request_id baru.
   * - Retry setelah network error -> request_id SAMA (hasilnya belum diketahui).
   * - Respons HTTP definitif (sukses maupun gagal) -> identity dibuang.
   * Ref agar re-render TIDAK membuat request_id baru.
   */
  const pendingCancelIdRef = useRef<string | null>(null)
  const [unknownCancelResult, setUnknownCancelResult] = useState(false)

  useEffect(() => {
    if (!reservationId) return
    let active = true
    setReservation(null)
    setNotFound(false)
    setError(null)
    // Reservasi berbeda = konteks pembatalan berbeda; identity lama tidak relevan.
    pendingCancelIdRef.current = null
    setUnknownCancelResult(false)

    fetchReservation(reservationId)
      .then((data) => {
        if (active) setReservation(data)
      })
      .catch((err: Error) => {
        if (!active) return
        if (err instanceof ApiError && err.message.startsWith("Reservasi tidak ditemukan")) {
          setNotFound(true)
        } else {
          setError(err.message)
        }
      })

    return () => {
      active = false
    }
  }, [reservationId])

  const cancel = useCallback(async () => {
    if (!reservationId || cancelling) return
    setCancelling(true)
    setError(null)
    // Tindakan pembatalan BARU -> request_id baru, tepat satu per tindakan.
    // Retry hasil-unknown TIDAK membuat ID baru.
    if (!pendingCancelIdRef.current) {
      pendingCancelIdRef.current = newRequestId()
    }
    const requestId = pendingCancelIdRef.current
    try {
      const updated = await cancelReservation(reservationId, requestId)
      // Tindakan selesai; pembatalan berikutnya memakai request_id baru.
      pendingCancelIdRef.current = null
      setUnknownCancelResult(false)
      setReservation(updated)
    } catch (err) {
      if (err instanceof NetworkError) {
        // Hasil TIDAK diketahui -> pertahankan identity agar tombol cancel
        // mengulang dengan request_id yang sama.
        setUnknownCancelResult(true)
        setError(err.message)
      } else {
        // Respons HTTP definitif (mis. 404 sudah tidak ada) -> tindakan berakhir;
        // click berikutnya dianggap pembatalan baru dengan request_id baru.
        pendingCancelIdRef.current = null
        setUnknownCancelResult(false)
        setError((err as Error).message)
      }
    } finally {
      setCancelling(false)
    }
  }, [reservationId, cancelling])

  return { reservation, isLoading: reservation === null && !error && !notFound, error, notFound, cancelling, cancel, unknownCancelResult }
}
