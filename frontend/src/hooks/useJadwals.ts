import { useEffect, useState } from "react"
import type { Jadwal } from "../types"
import { fetchJadwals } from "../services/api"

interface UseJadwalsResult {
  jadwals: Jadwal[] | null
  isLoading: boolean
  error: string | null
}

/** Daftar jadwal (film + jam) dari server; source of truth tayang adalah backend. */
export function useJadwals(): UseJadwalsResult {
  const [jadwals, setJadwals] = useState<Jadwal[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    fetchJadwals()
      .then((list) => {
        if (active) setJadwals(list)
      })
      .catch((err: Error) => {
        if (active) setError(err.message)
      })
    return () => {
      active = false
    }
  }, [])

  return { jadwals, isLoading: jadwals === null && error === null, error }
}
