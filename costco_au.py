#!/usr/bin/env python3
"""Find Costco Australia price adjustments worth asking for.

When something you bought at a Costco Australia warehouse goes on special within about 30 days, you can
ask the Membership counter to refund the difference (at the warehouse's discretion). This compares your
receipts against the current In-Warehouse Savings booklet and lists what to ask for, with a date for each.

  costco-au link                                         print the current booklet link
  costco-au check costco-receipts.json costco-booklet.json   what to ask for
"""
import argparse
import base64
import csv
import datetime
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

UA = 'costco-au-price-adjust (personal use; https://github.com/campbellsmurphy/costco-au-price-adjust)'
CMS = 'https://www.costco.com.au/rest/v3/australia/cms/pages?pageType=ContentPage&pageLabelOrId=warehouse-savings'
PRODUCT = 'https://www.costco.com.au/rest/v2/australia/products/{code}?fields=FULL'
WINDOW_DAYS = 30


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ''
        sys.exit(f'costco.com.au answered {e.code} for {url}. Try again later; this tool does not retry.')
    except urllib.error.URLError:
        sys.exit('Could not reach costco.com.au. Check your internet connection and try again.')


# ---------- booklet ----------

def booklet_url():
    m = re.search(r'https://viewer\.joomag\.com/in-warehouse-savings[^"\\]*', get(CMS))
    if not m:
        sys.exit('Could not find the booklet link. Open https://www.costco.com.au/warehouse-savings '
                 'and use its "View In-Warehouse Savings" link.')
    return m.group(0)


def booklet_dates(url):
    """The link names its own dates: in-warehouse-savings-26-10-26-22-11-26 is 26/10/26 to 22/11/26."""
    m = re.search(r'savings-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', url or '')
    if not m:
        return None, None
    d = [int(x) for x in m.groups()]
    return datetime.date(2000 + d[2], d[1], d[0]), datetime.date(2000 + d[5], d[4], d[3])


def read_json(path):
    if not os.path.exists(path):
        sys.exit(f'{path} not found. Run sync first, or pass the files the browser snippet saved.')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_private(path, data):
    """Receipts carry your member number, so only your user account can read what this tool saves."""
    os.makedirs(HOME, mode=0o700, exist_ok=True)
    os.chmod(HOME, 0o700)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as f:
        os.chmod(path, 0o600)  # the mode above only applies to a new file
        json.dump(data, f)


def load_booklet(path):
    """Read the booklet file that sync or the snippet saves: {'url', 'pages': {view: text}}."""
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get('pages'), dict):
        sys.exit(f'{path} is not a booklet file. Give the receipts file first and the booklet file second.')
    return data.get('url', ''), list(data['pages'].values())


def parse_booklet(texts):
    """Most offers read: name lines, '$21', '99', 'After $5.50 off', 'Item 112472 | $0.20 per 100sheets'.
    Liquor offers read: name lines, '$12 off', 'Item 45967', with no price.

    Returns {item number: {'off', 'price' (after the discount, or None), 'name'}}. Views overlap, so the
    first sighting wins.
    """
    money = lambda t: float(t.replace(',', '').replace(' ', ''))
    offers = {}
    for text in texts:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for i in range(len(lines)):
            off = re.fullmatch(r'(After )?\$ ?([\d,]+(?:\.\d+)?) o(?:ff|ﬀ)', lines[i])
            if not off:
                continue
            dollars = re.fullmatch(r'\$ ?([\d,]+)', lines[i - 2]) if i >= 2 else None
            cents = re.fullmatch(r'\d{2}', lines[i - 1]) if i >= 1 else None
            price = money(dollars.group(1)) + int(cents.group(0)) / 100 if off.group(1) and dollars and cents else None
            name = []
            for l in reversed(lines[max(0, i - 6):i - 2 if price is not None else i]):
                if l.startswith(('Item', '*', '$', 'After')) or re.fullmatch(r'\d{2}', l) or len(l) > 60:
                    break
                name.insert(0, l)
            j = i + 1
            while j < len(lines) and lines[j].startswith('Item'):
                for num in re.findall(r'\b(\d{4,8})\b', lines[j].split('$')[0]):
                    offers.setdefault(num, {'off': money(off.group(2)),
                                            'price': round(price, 2) if price is not None else None,
                                            'name': ' '.join(name)})
                j += 1
    return offers


# ---------- receipts ----------

def load_receipts(path):
    """Read the file the snippet saves on the receipts page (a list of {'text'}), or the one sync saves."""
    data = read_json(path)
    if not isinstance(data, list):
        sys.exit(f'{path} is not a receipts file. Give the receipts file first and the booklet file second.')
    return [r if 'lines' in r else r['text'] for r in data]


def parse_receipt(text):
    """Pull the date, member number and shop lines out of one receipt's text."""
    when = re.search(r'(\d{2})/(\d{2})/(\d{4}) \d{2}:\d{2}', text)
    # a refund receipt (items sold below zero) has no purchases on it, only reversals
    if not when or re.search(r'ITEMS SOLD = -\d', text):
        return None
    member = re.search(r'Member (\d+)', text)
    lines = text.split('\n')
    items = []
    for j, line in enumerate(lines):
        # "249314<tab>2x<tab>24.99<tab>49.98"; fuel is "29531<tab>44.11x" (decimal litres); returns and
        # discount lines end in "-"
        m = re.match(r'^(\d{4,8})\t(\d+)x\t([\d.]+)\t([\d.]+)( ?-)?', line)
        if not m or m.group(5):
            continue
        following = lines[j + 1] if j + 1 < len(lines) else ''
        items.append({
            'item': m.group(1),
            'qty': int(m.group(2)),
            'paid': float(m.group(3)),
            'name': ' '.join(l.strip() for l in lines[max(0, j - 2):j] if not re.match(r'^(\d|TPD|MVM|IRC|Member|SBS)', l)),
            # the till already took a discount off this line (temporary price drop, multi-buy, rebate)
            'discounted': bool(re.match(r'^(TPD|MVM|IRC)\b', following)),
        })
    return {
        'date': datetime.date(int(when.group(3)), int(when.group(2)), int(when.group(1))),
        'member': member.group(1) if member else '',
        'items': items,
    }


def receipt_from_api(d):
    """Same shape as parse_receipt, from a receipt that `sync` saved (costco.com.au receipt details JSON)."""
    if d.get('recordType') != 'SALE':
        return None
    when = datetime.datetime.fromisoformat(d['transactionDateTime'].replace('Z', '+00:00'))
    lines = d.get('lines') or []
    items = []
    for j, l in enumerate(lines):
        qty = l.get('qty') or 0
        # fuel is sold in fractional litres; a COUPON line straight after an item is a discount taken at the till
        if l.get('type') != 'CAPTURED' or qty != int(qty) or qty <= 0:
            continue
        nxt = lines[j + 1] if j + 1 < len(lines) else {}
        items.append({
            'item': l['itemNumber'],
            'qty': int(qty),
            'paid': l['sellPrice']['value'],
            'name': ' '.join(l.get('itemDescription') or [])[:60],
            'discounted': nxt.get('type') == 'COUPON',
        })
    return {
        'date': when.astimezone(ZoneInfo('Australia/Sydney')).date(),
        'member': d.get('membershipNumber', ''),
        'items': items,
    }


def load_claimed(path):
    """Refunds you already got: CSV with purchase_date (YYYY-MM-DD) and item columns."""
    if not path:
        return set()
    with open(path, encoding='utf-8') as f:
        return {(r['purchase_date'], r['item']) for r in csv.DictReader(f)}


def find_claims(receipts, offers, claimed, today):
    cut = today - datetime.timedelta(days=WINDOW_DAYS)
    claims, skipped, in_window = [], [], []
    for r in receipts:
        if not r or not r['items'] or not cut <= r['date'] <= today:
            continue
        in_window.append(r)
        for it in r['items']:
            o = offers.get(it['item'])
            if not o:
                continue
            if (r['date'].isoformat(), it['item']) in claimed:
                skipped.append((r, it, 'already refunded'))
            elif it['discounted']:
                skipped.append((r, it, 'the discount was already taken at the till'))
            else:
                # never more than the gap between what you paid and the booklet price
                each = o['off'] if o['price'] is None else round(min(o['off'], it['paid'] - o['price']), 2)
                if each > 0:
                    claims.append((r, it, o, each))
                else:
                    skipped.append((r, it, 'you already paid the booklet price or less'))
    return claims, skipped, in_window


# ---------- online discounts (opt in) ----------

def online_finding(p, paid, today):
    """What costco.com.au shows for one product that is worth a look: a live '$X off', or a price
    (after any discount) below what you paid in the warehouse. None if neither."""
    if not p.get('name'):
        return None
    c = p.get('couponDiscount') or {}
    end = (c.get('discountEndDate') or '')[:10]
    off = float(c['discountValue']) if c.get('discountValue') and (not end or end >= today.isoformat()) else 0.0
    price = (p.get('price') or {}).get('value')
    now = price - off if price is not None else None
    if not off and not (now is not None and now < paid):
        return None
    return {'off': off, 'end': end, 'now': now, 'paid': paid, 'name': p['name']}


def online_check(paid_by_code, today):
    """Look up each item on costco.com.au: one request per item, a second apart."""
    found = {}
    for code, paid in sorted(paid_by_code.items()):
        body = get(PRODUCT.format(code=code))
        time.sleep(1)
        try:
            f = online_finding(json.loads(body) if body else {}, paid, today)
        except ValueError:
            continue
        if f:
            found[code] = f
    return found


# ---------- sync: your own receipts, through your own signed-in Chrome ----------
#
# Like costco-cli for costco.com: Chrome runs with a profile kept just for this tool, and you sign in yourself
# when Costco asks. `sync` reads the session header the receipts page sends, keeps it in memory, and makes
# the same requests the page makes, from inside that tab. Chrome is closed again at the end.


HOME = os.path.expanduser(os.environ.get('COSTCO_AU_HOME', '~/.local/share/costco-au'))
PROFILE = os.path.join(HOME, 'chrome-profile')
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
RECEIPTS_PAGE = 'https://www.costco.com.au/my-account/receipts'


class Tab:
    """Just enough of the Chrome DevTools protocol (over a local WebSocket) to run JavaScript in a tab."""

    def __init__(self, ws_url):
        host, path = ws_url[len('ws://'):].split('/', 1)
        h, p = host.split(':')
        self.sock = socket.create_connection((h, int(p)), timeout=120)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET /{path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                           f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        reply = b''
        while b'\r\n\r\n' not in reply:
            reply += self.sock.recv(1)
        if not reply.startswith(b'HTTP/1.1 101'):
            sys.exit('Chrome refused the connection from this tool.')
        self.next_id = 0

    def _read(self, n):
        b = b''
        while len(b) < n:
            chunk = self.sock.recv(n - len(b))
            if not chunk:
                raise EOFError('Chrome closed the connection')
            b += chunk
        return b

    def _frame(self):
        msg = b''
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7f
            if n == 126:
                n = struct.unpack('>H', self._read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._read(8))[0]
            data = self._read(n)
            if b0 & 0x0f == 8:
                raise EOFError('Chrome closed the connection')
            if b0 & 0x0f in (9, 10):  # ping, pong
                continue
            msg += data
            if b0 & 0x80:
                return json.loads(msg)

    def wait_for(self, method, match, timeout=30):
        """Return the params of the first `method` event that `match(params)` accepts."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = self._frame()
            except socket.timeout:
                continue  # a quiet spell (someone typing a password); keep waiting until `timeout`
            if m.get('method') == method and match(m['params']):
                return m['params']
        return None

    def call(self, method, **params):
        self.next_id += 1
        data = json.dumps({'id': self.next_id, 'method': method, 'params': params}).encode()
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0xfe]) + struct.pack('>H', n) if n < 65536
                                 else bytes([0xff]) + struct.pack('>Q', n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        while True:
            m = self._frame()
            if m.get('id') == self.next_id:
                if 'error' in m:
                    raise RuntimeError(m['error'])
                return m['result']

    def js(self, expression):
        r = self.call('Runtime.evaluate', expression=expression, awaitPromise=True, returnByValue=True)
        if 'exceptionDetails' in r:
            raise RuntimeError(r['exceptionDetails'].get('exception', {}).get('description', r['exceptionDetails']))
        return r['result'].get('value')


def devtools(path, method='GET'):
    """Ask this tool's Chrome (on the random local port it wrote into its profile) for `path`; None if it isn't running."""
    try:
        with open(os.path.join(PROFILE, 'DevToolsActivePort')) as f:
            port = int(f.readline())
        req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', method=method)
        return json.load(urllib.request.urlopen(req, timeout=3))
    except (OSError, ValueError):
        return None


def chrome_tabs():
    return devtools('/json/list')


def start_chrome():
    if not os.path.exists(CHROME):
        sys.exit('Google Chrome is not in your Applications folder. Install it from google.com/chrome and try again.')
    os.makedirs(HOME, mode=0o700, exist_ok=True)
    # port 0: Chrome picks a free port and writes it to DevToolsActivePort, so nothing else can pose as it
    args = [CHROME, f'--user-data-dir={PROFILE}', '--remote-debugging-port=0', '--no-first-run',
            '--no-default-browser-check', RECEIPTS_PAGE]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(1)
        if chrome_tabs() is not None:
            return
    sys.exit('Chrome did not start. If the window for this tool is already open without it, quit Chrome and try again.')


def close_chrome():
    """Quit this tool's Chrome, which also closes its DevTools port."""
    v = devtools('/json/version')
    if v:
        try:
            Tab(v['webSocketDebuggerUrl']).call('Browser.close')
        except (OSError, EOFError):
            pass


def costco_tab():
    for t in chrome_tabs() or []:
        if t['type'] == 'page' and 'costco.com.au' in t['url']:
            return Tab(t['webSocketDebuggerUrl'])


def new_tab(url):
    return Tab(devtools(f'/json/new?{url}', method='PUT')['webSocketDebuggerUrl'])


def post(tab, auth, path, body):
    """POST to costco.com.au from inside the signed-in tab, with the page's own session."""
    r = tab.js("(async () => { const r = await fetch(%s, {method: 'POST', body: %s, headers: {"
               "'Content-Type': 'application/json', Accept: 'application/json', Authorization: %s}});"
               " return {status: r.status, body: await r.text()}; })()"
               % (json.dumps(f'/rest/v2/australia/users/current/{path}?lang=en_AU&curr=AUD'),
                  json.dumps(json.dumps(body)), json.dumps(auth)))
    if r['status'] != 200:
        sys.exit(f'costco.com.au answered {r["status"]} for {path}. Try again later, or run sync again to sign in.')
    return json.loads(r['body'])


# The same page turning as the browser snippet: each view's text is kept until the last page.
FLIP_BOOKLET = """(async () => {
  const pages = {}; let last = '';
  for (let n = 0; n < 40; n++) {
    await new Promise(r => setTimeout(r, 1800));
    pages[location.pathname] = document.body.innerText;
    if (location.pathname === last) break;
    last = location.pathname;
    document.querySelector('.j-button-next')?.click();
  }
  return pages;
})()"""


def sync():
    # None means this tool's Chrome isn't running; an empty list is Chrome still running with its window closed.
    # Not headless: headless Chrome gets the booklet's text-only view, which leaves out half the pages.
    if chrome_tabs() is None:
        start_chrome()
    try:
        tab = costco_tab() or new_tab(RECEIPTS_PAGE)
        tab.call('Network.enable')
        tab.call('Page.navigate', url=RECEIPTS_PAGE)
        # Read the session header off the page's own first account request. Signed out, the page redirects
        # to /login and asks for that page's data instead. Costco's sign-in lasts about 25 minutes, so
        # signing in here is the normal case, not an error.
        signed_in = lambda p: ('/rest/v2/australia/users/' in p['request']['url'] and '/users/anonymous' not in
                               p['request']['url'] and 'Authorization' in p['request']['headers'])
        ev = tab.wait_for('Network.requestWillBeSent', lambda p: signed_in(p) or '/metadata/login' in p['request']['url'],
                          timeout=40)
        if not ev or not signed_in(ev):
            print('Sign in to costco.com.au in the Chrome window that opened. Waiting up to 5 minutes...')
            ev = tab.wait_for('Network.requestWillBeSent', signed_in, timeout=300)
            if not ev:
                sys.exit('No sign-in after 5 minutes. Run sync again when you are ready.')
            time.sleep(3)
        auth = ev['request']['headers']['Authorization']
        tab.call('Network.disable')

        # every month the 30-day window touches: two, or three on 1 and 2 March
        cut = datetime.date.today() - datetime.timedelta(days=WINDOW_DAYS)
        month_list = [datetime.date.today().replace(day=1)]
        while month_list[-1] > cut.replace(day=1):
            month_list.append((month_list[-1] - datetime.timedelta(days=1)).replace(day=1))
        receipts = []
        for m in month_list:
            for summary in post(tab, auth, 'receipts', {'transactionMonth': f'{m:%Y-%m}', 'sortCode': '', 'source': 'inline'}).get('receiptsSummaryList') or []:
                if summary['recordType'] != 'SALE':
                    continue
                time.sleep(1)
                receipts.append(post(tab, auth, 'receipts/details', {'receiptNumber': summary['receiptNumber'], 'source': 'inline'}))
        write_private(os.path.join(HOME, 'receipts.json'), receipts)
        print(f'Saved {len(receipts)} receipts ({", ".join(f"{m:%b %Y}" for m in month_list)}).')

        url = booklet_url()
        btab = new_tab(url)
        time.sleep(4)
        pages = btab.js(FLIP_BOOKLET)
        btab.call('Page.close')
        write_private(os.path.join(HOME, 'booklet.json'), {'url': url, 'pages': pages})
        print(f'Saved the booklet ({len(parse_booklet(pages.values()))} items).')
    finally:
        close_chrome()


# ---------- commands ----------

def cmd_link(args):
    url = booklet_url()
    start, end = booklet_dates(url)
    print(url)
    if start:
        print(f'Valid {start:%d/%m/%Y} to {end:%d/%m/%Y}')


def cmd_check(args):
    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    url, texts = load_booklet(args.booklet)
    offers = parse_booklet(texts)
    if not offers:
        sys.exit(f'No offers found in {args.booklet}. Was it saved on the booklet page?')
    for extra in args.extra:
        m = re.fullmatch(r'(\d{4,8})=\$?(\d+(?:\.\d+)?)', extra)
        if not m:
            sys.exit(f'--extra {extra}: write the item number, "=", then the dollars off, like --extra 122000=8.00')
        offers[m.group(1)] = {'off': float(m.group(2)), 'price': None, 'name': 'shelf sign'}
    start, end = booklet_dates(url)
    if end and end < today:
        sys.exit(f'This booklet ended {end:%d/%m/%Y}. Run sync again (or save the current booklet) and check again.')
    if start and start > today:
        print(f'Note: this booklet starts {start:%d/%m/%Y}. Its prices are not in the warehouse yet.\n')
    receipts = [receipt_from_api(r) if isinstance(r, dict) else parse_receipt(r) for r in load_receipts(args.receipts)]
    claims, skipped, in_window = find_claims(receipts, offers, load_claimed(args.claimed), today)

    period = f' {start:%d/%m} to {end:%d/%m/%Y}' if start else ''
    print(f'Receipts from the last {WINDOW_DAYS} days: {len(in_window)}. Booklet{period}: {len(offers)} items.\n')
    total = 0.0
    if claims:
        members = sorted({c[0]['member'] for c in claims if c[0]['member']})
        print('Ask at the Membership counter' + (f' (member {", ".join(members)})' if members else '') + ':\n')
        print('| Item # | Qty | Bought | Item | Paid each | $ off each | Refund | Ask by |')
        print('|---|---|---|---|---|---|---|---|')
        for r, it, o, each in sorted(claims, key=lambda c: (c[0]['date'], c[1]['item'])):
            refund = it['qty'] * each
            total += refund
            # staff check the shelf price, so the special has to still be on too
            by = min(r['date'] + datetime.timedelta(days=WINDOW_DAYS), end or datetime.date.max)
            print(f"| {it['item']} | {it['qty']} | {r['date']:%d/%m/%Y} | {(it['name'] or o['name'])[:40]} | "
                  f"{it['paid']:.2f} | {each:.2f} | {refund:.2f} | {by:%d/%m/%Y} |")
        print()
    print(f'Total to ask for: ${total:.2f}')
    for r, it, why in skipped:
        print(f"  not counted: {it['item']} bought {r['date']:%d/%m}: {why}")

    if args.online:
        paid = {}
        for r in in_window:
            for it in r['items']:
                if it['item'] not in offers:
                    paid[it['item']] = max(paid.get(it['item'], 0), it['paid'])
        print(f'\nChecking costco.com.au for discounts and price cuts on {len(paid)} items (about {len(paid)} seconds)...')
        web = online_check(paid, today)
        if web:
            print('Worth a look. Not counted above: online prices and pack sizes can differ from the warehouse,')
            print('so check the shelf or ask at the counter.')
            for code, w in sorted(web.items()):
                deal = f"${w['off']:.2f} off online until {w['end'] or '?'}" if w['off'] else 'price cut online'
                now = f", now ${w['now']:.2f} online (you paid ${w['paid']:.2f})" if w['now'] is not None else ''
                print(f"  {code}  {deal}{now}  {w['name']}")
        else:
            print('Nothing cheaper online.')


def main(argv=None):
    p = argparse.ArgumentParser(prog='costco-au', description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('link', help='print the current In-Warehouse Savings booklet link')
    sub.add_parser('sync', help='save your recent receipts and the current booklet (opens Chrome; sign in if asked)')
    c = sub.add_parser('check', help='list what to ask for, from your receipts')
    c.add_argument('receipts', nargs='?', default=os.path.join(HOME, 'receipts.json'),
                   help='receipts file (default: the one sync saves; or costco-receipts.json from the snippet)')
    c.add_argument('booklet', nargs='?', default=os.path.join(HOME, 'booklet.json'),
                   help='booklet file (default: the one sync saves; or costco-booklet.json from the snippet)')
    c.add_argument('--claimed', help='CSV of refunds you already got (purchase_date,item)')
    c.add_argument('--extra', action='append', default=[], metavar='ITEM=OFF',
                   help='a special not in the booklet, such as a shelf sign: --extra 122000=8.00 (repeat for more)')
    c.add_argument('--online', action='store_true',
                   help='also look up costco.com.au discounts and price cuts on what you bought')
    c.add_argument('--today', help='pretend today is YYYY-MM-DD')
    args = p.parse_args(argv)
    {'link': cmd_link, 'sync': lambda a: sync(), 'check': cmd_check}[args.cmd](args)


if __name__ == '__main__':
    main()
