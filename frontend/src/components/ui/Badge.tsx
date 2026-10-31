type BadgeTone = "available" | "reserved" | "active" | "cancelled"

const toneClasses: Record<BadgeTone, string> = {
  available: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30",
  reserved: "bg-neutral-700/60 text-neutral-300 ring-1 ring-neutral-600",
  active: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30",
  cancelled: "bg-rose-500/15 text-rose-300 ring-1 ring-rose-500/30",
}

const labels: Record<BadgeTone, string> = {
  available: "Tersedia",
  reserved: "Terisi",
  active: "Aktif",
  cancelled: "Dibatalkan",
}

export function Badge({ tone }: { tone: BadgeTone }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${toneClasses[tone]}`}>
      {labels[tone]}
    </span>
  )
}
