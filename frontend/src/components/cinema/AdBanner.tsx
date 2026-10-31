import type { AdBannerItem } from "../../types"

/** Banner iklan voucher kinos (statis). */
export function AdBanner({ ad }: { ad: AdBannerItem }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-dashed border-amber-500/40 bg-amber-500/5 p-4">
      <span className="text-3xl" aria-hidden>
        {ad.emoji}
      </span>
      <div className="flex-1">
        <p className="text-sm font-bold text-amber-300">{ad.headline}</p>
        <p className="text-xs text-neutral-400">{ad.subline}</p>
      </div>
      <span className="rounded-lg bg-amber-500/20 px-3 py-2 text-xs font-mono font-bold tracking-wider text-amber-200">
        {ad.voucherCode}
      </span>
    </div>
  )
}
