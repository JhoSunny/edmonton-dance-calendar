#!/usr/bin/env python3
"""Generate an unofficial iPhone calendar feed from public Donde Bailamos Edmonton listings."""
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

INDEX_URL = "https://dondebailamos.com/en/edmonton/events"
EVENT_PATH = "/en/edmonton/events/"
OUTPUT = Path(__file__).with_name("edmonton.ics")
LOCAL_TZ = ZoneInfo("America/Edmonton")
DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
TIMELINE = re.compile(r"(20\d{2}-\d{2}-\d{2})(?:\s*[–—-]\s*(20\d{2}-\d{2}-\d{2}))?(?:\s*[·•]\s*(.*))?")
TIMES = re.compile(r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM)?)\s*[–—-]\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM)?)", re.I)
CLOCK = re.compile(r"\d{1,2}(?::\d{2})?\s*(?:AM|PM)", re.I)


@dataclass(frozen=True)
class Event:
    uid: str
    title: str
    url: str
    start_day: date
    end_day: date
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str = ""
    info: str = ""
    organizer_url: str = ""
    unknown_time: bool = False


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": "EdmontonDanceCalendar/1.0 (unofficial public event calendar)",
                      "Accept-Language": "en-CA,en;q=0.8"})
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])))
    return s


def fetch(s, url):
    response = s.get(url, timeout=(10, 22))
    response.raise_for_status()
    return response.text


def links_from_index(html):
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        url = urljoin(INDEX_URL, a["href"]).split("#", 1)[0]
        parts = urlsplit(url)
        if parts.netloc != "dondebailamos.com" or not parts.path.startswith(EVENT_PATH) or len(parts.path) <= len(EVENT_PATH):
            continue
        title = a.get_text(" ", strip=True)
        if not title or title.lower().startswith(("browse ", "calendar", "more events")):
            continue
        context = a.parent.get_text(" ", strip=True) if a.parent else ""
        match = DATE_PATTERN.search(context) or DATE_PATTERN.search(url)
        day = None
        if match:
            try:
                day = date.fromisoformat(match.group(1))
            except ValueError:
                pass
        found[url] = (url, title, day)
    return list(found.values())


def section(tokens, heading, stop):
    for i, t in enumerate(tokens):
        if t.casefold() == heading.casefold():
            collected = []
            for nxt in tokens[i + 1:]:
                if nxt.casefold() in stop or nxt.startswith("Check the organizer"):
                    break
                collected.append(nxt)
                if len(collected) >= 25:
                    break
            return " ".join(collected).strip()
    return ""


def clock_time(raw, other=""):
    raw = raw.strip()
    if not re.search(r"\b(am|pm)\b", raw, re.I):
        suffix = re.search(r"\b(am|pm)\b", other, re.I)
        if suffix:
            raw += " " + suffix.group(1)
        else:
            hhmm = raw if ":" in raw else raw + ":00"
            return datetime.strptime(hhmm, "%H:%M").time()
    return date_parser.parse(raw).time()


def parse_date_line(raw):
    m = TIMELINE.search(" ".join(raw.split()))
    if not m:
        raise ValueError("No dated event")
    start = date.fromisoformat(m.group(1))
    end = date.fromisoformat(m.group(2)) if m.group(2) else start
    if end < start:
        raise ValueError("Invalid event date range")
    times = (m.group(3) or "").strip()
    if not times or re.search(r"\b(TBA|TBD|unknown|not announced)\b", times, re.I):
        return start, end, None, None, True
    span = TIMES.search(times)
    if span:
        a = datetime.combine(start, clock_time(span.group(1), span.group(2)), LOCAL_TZ)
        b = datetime.combine(end, clock_time(span.group(2), span.group(1)), LOCAL_TZ)
        if b <= a:
            b += timedelta(days=1)
        return start, end, a, b, False
    single = CLOCK.search(times)
    if single:
        return start, end, datetime.combine(start, clock_time(single.group()), LOCAL_TZ), None, False
    return start, end, None, None, True


def make_uid(url):
    return hashlib.sha256(unquote(urlsplit(url).path).encode()).hexdigest()[:24] + "@unofficial-edmonton-dance-calendar"


def parse_event_page(html, url, title_hint="", day_hint=None):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "noscript"]):
        tag.decompose()
    h1 = soup.find("h1")
    title = (h1.get_text(" ", strip=True) if h1 else "") or title_hint
    tokens = list(soup.stripped_strings)
    details = section(tokens, "Date and time", {"location", "cover", "view organizer source ↗", "view organizer source"})
    try:
        start, end, a, b, unknown = parse_date_line(details)
    except (ValueError, TypeError):
        if day_hint is None:
            raise
        start = end = day_hint
        a = b = None
        unknown = True
    location = section(tokens, "Location", {"cover", "view organizer source ↗", "view organizer source"})
    info = section(tokens, "Cover", {"view organizer source ↗", "view organizer source"})
    organizer = ""
    for anchor in soup.find_all("a", href=True):
        if "View organizer source" in anchor.get_text(" ", strip=True):
            candidate = urljoin(url, anchor["href"])
            if urlsplit(candidate).scheme in {"http", "https"}:
                organizer = candidate
            break
    return Event(make_uid(url), title, url, start, end, a, b, location, info, organizer, unknown)


def escape(value):
    return (str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n")
            .replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,"))


def fold(line):
    chunks, current, count = [], "", 0
    for char in line:
        length = len(char.encode("utf-8"))
        if count + length > 75:
            chunks.append(current)
            current, count = " ", 1
        current += char
        count += length
    chunks.append(current)
    return "\r\n".join(chunks)


def render_ical(events, now=None):
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//Unofficial Edmonton Dance Calendar//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Edmonton Latin Dance Events",
             "X-WR-CALDESC:Unofficial calendar from Donde Bailamos Edmonton",
             "X-WR-TIMEZONE:America/Edmonton", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
             "X-PUBLISHED-TTL:PT12H"]
    for e in sorted(events, key=lambda v: (v.start_day, v.title)):
        desc = ["Unofficial feed. Confirm event information with the organizer."]
        if e.unknown_time:
            desc.append("Time not available or TBA. Verify the start time before attending.")
        if e.info:
            desc.append("Cover/info: " + e.info)
        desc.append("Event: " + e.url)
        if e.organizer_url:
            desc.append("Organizer: " + e.organizer_url)
        lines.extend(["BEGIN:VEVENT", "UID:" + e.uid, "DTSTAMP:" + stamp,
                      "SUMMARY:" + escape(e.title), "DESCRIPTION:" + escape("\n".join(desc)), "URL:" + e.url])
        if e.location:
            lines.append("LOCATION:" + escape(e.location))
        if e.start_time:
            lines.append("DTSTART:" + e.start_time.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
            if e.end_time:
                lines.append("DTEND:" + e.end_time.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        else:
            lines.append("DTSTART;VALUE=DATE:" + e.start_day.strftime("%Y%m%d"))
            lines.append("DTEND;VALUE=DATE:" + (e.end_day + timedelta(days=1)).strftime("%Y%m%d"))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return ("\r\n".join(fold(x) for x in lines) + "\r\n").encode("utf-8")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    s = session()
    links = links_from_index(fetch(s, INDEX_URL))
    if not links:
        raise RuntimeError("No event links found; preserving prior feed.")
    events, failed = [], 0
    for url, title, day in links:
        try:
            events.append(parse_event_page(fetch(s, url), url, title, day))
        except Exception as exc:
            failed += 1
            logging.warning("Failed %s: %s", url, exc)
            if day:
                events.append(Event(make_uid(url), title, url, day, day, unknown_time=True))
        time.sleep(0.18)
    if not events or failed > len(links) // 2:
        raise RuntimeError(f"Failed {failed}/{len(links)} events; preserving prior feed.")
    OUTPUT.write_bytes(render_ical(events))
    logging.info("Published %d events", len(events))


if __name__ == "__main__":
    main()
