"""Calendar files for the Anaesthesia Meetings Almanac.

Writes one .ics per meeting and one per published deadline into docs/ics/, plus two subscription files
(docs/anaesthesia-meetings.ics with every meeting, docs/anaesthesia-meetings-deadlines.ics with every deadline
still ahead, each with reminders a week before and the day before), and stamps docs/sw.js so the offline copy refreshes.

Usage, from the repository root:
  python3 tools/make_ics.py                         # reads the meetings JSON embedded in docs/index.html (what the GitHub workflow runs)
  python3 tools/make_ics.py --from-json data/meetings.json --docs docs
Output is deterministic for a given dataset (DTSTAMP is the dataset's checked date), so unchanged meetings give unchanged files.
"""
import argparse, glob, hashlib, json, os, re, datetime as dt

PUB_URL = 'https://ganeshsivasankara.com/anaesthesia-meetings/'
DOMAIN = 'anaesthesia-meetings.ganeshsivasankara.com'
KINDS = {'abstract_deadline': ('abstracts', 'abstracts close'), 'early_registration_deadline': ('early-rate', 'early rate ends')}
WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

def load(args):
    if args.from_json:
        return json.load(open(args.from_json, encoding='utf-8'))
    html = open(args.from_html, encoding='utf-8').read()
    m = re.search(r'<script id="meetings-data" type="application/json">(.*?)</script>', html, re.S)
    if not m: raise SystemExit('meetings-data script not found in ' + args.from_html)
    return json.loads(m.group(1).replace('<\\/', '</'))

def esc(s):
    return str(s or '').replace('\\', '\\\\').replace('\r\n', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')

def fold(line):
    out, b = [], line.encode('utf-8')
    while len(b) > 75:
        cut = 75
        while cut > 0 and (b[cut] & 0xC0) == 0x80: cut -= 1
        out.append(b[:cut].decode('utf-8')); b = b' ' + b[cut:]
    out.append(b.decode('utf-8'))
    return '\r\n'.join(out)

def ymd(s): return s.replace('-', '')
def date(s): return dt.date.fromisoformat(s)
def nice(s):
    x = date(s); return f'{WD[x.weekday()]} {x.day} {MON[x.month-1]} {x.year}'
def plus(s, n): return (date(s) + dt.timedelta(days=n)).isoformat()

def vevent(stamp, uid, start, end_excl, summary, description, location, url, alarms=()):
    lines = ['BEGIN:VEVENT', f'UID:{uid}@{DOMAIN}', f'DTSTAMP:{stamp}', f'DTSTART;VALUE=DATE:{ymd(start)}', f'DTEND;VALUE=DATE:{ymd(end_excl)}',
             f'SUMMARY:{esc(summary)}']
    if location: lines.append(f'LOCATION:{esc(location)}')
    if description: lines.append(f'DESCRIPTION:{esc(description)}')
    if url: lines.append(f'URL:{url}')
    lines.append('TRANSP:TRANSPARENT')
    for trig, text in alarms:
        lines += ['BEGIN:VALARM', 'ACTION:DISPLAY', f'DESCRIPTION:{esc(text)}', f'TRIGGER:{trig}', 'END:VALARM']
    lines.append('END:VEVENT')
    return lines

def vcalendar(name, events, desc=None):
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', f'PRODID:-//Anaesthesia Meetings Almanac//{DOMAIN}//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
             f'X-WR-CALNAME:{esc(name)}']
    if desc: lines.append(f'X-WR-CALDESC:{esc(desc)}')
    lines += ['REFRESH-INTERVAL;VALUE=DURATION:P1D', 'X-PUBLISHED-TTL:P1D']
    for ev in events: lines += ev
    lines.append('END:VCALENDAR')
    return '\r\n'.join(fold(l) for l in lines) + '\r\n'

def meeting_event(stamp, m):
    loc = ', '.join(x for x in [m.get('venue'), m.get('city'), m.get('country')] if x)
    bits = [m['name'], m['organiser']]
    if m.get('dates_status') == 'provisional': bits.append('Dates provisional: the organiser has not yet confirmed them.')
    if m.get('abstract_deadline'): bits.append(f"Abstracts close {nice(m['abstract_deadline'])}.")
    if m.get('early_registration_deadline'): bits.append(f"Early rate ends {nice(m['early_registration_deadline'])}.")
    if m.get('website'): bits.append(m['website'])
    bits.append(f"Anaesthesia Meetings Almanac: {PUB_URL}#{m['id']}")
    return vevent(stamp, m['id'], m['start'], plus(m['end'], 1), m['short'], '\n'.join(bits), loc, m.get('website'))

def deadline_event(stamp, m, key):
    slug, words = KINDS[key]
    day = m[key]
    desc = '\n'.join(x for x in [m['name'], f"{words[0].upper()}{words[1:]} {nice(day)}.", m.get('website'), f"Anaesthesia Meetings Almanac: {PUB_URL}#{m['id']}"] if x)
    alarms = [('-P7DT15H', f"{m['short']}: {words} in a week"), ('-PT15H', f"{m['short']}: {words} tomorrow")]
    return vevent(stamp, f"{m['id']}-{slug}", day, plus(day, 1), f"{m['short']}: {words}", desc, None, m.get('website'), alarms)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from-html', default='docs/index.html')
    ap.add_argument('--from-json', default=None)
    ap.add_argument('--docs', default='docs')
    ap.add_argument('--today', default=dt.date.today().isoformat(), help='deadlines before this date are left out of the subscription file')
    args = ap.parse_args()
    d = load(args)
    meetings = d['meetings']
    stamp = ymd(d['checked']) + 'T000000Z'
    today = date(args.today)
    out = os.path.join(args.docs, 'ics')
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, '*.ics')): os.remove(old)
    def write(path, text): open(path, 'w', encoding='utf-8', newline='').write(text)
    n_files = 0
    all_meetings, all_deadlines = [], []
    for m in meetings:
        ev = meeting_event(stamp, m); all_meetings.append(ev)
        write(os.path.join(out, f"{m['id']}.ics"), vcalendar(m['short'], [ev])); n_files += 1
        for key, (slug, words) in KINDS.items():
            if m.get(key):
                ev = deadline_event(stamp, m, key)
                if date(m[key]) >= today: all_deadlines.append(ev)
                write(os.path.join(out, f"{m['id']}-{slug}.ics"), vcalendar(f"{m['short']}: {words}", [ev])); n_files += 1
    win = d['window']
    write(os.path.join(args.docs, 'anaesthesia-meetings.ics'),
          vcalendar('Anaesthesia meetings', all_meetings, f'Anaesthesia meetings worldwide, {nice(win[0])} to {nice(win[1])}, each read from its official page. {PUB_URL}'))
    write(os.path.join(args.docs, 'anaesthesia-meetings-deadlines.ics'),
          vcalendar('Anaesthesia meeting deadlines', all_deadlines, f'Abstract and early-rate deadlines for anaesthesia meetings, with reminders a week before and the day before. {PUB_URL}'))
    # stamp the service worker with the page's hash so the offline copy refreshes after a review
    sw_path = os.path.join(args.docs, 'sw.js')
    if os.path.exists(sw_path) and os.path.exists(args.from_html):
        stamp_id = hashlib.sha1(open(args.from_html, 'rb').read()).hexdigest()[:10]
        sw = open(sw_path, encoding='utf-8').read()
        sw2 = re.sub(r"const V = 'almanac-[0-9a-f]+';", f"const V = 'almanac-{stamp_id}';", sw)
        if sw2 != sw: open(sw_path, 'w', encoding='utf-8').write(sw2)
    print(f'{n_files} single-event files, {len(all_meetings)} meetings and {len(all_deadlines)} deadlines in the year files')

if __name__ == '__main__':
    main()
