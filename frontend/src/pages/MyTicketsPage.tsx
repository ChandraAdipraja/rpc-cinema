import { Link } from "react-router-dom"
import { useCallback, useEffect, useState } from "react"
import type { Jadwal, Reservation } from "../types"
import { ApiError, fetchJadwals, fetchReservation } from "../services/api"
import { getTicketIds } from "../services/tickets"
import { Button } from "../components/ui/Button"
import { Badge } from "../components/ui/Badge"
import { ErrorAlert } from "../components/ui/Alerts"
import { Spinner } from "../components/ui/Spinner"

type TicketEntry =
  | { kind: "ok"; key: string; reservation: Reservation; jadwal: Jadwal | null }
  | { kind: "hilang"; key: string; reservationId: string }
  | { kind: "error"; key: string; reservationId: string; message: string }

export function MyTicketsPage() {
  const [entries, setEntries] = useState<TicketEntry[] | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const ids = getTicketIds()
    let active = true

    if (ids.length === 0) {
      setEntries([])
      return
    }

    // Ambil sekali daftar jadwal untuk label; gagal = label generik saja.
    fetchJadwals()
      .catch(() => [] as Jadwal[])
      .then((jadwalList) =>
        Promise.all(
          ids.map(async (id) => {
            const tryFetch = async () => {
              const reservation = await fetchReservation(id)
              const jadwal = jadwalList.find((item) => item.schedule_id === reservation.schedule_id) ?? null
              return { kind: "ok", key: id, reservation, jadwal } as TicketEntry
            }
            const fallback = async (err: Error) => {
              if (err instanceof ApiError && err.message.startsWith("Reservasi tidak ditemukan")) {
                return { kind: "hilang", key: id, reservationId: id } as TicketEntry
              }
              return { kind: "error", key: id, reservationId: id, message: err.message } as TicketEntry
            }
            try {
              return await tryFetch()
            } catch (err) {
              return await fallback(err as Error)
            }
          }),
        ),
      )
      .then((result) => {
        if (active) setEntries(result)
      })

    return () => {
      active = false
    }
  }, [reloadKey])

  const periksaUlang = useCallback(() => {
    setEntries(null)
    setReloadKey((n) => n + 1)
  }, [])

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Tiket Saya</h1>
          <p className="mt-1 text-sm text-neutral-400">
            Daftar tiket yang pernah kamu pesan dari perangkat ini. Riwayat di server sifatnya in-memory —
            sesudah server restart tiket jadi "hilang".
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={periksaUlang} disabled={entries === null}>
            Periksa Ulang
          </Button>
          <Link to="/booking">
            <Button>Pesan Kursi Baru</Button>
          </Link>
        </div>
      </header>

      {entries === null ? (
        <Spinner label="Memuat tiket dari server..." />
      ) : entries.length === 0 ? (
        <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-6 text-sm text-neutral-400">
          <p>Kamu belum menyimpan tiket di perangkat ini.</p>
          <Link
            to="/booking"
            className="mt-2 inline-block text-sm font-semibold text-amber-400 hover:text-amber-300"
          >
            Pesan kursi sekarang →
          </Link>
        </div>
      ) : (
        <section className="flex flex-col gap-3">
          {entries.map((entry) => (
            <TicketCard key={entry.key} entry={entry} />
          ))}
        </section>
      )}
    </div>
  )
}

function TicketCard({ entry }: { entry: TicketEntry }) {
  if (entry.kind === "hilang") {
    return (
      <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4">
        <p className="break-all font-mono text-xs text-neutral-500">{entry.reservationId}</p>
        <p className="mt-2 text-sm text-neutral-400">
          Tiket ini hilang — server sudah restart atau datanya tidak ada di server. ID tetap tersimpan.
        </p>
      </div>
    )
  }
  if (entry.kind === "error") {
    return <ErrorAlert message={`Tiket ${entry.reservationId}: ${entry.message}`} />
  }
  const { reservation, jadwal } = entry
  const aktif = reservation.status === "AKTIF"
  return (
    <article
      className={`rounded-xl border p-4 ${
        aktif ? "border-amber-500/40 bg-neutral-900" : "border-neutral-800 bg-neutral-950 opacity-70"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-neutral-100">
            {jadwal ? `${jadwal.judul} — ${jadwal.jam_tayang}` : "Jadwal tidak dikenal"}
          </h3>
          <p className="mt-0.5 break-all font-mono text-xs text-neutral-500">{reservation.reservation_id}</p>
        </div>
        <Badge tone={aktif ? "active" : "cancelled"} />
      </div>
      <p className="mt-2 font-bold text-amber-300">{reservation.seat_ids.join(", ")}</p>
      <div className="mt-3 flex items-center gap-4">
        <Link
          to={`/reservasi/${encodeURIComponent(reservation.reservation_id)}`}
          className="text-xs font-semibold text-amber-400 hover:text-amber-300"
        >
          Lihat detail →
        </Link>
        {aktif && <span className="text-xs text-neutral-500">Bisa dibatalkan di halaman detail.</span>}
      </div>
    </article>
  )
}
