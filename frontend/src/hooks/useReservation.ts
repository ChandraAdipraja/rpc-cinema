import { useCallback, useEffect, useState } from "react"
import type { Reservation } from "../types"
import { ApiError, cancelReservation, fetchReservation } from "../services/api"

interface UseReservationResult {
  reservation: Reservation | null
  isLoading: boolean
  error: string | null
  notFound: boolean
  cancelling: boolean
  cancel: () => Promise<void>
}

export function useReservation(reservationId: string | undefined): UseReservationResult {
  const [reservation, setReservation] = useState<Reservation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [cancelling, setCancelling] = useState(false)

  useEffect(() => {
    if (!reservationId) return
    let active = true
    setReservation(null)
    setNotFound(false)
    setError(null)

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
    try {
      const updated = await cancelReservation(reservationId)
      setReservation(updated)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setCancelling(false)
    }
  }, [reservationId, cancelling])

  return { reservation, isLoading: reservation === null && !error && !notFound, error, notFound, cancelling, cancel }
}
