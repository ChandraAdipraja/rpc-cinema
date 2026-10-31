export function Spinner({ label = "Memuat..." }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-neutral-400">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" aria-hidden />
      {label}
    </div>
  )
}
