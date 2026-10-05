import hashlib
import hmac
import re
import tempfile
import unittest
from pathlib import Path

import db
from app import app


class BookingCsrfTests(unittest.TestCase):
    def setUp(self):
        self.database_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.database_dir.name) / "officehours.db"
        self.client = app.test_client()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.database_dir.cleanup()

    def login(self, email, password):
        response = self.client.post("/login", data={"email": email, "password": password})
        self.assertEqual(response.status_code, 302)

    def booking_owner(self, booking_id):
        conn = db.get_db()
        row = conn.execute(
            "SELECT users.email FROM bookings JOIN users ON users.id = bookings.student_id "
            "WHERE bookings.id = ?",
            (booking_id,),
        ).fetchone()
        conn.close()
        return row["email"] if row else None

    def form_token(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(r'name="csrf_token" value="([0-9a-f]+)"', response.text)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_old_get_urls_do_not_change_booking(self):
        self.login("lea@campus.edu", "campus123")
        self.assertEqual(self.client.get("/bookings/1/transfer?email=nico@campus.edu").status_code, 405)
        self.assertEqual(self.client.get("/bookings/1/cancel").status_code, 405)
        self.assertEqual(self.booking_owner(1), "lea@campus.edu")

    def test_missing_or_invalid_csrf_is_rejected(self):
        self.login("lea@campus.edu", "campus123")
        self.assertEqual(
            self.client.post("/bookings/1/transfer", data={"email": "nico@campus.edu"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/bookings/1/cancel", data={"csrf_token": "wrong"}).status_code,
            403,
        )
        self.assertEqual(self.booking_owner(1), "lea@campus.edu")

    def test_legitimate_transfer_and_cancellation(self):
        self.login("lea@campus.edu", "campus123")
        token = self.form_token("/bookings/1")
        response = self.client.post(
            "/bookings/1/transfer",
            data={"email": "nico@campus.edu", "csrf_token": token},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.booking_owner(1), "nico@campus.edu")

        token = self.form_token("/bookings/2")
        response = self.client.post("/bookings/2/cancel", data={"csrf_token": token})
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.booking_owner(2))

    def test_other_users_cannot_modify_booking_with_valid_token(self):
        self.login("nico@campus.edu", "campus123")
        token = self.form_token("/")
        self.assertEqual(
            self.client.post("/bookings/1/cancel", data={"csrf_token": token}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/bookings/1/transfer",
                data={"email": "nico@campus.edu", "csrf_token": token},
            ).status_code,
            403,
        )
        self.assertEqual(self.booking_owner(1), "lea@campus.edu")

    def test_ta_cannot_cancel_a_students_booking(self):
        self.login("ravi@campus.edu", "ta-office")
        session_token = self.client.get_cookie("hold_session").value
        token = hmac.new(
            session_token.encode("ascii"), b"booking-csrf-v1", hashlib.sha256
        ).hexdigest()
        self.assertEqual(
            self.client.post("/bookings/1/cancel", data={"csrf_token": token}).status_code,
            403,
        )
        self.assertEqual(self.booking_owner(1), "lea@campus.edu")

    def test_csrf_token_is_bound_to_session(self):
        self.login("lea@campus.edu", "campus123")
        lea_token = self.form_token("/bookings/1")
        self.client.post("/logout")
        self.login("nico@campus.edu", "campus123")
        self.assertEqual(
            self.client.post("/slots/2/book", data={"csrf_token": lea_token}).status_code,
            403,
        )
        self.assertIsNone(self.booking_owner(3))

    def test_booking_still_works_with_its_form_token(self):
        self.login("nico@campus.edu", "campus123")
        token = self.form_token("/")
        self.assertEqual(self.client.post("/slots/2/book").status_code, 403)
        response = self.client.post("/slots/2/book", data={"csrf_token": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.booking_owner(3), "nico@campus.edu")


if __name__ == "__main__":
    unittest.main()
