import { Route, BrowserRouter as Router, Routes } from "react-router-dom"
import { Layout } from "./components/layout/Layout"
import { HomePage } from "./pages/HomePage"
import { BookingPage } from "./pages/BookingPage"
import { ReservationPage } from "./pages/ReservationPage"
import { MyTicketsPage } from "./pages/MyTicketsPage"

export default function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/booking" element={<BookingPage />} />
          <Route path="/reservasi/:reservationId" element={<ReservationPage />} />
          <Route path="/tiket-saya" element={<MyTicketsPage />} />
        </Routes>
      </Layout>
    </Router>
  )
}
