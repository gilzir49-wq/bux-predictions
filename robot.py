# רובוט תוצאות: מושך תוצאות לייב מ-LiveScore ומעדכן את האפליקציה (Firebase) אוטומטית.
# רץ בענן של GitHub (Actions). המנהל יכול לכבות אותו מהאפליקציה, ותיקון ידני נשמר עד שהתוצאה במקור משתנה.
import json, time, urllib.request, datetime, sys

DB = 'https://command-center-gal-default-rtdb.europe-west1.firebasedatabase.app'
NODE = next((a for a in sys.argv[1:] if not a.startswith('--')), 'bux-predictions')
DATE = '20261016'
FEED = f'https://prod-public-api.livescore.com/v1/api/app/date/soccer/{DATE}/3?MD=1'
# משחק באפליקציה ← מזהה המשחק ב-LiveScore (קבוצת הבית זהה)
MAP = {'g1': '1799344', 'g2': '1799345', 'g3': '1799339', 'g4': '1799343', 'g5': '1799341'}
STOP_AT = datetime.datetime(2026, 10, 16, 16, 45, tzinfo=datetime.timezone.utc)  # 19:45 שעון ישראל
POLL = 20
# מצב בדיקה: --test=EID1,EID2 → משחקים חיים אחרים, בסביבת בדיקה נפרדת, נמחק לגמרי ב-15:30
TEST = next((a.split('=',1)[1].split(',') for a in sys.argv if a.startswith('--test=')), None)
if TEST:
    MAP = {f't{i+1}': eid for i, eid in enumerate(TEST)}
    STOP_AT = datetime.datetime(2026, 10, 16, 12, 30, tzinfo=datetime.timezone.utc)  # 15:30 שעון ישראל

def http(url, method='GET', body=None):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode() or 'null')

def feed():
    d = http(FEED)
    out = {}
    for s in d.get('Stages', []):
        for e in s.get('Events', []):
            out[str(e.get('Eid'))] = e
    return out

def status_of(eps):
    eps = (eps or '').strip()
    if eps in ('FT', 'AET', 'AP', 'Ended'): return 'finished'
    if eps in ('NS', '', 'Postp.', 'Canc.', 'Abd.', 'TBA', 'Delayed'): return 'none'
    return 'live'   # HT / דקה ("37'") וכו'

def tick():
    meta = http(f'{DB}/{NODE}/meta.json') or {}
    if meta.get('auto') == 'off':
        return 'off'
    f = feed()
    results = http(f'{DB}/{NODE}/results.json') or {}
    upd = {}
    for gid, eid in MAP.items():
        e = f.get(eid)
        if not e: continue
        st = status_of(e.get('Eps'))
        h = int(e.get('Tr1') or 0) if st != 'none' else 0
        a = int(e.get('Tr2') or 0) if st != 'none' else 0
        sig = f'{h}-{a}-{st}'
        cur = results.get(gid) or {}
        if cur.get('feed') != sig:
            upd[f'results/{gid}'] = {'h': h, 'a': a, 'status': st, 'feed': sig}
    stamp = {'meta/robotAt': int(time.time() * 1000)}
    if upd:
        upd['meta/prevResults'] = {'r': results, 't': int(time.time() * 1000)}   # לחצים בטבלה + "עלו בטבלה"
        http(f'{DB}/{NODE}.json', 'PATCH', {**upd, **stamp})
    else:
        http(f'{DB}/{NODE}.json', 'PATCH', stamp)
    fin = all((f.get(e) and status_of(f[e].get('Eps')) == 'finished') for e in MAP.values())
    return ('updated ' + ', '.join(f'{k}={v["feed"]}' for k, v in upd.items() if k.startswith('results/'))) if upd else ('done' if fin else 'no change')

def setup_test():
    f = feed()
    games = [{'id': gid, 'home': f[eid]['T1'][0]['Nm'], 'away': f[eid]['T2'][0]['Nm']} for gid, eid in MAP.items()]
    cur = {gid: (int(f[eid].get('Tr1') or 0), int(f[eid].get('Tr2') or 0)) for gid, eid in MAP.items()}
    # שני שחקני דמה כדי לראות את הטבלה זזה
    pa = {gid: {'h': h, 'a': a} for gid, (h, a) in cur.items()}
    pb = {gid: {'h': h + 1, 'a': a} for gid, (h, a) in cur.items()}
    http(f'{DB}/{NODE}.json', 'PUT', {'meta': {'games': games, 'lock': 'locked'},
        'players': {'בודק_א': {'name': 'בודק א', 'owner': 'x', 'preds': pa, 'total': sum(h+a for h, a in cur.values())},
                    'בודק_ב': {'name': 'בודק ב', 'owner': 'x', 'preds': pb, 'joker': 't1', 'total': 9}}})
    print('test setup:', games, flush=True)

if __name__ == '__main__':
    once = '--once' in sys.argv
    if TEST: setup_test()
    while True:
        try:
            r = tick()
            print(datetime.datetime.now().strftime('%H:%M:%S'), r, flush=True)
            if r == 'done' or once: break
        except Exception as ex:
            print('error:', ex, flush=True)
            if once: break
        if datetime.datetime.now(datetime.timezone.utc) > STOP_AT: break
        time.sleep(POLL)
    if TEST:   # מחיקה מלאה של סביבת הבדיקה
        http(f'{DB}/{NODE}.json', 'DELETE'); print('test deleted', flush=True)
