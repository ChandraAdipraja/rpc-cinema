import { Link } from "react-router-dom"
import { useJadwals } from "../hooks/useJadwals"
import { groupJadwalsByFilm } from "../services/movies"
import { AD_BANNERS } from "../services/movies"
import { FilmCard } from "../components/cinema/FilmCard"
import { AdBanner } from "../components/cinema/AdBanner"
import { ComingSoonSection } from "../components/cinema/ComingSoonSection"
import { Spinner } from "../components/ui/Spinner"
import { ErrorAlert } from "../components/ui/Alerts"

export function HomePage() {
  const { jadwals, isLoading, error } = useJadwals()
  const filmGroups = jadwals ? groupJadwalsByFilm(jadwals) : []

  return (
    <div className="flex flex-col gap-10">
      <section className="rounded-2xl border border-neutral-800 bg-gradient-to-br from-neutral-900 via-neutral-950 to-neutral-900 p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-amber-400">Distributed Cinema Reservation</p>
        <h1 className="mt-3 max-w-xl text-3xl font-bold leading-tight sm:text-4xl">
          Reservasi tiket bioskop yang <span className="text-amber-400">aman dari tabrakan booking</span>
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-neutral-400">
          Mini-project RPC: frontend React lewat FastAPI Gateway ke gRPC Server. Setiap jadwal (film + jam) punya
          denah kursi sendiri, reservasi bisa beberapa kursi sekaligus, dan saat lintas penonton memilih kursi sama
          maka hanya satu yang berhasil. Ketuk jam tayang di bawah untuk mulai memesan.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to="/booking"
            className="rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-neutral-950 transition-colors hover:bg-amber-400"
          >
            Mulai Pesan
          </Link>
          <Link
            to="/tiket-saya"
            className="rounded-lg border border-neutral-700 px-5 py-2.5 text-sm font-semibold text-neutral-300 transition-colors hover:border-amber-500/40 hover:text-amber-300"
          >
            Tiket Saya
          </Link>
        </div>
      </section>

      <section className="flex flex-col gap-5">
        <div>
          <h2 className="text-xl font-bold">Sedang Tayang</h2>
          <p className="text-xs text-neutral-500">Kursi per jadwal; status denah real-time di halaman pemesanan.</p>
        </div>

        {isLoading && <Spinner label="Memuat jadwal dari server..." />}
        {error && <ErrorAlert message={error} />}
        {!isLoading && !error && jadwals && filmGroups.length === 0 && (
          <p className="rounded-xl border border-neutral-800 bg-neutral-900 p-6 text-sm text-neutral-400">
            Belum ada jadwal yang dibuka server.
          </p>
        )}
        {!error && jadwals && filmGroups.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {filmGroups.map((film) => (
              <FilmCard key={film.filmId} film={film} />
            ))}
          </div>
        )}
      </section>

      <ComingSoonSection />

      <section className="flex flex-col gap-5">
        <div>
          <h2 className="text-xl font-bold">Promo & Voucher</h2>
          <p className="text-xs text-neutral-500">Tampilkan kode di kasir untuk menukarkan promosi.</p>
        </div>
        <div className="flex flex-col gap-3">
          {AD_BANNERS.map((ad) => (
            <AdBanner key={ad.voucherCode} ad={ad} />
          ))}
        </div>
      </section>
    </div>
  )
}
