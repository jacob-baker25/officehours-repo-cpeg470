import os
import re
import unittest

from app import app
from db import get_db


@unittest.skipUnless(
    os.environ.get("RUN_POSTGRES_SMOKE_TEST") == "1" and os.environ.get("DATABASE_URL"),
    "requires a disposable Postgres database",
)
class PostgresSmokeTests(unittest.TestCase):
    def test_registration_booking_transfer_and_cancellation(self):
        student = app.test_client()
        self.assertEqual(student.get("/health").status_code, 200)
        self.assertEqual(
            student.post(
                "/register",
                data={
                    "email": "test@campus.edu",
                    "display_name": "Test Student",
                    "password": "test-password",
                },
            ).status_code,
            302,
        )

        token = re.search(
            r'name="csrf_token" value="([0-9a-f]+)"', student.get("/").text
        ).group(1)
        self.assertEqual(
            student.post("/slots/2/book", data={"csrf_token": token}).status_code,
            302,
        )
        conn = get_db()
        booking_id = conn.execute("SELECT id FROM bookings WHERE slot_id = ?", (2,)).fetchone()["id"]
        conn.close()

        token = re.search(
            r'name="csrf_token" value="([0-9a-f]+)"',
            student.get(f"/bookings/{booking_id}").text,
        ).group(1)
        self.assertEqual(
            student.post(
                f"/bookings/{booking_id}/transfer",
                data={"email": "nico@campus.edu", "csrf_token": token},
            ).status_code,
            302,
        )

        recipient = app.test_client()
        self.assertEqual(
            recipient.post(
                "/login", data={"email": "nico@campus.edu", "password": "campus123"}
            ).status_code,
            302,
        )
        token = re.search(
            r'name="csrf_token" value="([0-9a-f]+)"',
            recipient.get(f"/bookings/{booking_id}").text,
        ).group(1)
        self.assertEqual(
            recipient.post(
                f"/bookings/{booking_id}/cancel", data={"csrf_token": token}
            ).status_code,
            302,
        )
        conn = get_db()
        self.assertIsNone(
            conn.execute("SELECT id FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
