import { useEffect, useState } from "react"
import type { Seat } from "../types"
import { fetchSeats } from "../services/api"
import { subscribeSeats } from "../services/stream"

interface UseSeatsResult {
  seats: Seat[] | null
  isLoading: boolean
  error: string | null
}

/**
 * Status kursi satu jadwal: fetch awal + realtime update dari SSE
 * StreamStatusKursi per jadwal. Ganti scheduleId -> reset dan langganan
 * ulang ke stream jadwal yang baru.
 */
export function useSeats(scheduleId: string | null): UseSeatsResult {
  const [seats, setSeats] = useState<Seat[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!scheduleId) {
      setSeats(null)
      setError(null)
      return
    }
    let active = true
    setSeats(null)
    setError(null)

    fetchSeats(scheduleId)
      .then((list) => {
        if (active) setSeats(list)
      })
      .catch((err: Error) => {
        if (active) setError(err.message)
      })

    const unsubscribe = subscribeSeats(
      scheduleId,
      (update) => {
        if (!active) return
        setSeats((prev) =>
          prev?.map((seat) =>
            seat.id === update.id ? { ...seat, status: update.status as Seat["status"] } : seat,
          ) ?? prev,
        )
      },
      () => {
        // EventSource reconnect otomatis; reset error supaya UI mencoba lagi.
        if (active) setError(null)
      },
    )

    return () => {
      active = false
      unsubscribe()
    }
  }, [scheduleId])

  return { seats, isLoading: seats === null && error === null, error }
}
