interface SeatGridProps {
  seats: { id: string; status: string }[]
  selectedSeatIds: string[]
  onToggle: (seatId: string) => void
}

export function SeatLegend() {
  const items = [
    { label: "Tersedia", className: "border-amber-500/60 bg-amber-500/10" },
    { label: "Pilihan kamu", className: "border-emerald-400 bg-emerald-500/30" },
    { label: "Terisi", className: "border-neutral-700 bg-neutral-800" },
  ]
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-neutral-400">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-2">
          <span className={`h-4 w-4 rounded ${item.className}`} aria-hidden />
          {item.label}
        </span>
      ))}
    </div>
  )
}

export function SeatGrid({ seats, selectedSeatIds, onToggle }: SeatGridProps) {
  const rows = Array.from(new Set(seats.map((seat) => seat.id[0]))).sort()

  return (
    <div className="flex flex-col items-center gap-6">
      {/* Layar studio */}
      <div className="w-full max-w-sm">
        <div className="h-2 rounded-full bg-gradient-to-r from-transparent via-amber-400/80 to-transparent" />
        <p className="mt-2 text-center text-xs tracking-[0.4em] text-neutral-500">LAYAR</p>
      </div>

      <div className="w-full overflow-x-auto">
        <div className="mx-auto flex w-fit flex-col gap-2.5">
          {rows.map((row) => (
            <div key={row} className="flex items-center gap-2.5">
              <span className="w-5 text-center text-xs font-semibold text-neutral-500" aria-hidden>
                {row}
              </span>
              {seats
                .filter((seat) => seat.id[0] === row)
                .map((seat) => {
                  const isSelected = selectedSeatIds.includes(seat.id)
                  const isAvailable = seat.status === "AVAILABLE"
                  return (
                    <button
                      key={seat.id}
                      type="button"
                      disabled={!isAvailable}
                      onClick={() => onToggle(seat.id)}
                      title={`${seat.id} — ${isAvailable ? "Tersedia" : "Terisi"}`}
                      aria-label={`Kursi ${seat.id}, ${isAvailable ? "tersedia" : "terisi"}`}
                      aria-pressed={isSelected}
                      className={`h-10 w-10 rounded-lg border text-xs font-semibold transition-colors ${
                        isSelected
                          ? "border-emerald-400 bg-emerald-500/30 text-emerald-100 ring-2 ring-emerald-400/50"
                          : isAvailable
                            ? "border-amber-500/60 bg-amber-500/10 text-amber-200 hover:bg-amber-500/25"
                            : "cursor-not-allowed border-neutral-700 bg-neutral-800 text-neutral-600"
                      }`}
                    >
                      {seat.id.slice(1)}
                    </button>
                  )
                })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
