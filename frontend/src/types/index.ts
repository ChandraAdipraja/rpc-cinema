export type SeatStatus = "AVAILABLE" | "RESERVED"

export type ReservationStatus = "AKTIF" | "DIBATALKAN"

export interface Seat {
  id: string
  status: SeatStatus
}

export interface Reservation {
  reservation_id: string
  schedule_id: string
  seat_ids: string[]
  status: ReservationStatus
}

export interface BookingResult {
  success: boolean
  message: string
  reservasi?: Reservation
}

export interface Jadwal {
  schedule_id: string
  judul: string
  genre: string
  durasi_menit: number
  jam_tayang: string
}

/** Kumpulan jadwal satu film (sudah digroup). */
export interface FilmGroup {
  filmId: string
  judul: string
  genre: string
  durasiMenit: number
  jadwalList: Jadwal[]
}

export interface ComingSoonFilm {
  title: string
  genre: string
  tagline: string
  releaseMonth: string
  rating: string
}

export interface AdBannerItem {
  headline: string
  subline: string
  voucherCode: string
  emoji: string
}

export interface SeatStreamEvent {
  kursi: {
    id: string
    status: SeatStatus
  }
}
