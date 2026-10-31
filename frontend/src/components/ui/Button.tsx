import type { ButtonHTMLAttributes } from "react"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger"
  isLoading?: boolean
}

const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary: "bg-amber-500 text-neutral-950 hover:bg-amber-400 disabled:bg-amber-500/40",
  secondary: "bg-neutral-800 text-neutral-100 hover:bg-neutral-700 disabled:bg-neutral-800/40",
  danger: "bg-rose-600 text-white hover:bg-rose-500 disabled:bg-rose-600/40",
}

export function Button({ variant = "primary", isLoading = false, className = "", children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      className={`inline-flex min-w-32 items-center justify-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed ${variantClasses[variant]} ${className}`}
      disabled={disabled ?? isLoading}
      {...rest}
    >
      {isLoading && (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />
      )}
      {children}
    </button>
  )
}
