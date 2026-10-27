#!/usr/bin/env python3
"""Find Costco Australia price adjustments worth asking for.

When something you bought at a Costco Australia warehouse goes on special within about 30 days, you can
ask the Membership counter to refund the difference (at the warehouse's discretion). This compares your
receipts against the current In-Warehouse Savings booklet and lists what to ask for, with a date for each.

  costco-au link                                         print the current booklet link
  costco-au check costco-receipts.json costco-booklet.json   what to ask for
"""
import argparse
import csv
import datetime
import json
import re
import sys
import time
import urllib.error
import urllib.request

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


def load_booklet(path):
    """Read the file the snippet saves on the booklet: {'url', 'pages': {view: text}}."""
    data = json.load(open(path))
    pages = data.get('pages', data)
    return data.get('url', next(iter(pages), '')), list(pages.values())


def parse_booklet(texts):
    """Each offer reads: name lines, '$21', '99', 'After $5.50 off', 'Item 112472 | $0.20 per 100sheets'.

    Returns {item number: {'off', 'price', 'name'}}. Views overlap, so the first sighting wins.
    """
    offers = {}
    for text in texts:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for i in range(2, len(lines)):
            off = re.fullmatch(r'After \$([\d.]+) o(?:ff|ﬀ)', lines[i])
            dollars, cents = re.fullmatch(r'\$([\d,]+)', lines[i - 2]), re.fullmatch(r'\d{2}', lines[i - 1])
            if not (off and dollars and cents):
                continue
            name = []
            for l in reversed(lines[max(0, i - 6):i - 2]):
                if l.startswith(('Item', '*', '$', 'After')) or re.fullmatch(r'\d{2}', l) or len(l) > 60:
                    break
                name.insert(0, l)
            j = i + 1
            while j < len(lines) and lines[j].startswith('Item'):
                for num in re.findall(r'\b(\d{4,8})\b', lines[j].split('$')[0]):
                    offers.setdefault(num, {'off': float(off.group(1)),
                                            'price': float(dollars.group(1).replace(',', '') + '.' + cents.group(0)),
                                            'name': ' '.join(name)})
                j += 1
    return offers


# ---------- receipts ----------

def load_receipts(path):
    """Read the file the snippet saves on the receipts page: a list of {'text'}."""
    data = json.load(open(path))
    if isinstance(data, dict):
        data = [r for month in data.values() for r in (month or [])]
    return [r['text'] if isinstance(r, dict) else r for r in data]


def parse_receipt(text):
    """Pull the date, member number and shop lines out of one receipt's text."""
    when = re.search(r'(\d{2})/(\d{2})/(\d{4}) \d{2}:\d{2}', text)
    if not when:
        return None
    member = re.search(r'Member (\d+)', text)
    lines = text.split('\n')
    items = []
    for j, line in enumerate(lines):
        # "249314<tab>2x<tab>24.99<tab>49.98"; fuel is "29531<tab>44.11x" (decimal litres); returns end in " -"
        m = re.match(r'^(\d{4,8})\t(\d+)x\t([\d.]+)\t([\d.]+)( -)?', line)
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


def load_claimed(path):
    """Refunds you already got: CSV with purchase_date (YYYY-MM-DD) and item columns."""
    if not path:
        return set()
    return {(r['purchase_date'], r['item']) for r in csv.DictReader(open(path))}


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
                claims.append((r, it, o))
    return claims, skipped, in_window


# ---------- online discounts (opt in) ----------

def online_discounts(codes, today):
    """costco.com.au online discounts on the given item numbers: one request per item, a second apart."""
    found = {}
    for code in sorted(codes):
        body = get(PRODUCT.format(code=code))
        time.sleep(1)
        try:
            p = json.loads(body) if body else {}
        except ValueError:
            continue
        c = p.get('couponDiscount') or {}
        end = (c.get('discountEndDate') or '')[:10]
        if c.get('discountValue') and (not end or end >= today.isoformat()):
            found[code] = {'off': float(c['discountValue']), 'end': end, 'name': p.get('name', '')}
    return found


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
        num, off = extra.split('=')
        offers[num] = {'off': float(off), 'price': None, 'name': 'shelf sign'}
    start, end = booklet_dates(url)
    receipts = [parse_receipt(t) for t in load_receipts(args.receipts)]
    if end and end < today:
        print(f'Note: this booklet ended {end:%d/%m/%Y}. Save the current one first.\n')
    claims, skipped, in_window = find_claims(receipts, offers, load_claimed(args.claimed), today)

    period = f' {start:%d/%m} to {end:%d/%m/%Y}' if start else ''
    print(f'Receipts from the last {WINDOW_DAYS} days: {len(in_window)}. Booklet{period}: {len(offers)} items.\n')
    total = 0.0
    if claims:
        members = sorted({r['member'] for r, _, _ in claims if r['member']})
        print('Ask at the Membership counter' + (f' (member {", ".join(members)})' if members else '') + ':\n')
        print('| Item # | Qty | Bought | Item | Paid each | $ off each | Refund | Ask by |')
        print('|---|---|---|---|---|---|---|---|')
        for r, it, o in sorted(claims, key=lambda c: (c[0]['date'], c[1]['item'])):
            refund = it['qty'] * o['off']
            total += refund
            by = r['date'] + datetime.timedelta(days=WINDOW_DAYS)
            print(f"| {it['item']} | {it['qty']} | {r['date']:%d/%m/%Y} | {(it['name'] or o['name'])[:40]} | "
                  f"{it['paid']:.2f} | {o['off']:.2f} | {refund:.2f} | {by:%d/%m/%Y} |")
        print()
    print(f'Total to ask for: ${total:.2f}')
    for r, it, why in skipped:
        print(f"  not counted: {it['item']} bought {r['date']:%d/%m}: {why}")

    if args.online:
        codes = {it['item'] for r in in_window for it in r['items'] if it['item'] not in offers}
        print(f'\nChecking costco.com.au for online discounts on {len(codes)} items (about {len(codes)} seconds)...')
        web = online_discounts(codes, today)
        if web:
            print('Online discounts on things you bought. Not counted above: online prices and pack sizes can')
            print('differ from the warehouse, so check the shelf or ask at the counter.')
            for code, w in sorted(web.items()):
                print(f"  {code}  ${w['off']:.2f} off online until {w['end'] or '?'}  {w['name']}")
        else:
            print('None found.')


def main(argv=None):
    p = argparse.ArgumentParser(prog='costco-au', description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('link', help='print the current In-Warehouse Savings booklet link')
    c = sub.add_parser('check', help='list what to ask for, from your receipts')
    c.add_argument('receipts', help='costco-receipts.json saved by the snippet')
    c.add_argument('booklet', help='costco-booklet.json saved by the snippet')
    c.add_argument('--claimed', help='CSV of refunds you already got (purchase_date,item)')
    c.add_argument('--extra', nargs='*', default=[], metavar='ITEM=OFF',
                   help='specials not in the booklet, such as a shelf sign: 122000=8.00')
    c.add_argument('--online', action='store_true', help='also look up costco.com.au online discounts')
    c.add_argument('--today', help='pretend today is YYYY-MM-DD')
    args = p.parse_args(argv)
    {'link': cmd_link, 'check': cmd_check}[args.cmd](args)


if __name__ == '__main__':
    main()
