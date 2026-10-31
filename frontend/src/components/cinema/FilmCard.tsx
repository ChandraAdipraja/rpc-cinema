import { Link } from "react-router-dom"
import type { FilmGroup } from "../../types"

/** Kartu film dari data jadwal server: judul/genre/durasi + chip jam tayang. */
export function FilmCard({ film }: { film: FilmGroup }) {
  return (
    <article className="flex flex-col overflow-hidden rounded-xl border border-neutral-800 bg-neutral-900 transition-colors hover:border-amber-500/40">
      <div className="flex h-36 items-center justify-center bg-gradient-to-br from-amber-500/25 via-neutral-900 to-neutral-900">
        <span className="text-4xl" aria-hidden>
          🎬
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div>
          <h3 className="font-semibold text-neutral-100">{film.judul}</h3>
          <p className="text-xs text-neutral-400">
            {film.genre} · {film.durasiMenit} menit
          </p>
        </div>
        <ul className="flex flex-wrap gap-1.5" aria-label="Jadwal tayang">
          {film.jadwalList.map((jadwal) => (
            <li key={jadwal.schedule_id}>
              <Link
                to={`/booking?schedule=${encodeURIComponent(jadwal.schedule_id)}`}
                className="block rounded-md bg-neutral-800 px-2 py-1 text-xs text-neutral-300 transition-colors hover:bg-amber-500 hover:text-neutral-950"
              >
                {jadwal.jam_tayang}
              </Link>
            </li>
          ))}
        </ul>
        <Link
          to={`/booking?schedule=${encodeURIComponent(film.jadwalList[0]?.schedule_id ?? "")}`}
          className="mt-auto inline-flex items-center justify-center rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-neutral-950 transition-colors hover:bg-amber-400"
        >
          Pesan Kursi
        </Link>
      </div>
    </article>
  )
}
