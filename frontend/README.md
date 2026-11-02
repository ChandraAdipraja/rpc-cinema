# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Idempotency: `request_id` Frontend (POST /api/pesan & POST /api/batal)

Setiap tindakan booking atau pembatalan membawa `request_id` (UUID) yang dibuat di frontend:

- **Frontend menghasilkan `request_id`** untuk setiap tindakan baru — `crypto.randomUUID()` (fallback: `crypto.getRandomValues`) di `src/services/requestId.ts`. Bukan `Math.random()`, bukan timestamp.
- **Satu ID per satu tindakan** — identitas disimpan di `useRef`/state komponen (`BookingPage` untuk booking, hook `useReservation` untuk cancel), sehingga re-render React tidak membuat ID baru.
- **Retry memakai ID yang sama** — bila hasil operasi tidak diketahui (network error, `unknownResult: true` / `NetworkError`), tombol retry mengulang dengan `request_id` + payload yang sama. Tindakan yang sama, identitas yang sama.
- **Tindakan baru memakai ID baru** — setelah respons definitif (sukses, 409, 422, dll.) identity dibuang; klik berikutnya dianggap tindakan logis baru dengan ID baru.
- **Backend menangani deduplikasi** — request dengan `(request_id, fingerprint payload)` yang sama dibalas hasil sebelumnya; ID yang sama dengan payload berbeda ditolak HTTP 409.
- **409 tidak diulang otomatis** — 409 bisa berarti konflik kursi ATAU payload mismatch; detail pesan gateway ditampilkan, user yang memutuskan langkah berikutnya.

Keterbatasan: identitas retry hanya hidup selama sesi halaman (state/ref, tanpa sessionStorage). Backend cache idempotency juga in-memory dengan TTL 24 jam dan LRU — request_id tidak menjamin persistensi data reservasi setelah server restart.

