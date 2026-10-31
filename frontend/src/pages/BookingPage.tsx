import { useNavigate, useSearchParams } from "react-router-dom"
import { useEffect, useState } from "react"
import type { Jadwal } from "../types"
import { useJadwals } from "../hooks/useJadwals"
import { useSeats } from "../hooks/useSeats"
import { groupJadwalsByFilm, filmIdFromSchedule } from "../services/movies"
import { reserveSeats } from "../services/api"
import { Button } from "../components/ui/Button"
import { Badge } from "../components/ui/Badge"
import { ErrorAlert } from "../components/ui/Alerts"
import { Spinner } from "../components/ui/Spinner"
import { SeatGrid, SeatLegend } from "../components/cinema/SeatGrid"

export function BookingPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { jadwals, isLoading: jadwalLoading, error: jadwalError } = useJadwals()

  // Jadwal aktif: dari query param, fallback ke jadwal pertama.
  const paramSchedule = searchParams.get("schedule")
  const jadwalAktif: Jadwal | null =
    jadwals?.find((jadwal) => jadwal.schedule_id === paramSchedule) ?? jadwals?.[0] ?? null

  // Hanya jam-jam milik film yang dipilih di home — film lain tidak ditampilkan.
  const filmAktif =
    jadwalAktif
      ? (groupJadwalsByFilm(jadwals ?? []).find(
          (film) => film.filmId === filmIdFromSchedule(jadwalAktif.schedule_id),
        ) ?? null)
      : null

  const { seats, isLoading: kursiLoading, error: kursiError } = useSeats(jadwalAktif?.schedule_id ?? null)

  const [selectedSeatIds, setSelectedSeatIds] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Buang pilihan yang kursinya ternyata sudah diambil orang lain (SSE).
  useEffect(() => {
    if (!seats) return
    setSelectedSeatIds((prev) => {
      const tersisa = prev.filter(
        (id) => seats.find((seat) => seat.id === id)?.status === "AVAILABLE",
      )
      return tersisa.length === prev.length ? prev : tersisa
    })
  }, [seats])

  function toggleSeat(seatId: string) {
    setSelectedSeatIds((prev) =>
      prev.includes(seatId) ? prev.filter((id) => id !== seatId) : [...prev, seatId].sort(),
    )
  }

  function selectSchedule(scheduleId: string) {
    if (scheduleId !== paramSchedule) {
      setSearchParams({ schedule: scheduleId }, { replace: true })
      setSubmitError(null)
    }
  }

  async function handleReserve() {
    if (!jadwalAktif || selectedSeatIds.length === 0 || submitting) return
    setSubmitting(true)
    setSubmitError(null)
    const result = await reserveSeats(jadwalAktif.schedule_id, selectedSeatIds)
    setSubmitting(false)
    if (result.success && result.reservasi) {
      navigate(`/reservasi/${result.reservasi.reservation_id}`)
      return
    }
    setSubmitError(result.message)
  }

  if (jadwalLoading) return <Spinner label="Memuat jadwal dari server..." />
  if (jadwalError) return <ErrorAlert message={jadwalError} />
  if (!jadwalAktif) {
    return <ErrorAlert message="Server belum membuka jadwal. Coba muat ulang beberapa saat lagi." />
  }

  const ringkasanKursi =
    selectedSeatIds.length > 0
      ? `${selectedSeatIds.length} kursi: ${selectedSeatIds.join(", ")}`
      : "Pilih satu atau beberapa kursi yang tersedia."

  return (
    <div className="flex flex-col gap-8">
      <header className="rounded-xl border border-neutral-800 bg-neutral-900 p-5">
        <p className="text-xs uppercase tracking-widest text-amber-400">Bioskop Cinema RPC</p>
        <h1 className="mt-1 text-2xl font-bold">{jadwalAktif.judul}</h1>
        <p className="mt-1 text-sm text-neutral-400">
          {jadwalAktif.genre} · {jadwalAktif.durasi_menit} menit · Jam tayang: {jadwalAktif.jam_tayang}
        </p>
      </header>

      <section className="rounded-xl border border-neutral-800 bg-neutral-900 p-5">
        <h2 className="text-lg font-semibold">Pilih Jam Tayang</h2>
        <div className="mt-4 flex flex-wrap gap-2">
          {(filmAktif?.jadwalList ?? []).map((jadwal) => {
            const aktif = jadwal.schedule_id === jadwalAktif.schedule_id
            return (
              <button
                key={jadwal.schedule_id}
                type="button"
                onClick={() => selectSchedule(jadwal.schedule_id)}
                aria-pressed={aktif}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                  aktif
                    ? "bg-amber-500 text-neutral-950"
                    : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                }`}
              >
                {jadwal.jam_tayang}
              </button>
            )
          })}
        </div>
        <p className="mt-3 text-xs text-neutral-500">
          Setiap jadwal punya denah kursi sendiri — reservasi di jadwal lain tidak memengaruhi jadwal ini.
        </p>
      </section>

      <section className="rounded-xl border border-neutral-800 bg-neutral-900 p-5">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold">Denah Kursi</h2>
          <Badge tone="available" />
        </div>

        <div className="mt-6">
          {kursiLoading && <Spinner label="Memuat daftar kursi dari server..." />}
          {kursiError && <ErrorAlert message={kursiError} />}
          {!kursiLoading && !kursiError && seats && (
            <div className="flex flex-col gap-6">
              <SeatGrid
                seats={seats}
                selectedSeatIds={selectedSeatIds}
                onToggle={toggleSeat}
              />
              <SeatLegend />
            </div>
          )}
        </div>
      </section>

      {submitError && <ErrorAlert message={submitError} />}

      <section className="sticky bottom-4 flex flex-col gap-3 rounded-xl border border-neutral-800 bg-neutral-900/95 p-5 backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-neutral-300">{ringkasanKursi}</p>
        <Button onClick={handleReserve} disabled={selectedSeatIds.length === 0} isLoading={submitting}>
          Reservasi Sekarang
        </Button>
      </section>
    </div>
  )
}
