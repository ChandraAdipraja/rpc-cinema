import type { AdBannerItem, ComingSoonFilm, FilmGroup, Jadwal } from "../types"

/**
 * ID film = bagian schedule_id sebelum "-<jam>" (mis. "m-gerhana-1030" -> "m-gerhana").
 * Jadwal selalu dari server; frontend TIDAK menyimpan katalog tayang sendiri.
 */
export function filmIdFromSchedule(scheduleId: string): string {
  const index = scheduleId.lastIndexOf("-")
  return index > 0 ? scheduleId.slice(0, index) : scheduleId
}

/** Kelompokkan daftar jadwal per film untuk ditampilkan di Home & Booking. */
export function groupJadwalsByFilm(jadwals: Jadwal[]): FilmGroup[] {
  const map = new Map<string, FilmGroup>()
  for (const jadwal of jadwals) {
    const filmId = filmIdFromSchedule(jadwal.schedule_id)
    const group = map.get(filmId)
    if (group) {
      group.jadwalList.push(jadwal)
    } else {
      map.set(filmId, {
        filmId,
        judul: jadwal.judul,
        genre: jadwal.genre,
        durasiMenit: jadwal.durasi_menit,
        jadwalList: [jadwal],
      })
    }
  }
  return [...map.values()].map((group) => ({
    ...group,
    jadwalList: [...group.jadwalList].sort((a, b) => a.jam_tayang.localeCompare(b.jam_tayang)),
  }))
}

/** Film yang belum jadi tayang di server (untuk section Segera Tayang). */
export const COMING_SOON: ComingSoonFilm[] = [
  {
    title: "Solaris Line",
    genre: "Drama Misteri",
    tagline: "Operator stasiun benua terakhir menerima transmisi dari kereta yang sudah lama hilang.",
    releaseMonth: "Desember 2026",
    rating: "13+",
  },
  {
    title: "Nasi Bungkus Bandung",
    genre: "Komedi Keluarga",
    tagline: "Warung nasi keliling keluarga Anggara menantang lomba masak se-busway raya.",
    releaseMonth: "Januari 2027",
    rating: "SU",
  },
  {
    title: "Lumbung Langit",
    genre: "Animasi Keluarga",
    tagline: "Gudang padi versi peta bermata api yang terdesak pengembangan kota.",
    releaseMonth: "Februari 2027",
    rating: "SU",
  },
]

/** Iklan voucher (static, cuman buat kosmetik home page). */
export const AD_BANNERS: AdBannerItem[] = [
  {
    headline: "Voucher Snack 25%",
    subline: "Berlaku untuk paket popcorn + softdrink",
    voucherCode: "KINOS25",
    emoji: "🍿",
  },
  {
    headline: "Diskon Member 20%",
    subline: "Berlaku untuk pembelian tiket ke-3 dan seterusnya",
    voucherCode: "CINEMA20",
    emoji: "🎫",
  },
  {
    headline: "Cashback E-Wallet 15%",
    subline: "Pembayaran via aplikasi e-wallet rekanan",
    voucherCode: "PAYGO15",
    emoji: "💳",
  },
]
