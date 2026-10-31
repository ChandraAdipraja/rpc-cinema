import { Link, useParams } from "react-router-dom"
import { useEffect, useState } from "react"
import type { Jadwal } from "../types"
import { useReservation } from "../hooks/useReservation"
import { fetchJadwals } from "../services/api"
import { addTicketId } from "../services/tickets"
import { Button } from "../components/ui/Button"
import { Badge } from "../components/ui/Badge"
import { ErrorAlert } from "../components/ui/Alerts"
import { Spinner } from "../components/ui/Spinner"

export function ReservationPage() {
  const { reservationId } = useParams<{ reservationId: string }>()
  const { reservation, isLoading, error, notFound, cancelling, cancel } = useReservation(reservationId)
  const [jadwalList, setJadwalList] = useState<Jadwal[] | null>(null)

  useEffect(() => {
    let active = true
    fetchJadwals()
      .then((list) => {
        if (active) setJadwalList(list)
      })
      .catch(() => {
        // Jadwal adalah kosmetik; kalau gagal lewati saja.
        if (active) setJadwalList([])
      })
    return () => {
      active = false
    }
  }, [])

  // Simpan tiket ke My Ticket (localStorage perangkat ini).
  useEffect(() => {
    if (reservation?.status === "AKTIF" && reservation.reservation_id) {
      addTicketId(reservation.reservation_id)
    }
  }, [reservation])

  if (isLoading) return <Spinner label="Memuat detail reservasi..." />
  if (notFound) {
    return (
      <div className="flex flex-col gap-4">
        <ErrorAlert message="Reservasi tidak ditemukan atau sudah terhapus (data server bersifat in-memory dan hilang saat server restart)." />
        <Link to="/tiket-saya" className="text-sm font-semibold text-amber-400 hover:text-amber-300">
          ← Lihat tiket saya
        </Link>
      </div>
    )
  }

  const jadwal: Jadwal | null | undefined = reservation
    ? jadwalList?.find((item) => item.schedule_id === reservation.schedule_id) ?? null
    : null
  const labelJadwal = jadwal ? `${jadwal.judul} — ${jadwal.jam_tayang}` : "Jadwal (tidak dikenal di server)"

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold">Detail Reservasi</h1>
        <p className="mt-1 text-sm text-neutral-400">Data ini diambil langsung dari gRPC server.</p>
      </header>

      {error && <ErrorAlert message={error} />}

      {reservation && (
        <section className="rounded-xl border border-neutral-800 bg-neutral-900 p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">
              {labelJadwal} <span className="text-sm font-normal text-neutral-500">— tiket kamu</span>
            </h2>
            <Badge tone={reservation.status === "AKTIF" ? "active" : "cancelled"} />
          </div>

          <dl className="mt-5 grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
              <dt className="text-xs uppercase tracking-wider text-neutral-500">ID Reservasi</dt>
              <dd className="mt-1 break-all font-mono text-sm text-amber-300">{reservation.reservation_id}</dd>
            </div>
            <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
              <dt className="text-xs uppercase tracking-wider text-neutral-500">
                Kursi ({reservation.seat_ids.length})
              </dt>
              <dd className="mt-1 text-xl font-bold text-neutral-100">{reservation.seat_ids.join(", ")}</dd>
            </div>
            <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
              <dt className="text-xs uppercase tracking-wider text-neutral-500">Status</dt>
              <dd className="mt-1 text-sm text-neutral-300">{reservation.status}</dd>
            </div>
          </dl>

          {reservation.status === "AKTIF" ? (
            <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-emerald-300">Reservasi berhasil — semua kursi terkunci untukmu.</p>
              <div className="flex gap-3">
                <Link to="/booking">
                  <Button variant="secondary">Pesan lagi</Button>
                </Link>
                <Button variant="danger" onClick={() => void cancel()} isLoading={cancelling}>
                  Batalkan Pesanan
                </Button>
              </div>
            </div>
          ) : (
            <p className="mt-6 text-sm text-neutral-300">
              Pesanan sudah dibatalkan. Kursi <span className="font-bold">{reservation.seat_ids.join(", ")}</span>{" "}
              bisa dipesan orang lain kembali.
            </p>
          )}
        </section>
      )}

      <Link to="/tiket-saya" className="text-sm font-semibold text-neutral-400 hover:text-amber-300">
        ← Kembali ke Tiket Saya
      </Link>
    </div>
  )
}
