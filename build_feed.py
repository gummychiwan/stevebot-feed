#!/usr/bin/env python3
"""Build the SteveBot study feed: a dated folder of JSON + files the app reads.

Layout produced (repo root = this directory):
    index.json                      {"latest": "YYYY-MM-DD", "updated": iso, "dates": [...]}
    YYYY-MM-DD/
        study-data.json             homework, announcements, events, materials manifest
        summary.html                classroom summary (tabs deep-linkable: #hw #ann #cal)
        timetable.html              that week's study timetable
        materials/*.pdf             key notes / flashcards / mock papers

The app fetches index.json, reads `latest`, then loads that folder.
Run daily after new summaries/materials are made:
    python3 build_feed.py [YYYY-MM-DD]
"""
import json, re, shutil, sys, os
from datetime import datetime, timezone, timedelta

FEED = os.path.dirname(os.path.abspath(__file__))
HKT = timezone(timedelta(hours=8))
SUBJECT_ZH = {
    "Science": "科學", "History": "歷史", "ICT": "資訊科技",
    "Maths": "數學", "Geography": "地理", "Chinese": "中文",
    "English": "英文", "Art": "視藝", "Music": "音樂",
}
KIND_PATTERNS = [
    (re.compile(r"flashcards?", re.I), "Flashcards", "生字卡"),
    (re.compile(r"key-?notes?", re.I), "Key Notes", "重點筆記"),
    (re.compile(r"mock-?paper", re.I), "Mock Paper", "模擬試卷"),
    (re.compile(r"\bdrill\b", re.I), "Drill", "練習"),
]
DATE_PAT = re.compile(r"(\d{2})(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(\d{4})", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_material(fname):
    """Turn 'Maths-UC02-Percentages-Mock-Paper-13oct2026.pdf' into a manifest entry."""
    stem = fname[:-4] if fname.lower().endswith(".pdf") else fname
    parts = stem.split("-")
    subject = parts[0]
    kind_en, kind_zh = "Material", "教材"
    for pat, ke, kz in KIND_PATTERNS:
        if pat.search(stem):
            kind_en, kind_zh = ke, kz
            break
    # test label: middle parts minus kind words and trailing date
    skip = {"flashcards", "flashcard", "key", "notes", "note", "mock", "paper", "drill"}
    label_parts, test_date = [], None
    for p in parts[1:]:
        m = DATE_PAT.fullmatch(p)
        if m:
            d, mon, y = m.groups()
            test_date = f"{y}-{MONTHS[mon.lower()]:02d}-{int(d):02d}"
            continue
        if p.lower() not in skip:
            label_parts.append(p)
    test_label = " ".join(label_parts) or subject
    return {
        "subject_en": subject,
        "subject_zh": SUBJECT_ZH.get(subject, subject),
        "test_en": test_label,
        "test_date": test_date,
        "kind_en": kind_en, "kind_zh": kind_zh,
        "file": f"materials/{fname}",
        "title_en": f"{subject} {test_label} — {kind_en}",
        "title_zh": f"{SUBJECT_ZH.get(subject, subject)}{test_label}——{kind_zh}",
    }


def newest_data_json():
    base = "/home/hatch/workspace/research_notes"
    cands = sorted(
        (d for d in os.listdir(base)
         if d.startswith("classroom-") and
         os.path.exists(os.path.join(base, d, "data.json"))),
        reverse=True)
    if not cands:
        return None
    return os.path.join(base, cands[0], "data.json")


def newest_materials_dir():
    base = "/home/hatch/workspace/study/materials"
    cands = sorted(
        (d for d in os.listdir(base)
         if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
         and os.path.isdir(os.path.join(base, d))),
        reverse=True)
    return os.path.join(base, cands[0]) if cands else None


def build(date_str, prune_keep=10):
    data_path = newest_data_json()
    data = json.load(open(data_path)) if data_path else {}
    day_dir = os.path.join(FEED, date_str)
    mat_dir = os.path.join(day_dir, "materials")
    os.makedirs(mat_dir, exist_ok=True)

    # 1. study-data.json — only actionable items, app-friendly
    hw = [h for h in data.get("homework", [])
          if h.get("status") in ("outstanding", "na")]
    hw.sort(key=lambda h: (h.get("due") or "9999", h.get("subject_en", "")))
    events = sorted(data.get("events", []), key=lambda e: e.get("date") or "9999")

    # 2. materials: copy PDFs + manifest
    src_mat = newest_materials_dir()
    manifest = []
    if os.path.isdir(src_mat):
        for f in sorted(os.listdir(src_mat)):
            if not f.lower().endswith(".pdf"):
                continue
            shutil.copy2(os.path.join(src_mat, f), os.path.join(mat_dir, f))
            manifest.append(parse_material(f))
    manifest.sort(key=lambda m: (m["subject_en"], m["test_date"] or "9999"))

    study_data = {
        "date": date_str,
        "generated_at": datetime.now(HKT).isoformat(timespec="seconds"),
        "source": os.path.basename(data_path) if data_path else None,
        "homework": hw,
        "announcements": data.get("announcements", []),
        "events": events,
        "timetable": "timetable.html",
        "materials": manifest,
    }
    with open(os.path.join(day_dir, "study-data.json"), "w") as f:
        json.dump(study_data, f, ensure_ascii=False, indent=1)

    # 3. timetable.html
    tt = "/home/hatch/workspace/user/files/steve-study-timetable.html"
    if os.path.exists(tt):
        shutil.copy2(tt, os.path.join(day_dir, "timetable.html"))

    # 3b. summary.html — classroom summary with deep-linkable tabs.
    # The Studiyo app opens summary.html#hw / #ann / #cal in a WebView so the
    # app UI always matches the summary HTML exactly. Injection happens here
    # (not in the artifact) so every future export keeps working.
    SUMMARY_SRC = "/home/hatch/workspace/your_files/school-calendar/school-calendar.html"
    DEEPLINK_JS = (
        "<script>\n"
        "/* Studiyo app deep-link: summary.html#hw | #ann | #cal opens that tab */\n"
        "(function(){var h=(location.hash||'').replace('#','');"
        "if(h==='hw'||h==='ann'||h==='cal'){"
        "var b=document.querySelector('[data-tab=\"'+h+'\"]');"
        "if(b){b.click();}}})();\n"
        "</script>\n"
    )
    if os.path.exists(SUMMARY_SRC):
        html = open(SUMMARY_SRC).read()
        html = html.replace("</body>", DEEPLINK_JS + "</body>")
        with open(os.path.join(day_dir, "summary.html"), "w") as f:
            f.write(html)

    # 4. index.json with latest pointer (+ prune old dates to keep repo lean)
    dates = sorted(d for d in os.listdir(FEED)
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
                   and os.path.isdir(os.path.join(FEED, d)))
    for old in dates[:-prune_keep]:
        shutil.rmtree(os.path.join(FEED, old))
    dates = sorted(d for d in os.listdir(FEED)
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
                   and os.path.isdir(os.path.join(FEED, d)))
    index = {
        "latest": dates[-1] if dates else date_str,
        "updated": datetime.now(HKT).isoformat(timespec="seconds"),
        "dates": dates,
    }
    with open(os.path.join(FEED, "index.json"), "w") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    print(f"feed date {date_str}: {len(hw)} homework, "
          f"{len(study_data['announcements'])} announcements, "
          f"{len(events)} events, {len(manifest)} materials; latest={index['latest']}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else
          datetime.now(HKT).strftime("%Y-%m-%d"))
