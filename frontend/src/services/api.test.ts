import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { API_URL, NetworkError, cancelReservation, reserveSeats } from "./api"

/** Response minimal yang dipakai implementasi (ok/status/json) — tidak perlu Response asli. */
const jsonResponse = (content: unknown, ok = true, status = 200) => ({
  ok,
  status,
  json: async () => content,
})

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("reserveSeats", () => {
  it("mengirim request_id bersama schedule_id & seat_ids", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ success: true, message: "Reservasi berhasil", reservasi: [] }),
    )

    await reserveSeats("m-gerhana-1030", ["A1", "A2"], "id-booking-1")

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_URL}/api/pesan`,
      expect.objectContaining({ method: "POST" }),
    )
    const payload = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)
    expect(payload).toEqual({ schedule_id: "m-gerhana-1030", seat_ids: ["A1", "A2"], request_id: "id-booking-1" })
  })

  it("network error dijadikan hasil tidak diketahui (boleh diulang, ID sama)", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"))

    const result = await reserveSeats("m-gerhana-1030", ["A1"], "id-x")

    expect(result.success).toBe(false)
    expect(result.unknownResult).toBe(true)
  })

  it("HTTP 409 respons jelas: bukan hasil tidak diketahui, tanpa retry otomatis", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Kursi A1 sudah dipesan" }, false, 409))

    const result = await reserveSeats("m-gerhana-1030", ["A1"], "id-y")

    expect(result.unknownResult).toBeUndefined()
    expect(result.message).toBe("Kursi A1 sudah dipesan")
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("HTTP 422 (detail array FastAPI) memberi pesan yang dapat dimengerti", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: [{ loc: ["body", "schedule_id"], msg: "Field required" }] }, false, 422),
    )

    const result = await reserveSeats("", ["A1"], "id-z")

    expect(result.message).toContain("HTTP 422")
    expect(result.message).not.toContain("[object Object]")
  })
})

describe("cancelReservation", () => {
  it("mengirim request_id bersama reservation_id", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        success: true,
        message: "Reservasi berhasil dibatalkan",
        reservasi: { reservation_id: "r-1", schedule_id: "s-1", seat_ids: ["A1"], status: "DIBATALKAN" },
      }),
    )

    await cancelReservation("r-1", "id-cancel-1")

    const payload = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)
    expect(payload).toEqual({ reservation_id: "r-1", request_id: "id-cancel-1" })
  })

  it("network error melempar NetworkError (hasil pembatalan TIDAK diketahui)", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"))

    await expect(cancelReservation("r-1", "id-c")).rejects.toBeInstanceOf(NetworkError)
  })

  it("HTTP error respons jelas melempar ApiError bawaan (bukan NetworkError)", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Reservasi r-1 tidak ditemukan" }, false, 404))

    await expect(cancelReservation("r-1", "id-c")).rejects.toMatchObject({
      message: "Reservasi r-1 tidak ditemukan",
    })
  })
})
