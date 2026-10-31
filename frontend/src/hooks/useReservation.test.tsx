import { beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook, waitFor, act } from "@testing-library/react"
import { useReservation } from "./useReservation"
import { ApiError, NetworkError, cancelReservation, fetchReservation } from "../services/api"

vi.mock("../services/api", async (importActual) => {
  // Kelas Error asli agar instanceof NetworkError/ApiError tetap bekerja.
  const actual = await importActual<typeof import("../services/api")>()
  return {
    ...actual,
    cancelReservation: vi.fn(),
    fetchReservation: vi.fn(),
  }
})

const mockCancel = vi.mocked(cancelReservation)
const mockFetchReservation = vi.mocked(fetchReservation)
const UUID_V4_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

const RESERVASI: import("../types").Reservation = {
  reservation_id: "r-1",
  schedule_id: "jadwal-1",
  seat_ids: ["A1"],
  status: "AKTIF",
}

const RESERVASI_BATAL: import("../types").Reservation = { ...RESERVASI, status: "DIBATALKAN" }

beforeEach(() => {
  mockCancel.mockReset()
  mockFetchReservation.mockReset()
  mockFetchReservation.mockResolvedValue(RESERVASI)
})

describe("useReservation request_id (idempotency pembatalan)", () => {
  it("pembatalan mengirim request_id UUID bersama reservation_id", async () => {
    mockCancel.mockResolvedValue(RESERVASI_BATAL)
    const { result } = renderHook(() => useReservation("r-1"))
    await waitFor(() => expect(result.current.reservation).not.toBeNull())

    await act(async () => result.current.cancel())

    expect(mockCancel).toHaveBeenCalledWith("r-1", expect.stringMatching(UUID_V4_RE))
  })

  it("retry setelah network error memakai request_id YANG SAMA", async () => {
    mockCancel.mockRejectedValueOnce(new NetworkError("Gateway tidak dapat dijangkau"))
    mockCancel.mockResolvedValueOnce(RESERVASI_BATAL)

    const { result } = renderHook(() => useReservation("r-1"))
    await waitFor(() => expect(result.current.reservation).not.toBeNull())

    await act(async () => result.current.cancel())
    // Hasil belum diketahui -> identity dipertahankan untuk retry
    expect(result.current.unknownCancelResult).toBe(true)
    const firstId = mockCancel.mock.calls[0][1]

    await act(async () => result.current.cancel())

    expect(mockCancel).toHaveBeenCalledTimes(2)
    expect(mockCancel.mock.calls[1][1]).toBe(firstId)
    // Retry berhasil
    expect(result.current.reservation?.status).toBe("DIBATALKAN")
    expect(result.current.unknownCancelResult).toBe(false)
  })

  it("dua pembatalan tindakan berbeda (setelah sukses) memakai request_id BERBEDA", async () => {
    mockCancel.mockResolvedValue(RESERVASI_BATAL)

    const { result } = renderHook(() => useReservation("r-1"))
    await waitFor(() => expect(result.current.reservation).not.toBeNull())

    await act(async () => result.current.cancel())
    const firstId = mockCancel.mock.calls[0][1]

    // Tindakan pembatalan baru (state di-restart oleh UI, identity sudah dibuang)
    await act(async () => result.current.cancel())

    expect(mockCancel).toHaveBeenCalledTimes(2)
    expect(mockCancel.mock.calls[1][1]).not.toBe(firstId)
  })

  it("error HTTP definitif -> identity dibuang, cancel berikutnya memakai request_id baru", async () => {
    mockCancel.mockRejectedValueOnce(new ApiError("Reservasi r-1 tidak ditemukan"))
    mockCancel.mockRejectedValueOnce(new ApiError("Reservasi r-1 tidak ditemukan"))

    const { result } = renderHook(() => useReservation("r-1"))
    await waitFor(() => expect(result.current.reservation).not.toBeNull())

    await act(async () => result.current.cancel())
    expect(result.current.unknownCancelResult).toBe(false)
    const firstId = mockCancel.mock.calls[0][1]

    await act(async () => result.current.cancel())
    expect(mockCancel.mock.calls[1][1]).not.toBe(firstId)
  })

  it("ganti reservationId me-reset konteks pembatalan", async () => {
    mockCancel.mockResolvedValue(RESERVASI_BATAL)

    const { result, rerender } = renderHook(({ id }) => useReservation(id), {
      initialProps: { id: "r-1" },
    })
    await waitFor(() => expect(result.current.reservation).not.toBeNull())

    await act(async () => result.current.cancel())
    const firstId = mockCancel.mock.calls[0][1]

    rerender({ id: "r-2" })
    await waitFor(() => expect(mockFetchReservation).toHaveBeenCalledWith("r-2"))
    await act(async () => result.current.cancel())

    // Konteks reservasi berbeda = tindakan berbeda = request_id baru
    expect(mockCancel.mock.calls[1][0]).toBe("r-2")
    expect(mockCancel.mock.calls[1][1]).not.toBe(firstId)
  })
})
