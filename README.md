# SteveBot Study Feed

Backend "database" for Steve's study app. A new dated folder is published
whenever new Classroom summaries, timetables or study materials are made.

## Layout

```
index.json                  { "latest": "2026-10-03", "updated": "...", "dates": [...] }
2026-10-03/
    study-data.json         homework + announcements + events + materials manifest
    timetable.html          the week's study timetable (open in a WebView)
    materials/*.pdf         key notes, flashcards, mock papers
2026-10-04/
    ...
```

Old date folders are pruned to the most recent 10 to keep the repo lean.

## How the app reads it (no login needed)

```
GET {base}/index.json
→ { "latest": "2026-10-03", ... }

GET {base}/{latest}/study-data.json
→ {
    "homework":     [ {subject_en/zh, title_en/zh, due, status, submission, desc_en/zh} ],
    "announcements":[ {date, class_en/zh, author, content_en/zh} ],
    "events":       [ {date, type, title_en/zh, details_en/zh, time} ],
    "timetable":    "timetable.html",
    "materials":    [ {subject_en/zh, test_en, test_date, kind_en/zh,
                       title_en/zh, file: "materials/....pdf"} ]
  }
```

- `latest` always points at the most recent folder with materials, so the app
  automatically uses today's data after a publish, or yesterday's before that.
- Open `timetable.html` in a WebView; open material PDFs with an intent/viewer.

## Publishing

```
python3 build_feed.py [YYYY-MM-DD]     # defaults to today (HKT)
```

Reads the newest `research_notes/classroom-YYYY-MM-DD/data.json`, copies the
live timetable and the week's material PDFs, writes `study-data.json`, and
refreshes `index.json`. Run it at the end of the daily summary job and the
Friday study-plan job, then push to GitHub Pages.
