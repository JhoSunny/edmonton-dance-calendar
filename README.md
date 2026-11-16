# Edmonton Latin Dance Calendar (unofficial)

An unofficial auto-updating iCalendar feed for Edmonton events listed publicly at [Donde Bailamos](https://dondebailamos.com/en/edmonton/events). This project is not affiliated with Donde Bailamos.

## Subscribe with iPhone Calendar

**Feed:** https://jhosunny.github.io/edmonton-dance-calendar/edmonton.ics

The feed link works **only after** GitHub Pages is enabled and the first successful update creates `edmonton.ics`.

1. On GitHub, open **Settings → Pages**. Under **Build and deployment**, choose **Deploy from a branch**, branch **main**, folder **/(root)**, and save.
2. Open **Actions → Refresh Edmonton dance events → Run workflow** to generate the feed if the initial push did not run.
3. When the run succeeds, confirm the feed URL above serves `BEGIN:VCALENDAR` text.
4. On iPhone, open **Calendar → Calendars → Add Calendar → Add Subscription Calendar**, paste the URL, and confirm.

## Updates

GitHub Actions runs at approximately 01:17 and 13:17 UTC each day, which is twice daily in Edmonton. It fetches public Edmonton event pages and generates an `.ics` feed with titles, times, venues and links. Stable event IDs avoid duplicate entries when details change. It uses Alberta local time for conversion to UTC. If event time is missing, the event appears as all-day with a warning. Events removed from the source listing also disappear from the next successful feed.

If the scraper fails, the workflow does not overwrite the previous good feed. GitHub Actions schedules are approximate, and Apple independently controls when it refreshes subscriptions. A site layout change or rate limit might require a code update. Check the **Actions** tab for errors.

## Tests

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python generate_calendar.py
```

No account permissions or tokens from Donde Bailamos are needed. This repository and its feed are public. Do not add personal information.
