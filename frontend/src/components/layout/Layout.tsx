import { NavLink } from "react-router-dom"
import type { ReactNode } from "react"

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 bg-neutral-900/70 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
          <NavLink to="/" className="flex items-center gap-2 text-lg font-bold tracking-tight">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-amber-500 text-neutral-950" aria-hidden>
              C
            </span>
            Cinema<span className="text-amber-400">RPC</span>
          </NavLink>
          <nav className="flex items-center gap-1 text-sm">
            <NavLink
              to="/"
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 transition-colors ${isActive ? "bg-amber-500/15 text-amber-300" : "text-neutral-300 hover:bg-neutral-800"}`
              }
            >
              Beranda
            </NavLink>
            <NavLink
              to="/tiket-saya"
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 transition-colors ${isActive ? "bg-amber-500/15 text-amber-300" : "text-neutral-300 hover:bg-neutral-800"}`
              }
            >
              Tiket Saya
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">{children}</main>
      <footer className="border-t border-neutral-800 py-6 text-center text-xs text-neutral-500">
        Mini-project RPC — Reservasi via gRPC + FastAPI Gateway
      </footer>
    </div>
  )
}
