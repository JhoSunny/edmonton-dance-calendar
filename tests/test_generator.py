import sys
import unittest
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generate_calendar import links_from_index, parse_date_line, parse_event_page, render_ical

class CalendarTests(unittest.TestCase):
    def test_listing(self):
        html = '<p><a href="/en/edmonton/events/salsa-1">Salsa Social</a> 2026-11-20</p><a href="/en/calgary/events/no">No</a>'
        links = links_from_index(html)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][2], date(2026, 11, 20))

    def test_time(self):
        start, end, a, b, unknown = parse_date_line("2026-11-20 · 7:30 PM–9:00 PM")
        self.assertEqual((a.hour, b.hour), (19, 21))
        self.assertFalse(unknown)

    def test_midnight(self):
        _, _, a, b, _ = parse_date_line("2026-11-20 – 2026-11-21 · 9:00 PM–1:00 AM")
        self.assertEqual(b - a, timedelta(hours=4))

    def test_unknown_time(self):
        self.assertTrue(parse_date_line("2026-11-20 · Time TBA")[-1])

    def test_page(self):
        html = '<h1>Social Night</h1><h2>Date and time</h2><p>2026-11-20 · 8:00 PM–11:00 PM</p><h2>Location</h2><p>Dance Hall, Edmonton</p><h2>Cover</h2><p>$10</p><a href="https://example.org">View organizer source ↗</a>'
        ev = parse_event_page(html, "https://dondebailamos.com/en/edmonton/events/social")
        self.assertEqual(ev.title, "Social Night")
        self.assertIn("Dance Hall", ev.location)
        data = render_ical([ev], datetime(2026, 11, 16, tzinfo=timezone.utc))
        self.assertIn(b"DTSTART:20261121T030000Z", data)
        self.assertIn(b"BEGIN:VCALENDAR", data)
        self.assertTrue(all(len(line) <= 75 for line in data.split(b"\r\n")))

if __name__ == "__main__":
    unittest.main()
