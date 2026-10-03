#!/usr/bin/env python3
"""Build the SteveBot study feed: a dated folder of JSON + files the app reads.

Layout produced (repo root = this directory):
    index.json                      {"latest": "Summary/YYYY-MM-DD", "updated": iso, "dates": [...]}
    YYYY-MM-DD/
        study-data.json             homework, announcements, events, materials manifest
        homework.html               homework section only (filters work standalone)
        announcements.html          announcements section only
        calendar.html               calendar section only (day popups work standalone)
    materials/<Subject>/YYYY-MM-DD/*.pdf
    materials/index.json            every material, for the app's folder UI
    timetable/timetable.html        current weekly timetable

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
    "English": "英文", "Art": "美術", "Music": "音樂",
    "Drama": "戲劇", "PE": "體育", "French": "法文",
    "Spanish": "西班牙文", "Textile": "紡織", "STEM": "STEM",
    "Chinese History": "中國歷史",
}
# All of Steve's school subjects (user confirmed 2026-10-03).
# Every subject gets a folder under materials/, even before it has files.
ALL_SUBJECTS = sorted(SUBJECT_ZH.keys())
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


def _block(s, tag, id_value):
    """Extract the <tag ... id="id_value" ...>...</tag> block, depth-matched."""
    idpos = s.find(f'id="{id_value}"')
    if idpos == -1:
        return ""
    dstart = s.rfind(f'<{tag}', 0, idpos)
    close = f'</{tag}>'
    depth, i = 0, dstart
    while True:
        o = s.find(f'<{tag}', i + 1)
        c = s.find(close, i + 1)
        if c == -1:
            return ""
        if o != -1 and o < c:
            depth += 1
            i = o
        else:
            if depth == 0:
                return s[dstart:c + len(close)]
            depth -= 1
            i = c


def _split_summary(day_dir):
    """Split school-calendar.html into homework/announcements/calendar pages."""
    src = "/home/hatch/workspace/your_files/school-calendar/school-calendar.html"
    if not os.path.exists(src):
        return
    s = open(src).read()

    css_m = re.search(r'<style[^>]*>(.*?)</style>', s, re.S)
    css = css_m.group(1) if css_m else ""
    js = re.search(r'<script>(.*?)</script>', s, re.S).group(1)
    footer_m = re.search(r'<footer.*?</footer>', s, re.S)
    footer = footer_m.group(0) if footer_m else ""
    overlay = _block(s, "div", "overlay")

    def js_chunk(name, next_name=None):
        bi = js.find(f'============ {name}')
        st = js.rfind('/*', 0, bi)
        if next_name:
            npos = js.find(f'============ {next_name}')
            en = js.rfind('/*', 0, npos)
        else:
            en = len(js)
        return js[st:en]

    preamble = js[:js.rfind('/*', 0, js.find('============ Tabs'))]
    js_hw = preamble + js_chunk('Homework', 'Announcements') + "\nrenderHomework();\n"
    js_ann = preamble + js_chunk('Announcements', 'Calendar')
    js_cal = (preamble + js_chunk('Calendar', 'Modal')
              + js_chunk('Modal', 'Init') + "\nrenderCalendar();\n")

    def page(title, body, script):
        return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                f'<title>{title}</title>\n<style>{css}</style>\n</head>\n<body>\n'
                f'<header class="page-head"><h1>{title}</h1>'
                f'<p class="who">Steve Cheng &middot; Class 6B</p></header>\n'
                f'<main>\n{body}\n</main>\n{footer}\n<script>{script}</script>\n'
                f'</body>\n</html>')

    def panel(key):
        html = _block(s, "section", f"panel-{key}")
        # make the lone panel visible (original relies on tab switching)
        html = re.sub(r'<section([^>]*?)class="panel"([^>]*?)>',
                      r'<section\1class="panel active"\2>', html, count=1)
        html = html.replace(' hidden', '', 1)
        return html

    pages = [
        ("homework.html", "Homework 功課", panel("hw"), js_hw),
        ("announcements.html", "Announcements 通告", panel("ann"), js_ann),
        ("calendar.html", "Calendar 日曆", panel("cal") + "\n" + overlay, js_cal),
    ]
    for fname, title, body, script in pages:
        # sanity: no tab-switching code should remain in split pages
        assert "selectTab" not in script, fname
        with open(os.path.join(day_dir, fname), "w") as f:
            f.write(page(title, body, script))
    # drop the old combined file; the app now uses the three pages
    old = os.path.join(day_dir, "summary.html")
    if os.path.exists(old):
        os.remove(old)


def _write_materials_index():
    """Root materials/index.json: every PDF, grouped for the app's folder UI."""
    base = os.path.join(FEED, "materials")
    entries = []
    if os.path.isdir(base):
        for subj in sorted(os.listdir(base)):
            sdir = os.path.join(base, subj)
            if not os.path.isdir(sdir):
                continue
            for d in sorted(os.listdir(sdir)):
                ddir = os.path.join(sdir, d)
                if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and os.path.isdir(ddir)):
                    continue
                for f in sorted(os.listdir(ddir)):
                    if not f.lower().endswith(".pdf"):
                        continue
                    e = parse_material(f)
                    e["file"] = f"materials/{subj}/{d}/{f}"
                    e["date"] = d
                    entries.append(e)
    entries.sort(key=lambda m: (m["subject_en"], m.get("date") or "9999",
                                m["test_date"] or "9999"))
    # Every subject gets a folder, even with no materials yet
    # (.gitkeep keeps empty folders in git).
    for subj in ALL_SUBJECTS:
        sdir = os.path.join(base, subj)
        os.makedirs(sdir, exist_ok=True)
        if not any(os.scandir(sdir)):
            open(os.path.join(sdir, ".gitkeep"), "w").close()
    with open(os.path.join(base, "index.json"), "w") as f:
        json.dump({"updated": datetime.now(HKT).isoformat(timespec="seconds"),
                   "count": len(entries),
                   "subjects": [{"en": k, "zh": SUBJECT_ZH[k]} for k in ALL_SUBJECTS],
                   "materials": entries},
                  f, ensure_ascii=False, indent=1)


def build(date_str, prune_keep=10):
    # Disable Jekyll on GitHub Pages: serve raw files, build fast.
    open(os.path.join(FEED, ".nojekyll"), "a").close()
    data_path = newest_data_json()
    data = json.load(open(data_path)) if data_path else {}
    day_dir = os.path.join(FEED, "Summary", date_str)
    os.makedirs(day_dir, exist_ok=True)

    # 1. study-data.json — only actionable items, app-friendly
    hw = [h for h in data.get("homework", [])
          if h.get("status") in ("outstanding", "na")]
    hw.sort(key=lambda h: (h.get("due") or "9999", h.get("subject_en", "")))
    events = sorted(data.get("events", []), key=lambda e: e.get("date") or "9999")

    # 2. materials -> root materials/<Subject>/<YYYY-MM-DD>/ (outside date folders)
    src_mat = newest_materials_dir()
    manifest = []
    mat_date = os.path.basename(src_mat) if src_mat else date_str
    if src_mat and os.path.isdir(src_mat):
        for f in sorted(os.listdir(src_mat)):
            if not f.lower().endswith(".pdf"):
                continue
            entry = parse_material(f)
            subj_dir = os.path.join(FEED, "materials", entry["subject_en"], mat_date)
            os.makedirs(subj_dir, exist_ok=True)
            shutil.copy2(os.path.join(src_mat, f), os.path.join(subj_dir, f))
            entry["file"] = f"materials/{entry['subject_en']}/{mat_date}/{f}"
            manifest.append(entry)
    manifest.sort(key=lambda m: (m["subject_en"], m["test_date"] or "9999"))
    _write_materials_index()

    study_data = {
        "date": date_str,
        "generated_at": datetime.now(HKT).isoformat(timespec="seconds"),
        "source": os.path.basename(data_path) if data_path else None,
        "homework": hw,
        "announcements": data.get("announcements", []),
        "events": events,
        "timetable": "timetable/timetable.html",
        "materials": manifest,
    }
    with open(os.path.join(day_dir, "study-data.json"), "w") as f:
        json.dump(study_data, f, ensure_ascii=False, indent=1)

    # 3. timetable -> root timetable/timetable.html (single current file)
    tt = "/home/hatch/workspace/user/files/steve-study-timetable.html"
    tt_dir = os.path.join(FEED, "timetable")
    if os.path.exists(tt):
        os.makedirs(tt_dir, exist_ok=True)
        shutil.copy2(tt, os.path.join(tt_dir, "timetable.html"))
    # drop the old per-date copy if present
    old_tt = os.path.join(day_dir, "timetable.html")
    if os.path.exists(old_tt):
        os.remove(old_tt)

    # 3b. Split the classroom summary into standalone section pages.
    # The Studiyo app loads one page per button (no tab bar inside the app).
    # Splitting happens here at build time so every future export keeps working.
    _split_summary(day_dir)

    # 4. index.json with latest pointer (+ prune old dates to keep repo lean)
    sum_dir = os.path.join(FEED, "Summary")
    os.makedirs(sum_dir, exist_ok=True)
    dates = sorted(d for d in os.listdir(sum_dir)
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
                   and os.path.isdir(os.path.join(sum_dir, d)))
    for old in dates[:-prune_keep]:
        shutil.rmtree(os.path.join(sum_dir, old))
    dates = sorted(d for d in os.listdir(sum_dir)
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
                   and os.path.isdir(os.path.join(sum_dir, d)))
    index = {
        "latest": f"Summary/{dates[-1]}" if dates else f"Summary/{date_str}",
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
