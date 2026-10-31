export function ErrorAlert({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300"
    >
      {message}
    </div>
  )
}

export function SuccessAlert({ message }: { message: string }) {
  return (
    <div
      role="status"
      className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300"
    >
      {message}
    </div>
  )
}
