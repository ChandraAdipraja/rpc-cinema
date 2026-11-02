import { afterEach, describe, expect, it, vi } from "vitest"
import { newRequestId } from "./requestId"

const UUID_V4_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

/**
 * Jangan pakai Math.random sebagai pengganti UUID: kalau implementasi menyentuh
 * Math.random, panggilan ini melempar dan test gagal.
 */
const forbidMathRandom = () =>
  vi.spyOn(Math, "random").mockImplementation(() => {
    throw new Error("request_id tidak boleh dibuat dari Math.random")
  })

afterEach(() => {
  vi.restoreAllMocks()
})

describe("newRequestId", () => {
  it("menghasilkan UUID v4 yang valid", () => {
    expect(newRequestId()).toMatch(UUID_V4_RE)
  })

  it("dua panggilan menghasilkan ID berbeda", () => {
    expect(newRequestId()).not.toBe(newRequestId())
  })

  it("tidak menggunakan Math.random / timestamp", () => {
    const spy = forbidMathRandom()
    expect(newRequestId()).toMatch(UUID_V4_RE)
    expect(spy).not.toHaveBeenCalled()
  })

  it("fallback tanpa crypto.randomUUID menganut UUID v4 dari crypto.getRandomValues", () => {
    // Sembunyikan crypto.randomUUID: definisikan di instansi sehingga
    // implementation helper harus memakai crypto.getRandomValues.
    const cryptoAny = globalThis.crypto as unknown as { randomUUID?: unknown }
    const hadOwn = Object.prototype.hasOwnProperty.call(cryptoAny, "randomUUID")
    const original = (globalThis.crypto as Crypto).randomUUID

    Object.defineProperty(globalThis.crypto, "randomUUID", {
      value: undefined,
      configurable: true,
      writable: true,
    })
    try {
      const id = newRequestId()
      expect(id).toMatch(UUID_V4_RE)
    } finally {
      if (hadOwn) {
        Object.defineProperty(globalThis.crypto, "randomUUID", {
          value: original,
          configurable: true,
          writable: true,
        })
      } else {
        delete cryptoAny.randomUUID
      }
    }
  })
})
