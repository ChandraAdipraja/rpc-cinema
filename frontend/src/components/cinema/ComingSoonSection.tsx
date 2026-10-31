import { COMING_SOON } from "../../services/movies"

/** Section Segera Tayang: film yang belum ada jadwalnya di server. */
export function ComingSoonSection() {
  return (
    <section className="flex flex-col gap-5">
      <div>
        <h2 className="text-xl font-bold">Segera Tayang</h2>
        <p className="text-xs text-neutral-500">Jadwal pembukaan reservasi akan diumumkan.</p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {COMING_SOON.map((film) => (
          <article
            key={film.title}
            className="flex flex-col gap-2 rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 opacity-90"
          >
            <div className="flex items-center justify-between">
              <span className="rounded-md bg-neutral-800 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-neutral-400">
                Segera
              </span>
              <span className="text-xs text-neutral-500">{film.rating}</span>
            </div>
            <h3 className="mt-2 font-semibold text-neutral-100">{film.title}</h3>
            <p className="text-xs text-neutral-400">{film.genre}</p>
            <p className="text-xs leading-relaxed text-neutral-500">{film.tagline}</p>
            <p className="mt-auto pt-3 text-xs font-semibold text-amber-300">{film.releaseMonth}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
