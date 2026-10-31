import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { BookingPage } from "./BookingPage"
import { reserveSeats } from "../services/api"

vi.mock("../hooks/useJadwals", () => ({
  useJadwals: () => ({
    jadwals: [
      { schedule_id: "jadwal-1", judul: "Gerhana Sunyi", genre: "Drama", durasi_menit: 108, jam_tayang: "10:30" },
      { schedule_id: "jadwal-2", judul: "Gerhana Sunyi", genre: "Drama", durasi_menit: 108, jam_tayang: "19:00" },
    ],
    isLoading: false,
    error: null,
  }),
}))

vi.mock("../hooks/useSeats", () => ({
  useSeats: () => ({
    seats: [
      { id: "A1", status: "AVAILABLE" },
      { id: "A2", status: "AVAILABLE" },
      { id: "B1", status: "AVAILABLE" },
    ],
    isLoading: false,
    error: null,
  }),
}))

vi.mock("../services/api", async () => ({
  reserveSeats: vi.fn(),
}))

const mockReserve = vi.mocked(reserveSeats)
const UUID_V4_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

const idsOfCalls = () =>
  mockReserve.mock.calls.map(([scheduleId, seatIds, requestId]) => ({ scheduleId, seatIds, requestId }))

const renderPage = () =>
  render(
    <MemoryRouter>
      <BookingPage />
    </MemoryRouter>,
  )

const seatButton = (id: string) => screen.getByRole("button", { name: new RegExp(`Kursi ${id},`) })
const reserveButton = () => screen.getByRole("button", { name: /Reservasi Sekarang|Coba Lagi/ })

beforeEach(() => {
  mockReserve.mockReset()
})

describe("BookingPage request_id (idempotency)", () => {
  it("tindakan booking pertama mengirim request_id UUID + payload", async () => {
    const user = userEvent.setup()
    mockReserve.mockResolvedValue({ success: false, message: "Kursi A1 sudah dipesan" })

    renderPage()
    await user.click(seatButton("A1"))
    await user.click(reserveButton())

    await waitFor(() => expect(mockReserve).toHaveBeenCalledTimes(1))
    expect(idsOfCalls()[0]).toEqual({
      scheduleId: "jadwal-1",
      seatIds: ["A1"],
      requestId: expect.stringMatching(UUID_V4_RE),
    })
  })

  it("retry setelah network error pakai request_id & payload YANG SAMA", async () => {
    const user = userEvent.setup()
    mockReserve
      .mockResolvedValue({ success: false, message: "Gateway tidak dapat dijangkau", unknownResult: true })

    renderPage()
    await user.click(seatButton("A1"))
    await user.click(reserveButton())
    // Tindakan hasil-unknown: tombol berganti label "Coba Lagi"
    await screen.findByRole("button", { name: "Coba Lagi" })
    await user.click(screen.getByRole("button", { name: "Coba Lagi" }))

    await waitFor(() => expect(mockReserve).toHaveBeenCalledTimes(2))
    const call1 = idsOfCalls()[0]
    const call2 = idsOfCalls()[1]
    expect(call2.requestId).toBe(call1.requestId)
    expect(call2.seatIds).toEqual(call1.seatIds)
    expect(call2.scheduleId).toBe(call1.scheduleId)
  })

  it("respons definitif (409) -> klik berikutnya = tindakan baru = request_id BARU", async () => {
    const user = userEvent.setup()
    mockReserve.mockResolvedValue({ success: false, message: "Kursi A1 sudah dipesan" })

    renderPage()
    await user.click(seatButton("A1"))
    await user.click(reserveButton())
    await waitFor(() => expect(mockReserve).toHaveBeenCalledTimes(1))
    // Setelah 409 tampil, user mencoba lagi (belum ada perubahan pilihan)
    await user.click(reserveButton())

    await waitFor(() => expect(mockReserve).toHaveBeenCalledTimes(2))
    const [call1, call2] = idsOfCalls()
    expect(call2.requestId).not.toBe(call1.requestId)
  })

  it("409 tidak memicu retry otomatis dari frontend", async () => {
    const user = userEvent.setup()
    mockReserve.mockResolvedValue({ success: false, message: "Kursi A1 sudah dipesan" })

    renderPage()
    await user.click(seatButton("A1"))
    await user.click(reserveButton())

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy())
    expect(mockReserve).toHaveBeenCalledTimes(1)
  })

  it("payload berubah setelah hasil unknown -> identitas lama dibuang, request_id ganti", async () => {
    const user = userEvent.setup()
    mockReserve.mockResolvedValue({ success: false, message: "Gateway error", unknownResult: true })

    renderPage()
    await user.click(seatButton("A1"))
    await user.click(reserveButton())
    await screen.findByRole("button", { name: "Coba Lagi" })

    // User mengubah pilihan kursi -> bukan tindakan yang sama
    await user.click(seatButton("A2"))
    await user.click(reserveButton())

    await waitFor(() => expect(mockReserve).toHaveBeenCalledTimes(2))
    const [call1, call2] = idsOfCalls()
    expect(call2.requestId).not.toBe(call1.requestId)
    expect(call2.requestId).toMatch(UUID_V4_RE)
    expect(call2.seatIds).toEqual(["A1", "A2"])
  })

  it("re-render tidak membuat request_id baru (pending bertahan)", async () => {
    const user = userEvent.setup()
    mockReserve.mockResolvedValue({ success: false, message: "Gateway error", unknownResult: true })

    const { rerender } = renderPage()
    await user.click(seatButton("A1"))
    await user.click(reserveButton())
    await screen.findByRole("button", { name: "Coba Lagi" })

    rerender(
      <MemoryRouter>
        <BookingPage />
      </MemoryRouter>,
    )
    await user.click(screen.getByRole("button", { name: "Coba Lagi" }))

    await waitFor(() => expect(mockReserve).toHaveBeenCalledTimes(2))
    const id1 = mockReserve.mock.calls[0][2]
    const id2 = mockReserve.mock.calls[1][2]
    expect(id2).toBe(id1)
  })

  it("booking sukses mengirim request_id UUID", async () => {
    const user = userEvent.setup()
    mockReserve.mockResolvedValue({
      success: true,
      message: "Reservasi berhasil",
      reservasi: { reservation_id: "r-1", schedule_id: "jadwal-1", seat_ids: ["A1"], status: "AKTIF" },
    })

    renderPage()
    await user.click(seatButton("A1"))
    await user.click(reserveButton())

    await waitFor(() => expect(mockReserve).toHaveBeenCalledTimes(1))
    expect(mockReserve.mock.calls[0][2]).toMatch(UUID_V4_RE)
  })
})
