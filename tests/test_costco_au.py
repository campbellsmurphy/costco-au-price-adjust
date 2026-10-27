import datetime
import os
import stat
import tempfile
import unittest

import costco_au as c

# Fictional booklet text in the layouts the booklet viewer shows. Item numbers, names and prices are made up.
BOOKLET = """Example Farm
Crunchy Granola
1.3kg
$11
99
After $3 oﬀ
Item 900001 | $0.92 per 100g
Example Co
Soft Tissue
60 x 180 sheets
$21
99
After $5.50 off
Item 900002 | $0.20 per 100sheets
* Available in select warehouses
Example Vision
75" Television
$1,449
99
After $1,000 oﬀ
Item 900003
Item 900004
Example Estate
Shiraz 750ml
$12 oﬀ
Item 900005 | Item 900006
*Not available in QLD or SA warehouses
Terms and Conditions: Only valid in Costco warehouses located in Australia and while stock lasts."""

RECEIPT = """In-Warehouse Receipt
Member 00000000000
EXAMPLE SOFT TISSUE 60X180
900002\t2x\t27.49\t54.98
EXAMPLE CHICKEN
900010\t1x\t7.99\t7.99
EXAMPLE GRANOLA
900001\t1x\t14.99\t14.99
TPD EXAMPLE GRANOLA
SBS 01.10.26-11.10.26
900011\t1x\t3.00\t3.00-
EXAMPLE TELEVISION
900003\t1x\t1499.99\t1499.99
EXAMPLE ULP91
900012\t44.11x\t1.54\t67.93
TOTAL NUMBER OF ITEMS SOLD = 5
10/10/2026 05:12:00 pm 108 000 0000 000
"""


class Booklet(unittest.TestCase):
    def test_offers(self):
        o = c.parse_booklet([BOOKLET])
        self.assertEqual(o['900002'], {'off': 5.5, 'price': 21.99, 'name': 'Example Co Soft Tissue 60 x 180 sheets'})
        self.assertEqual(o['900001']['off'], 3.0)
        self.assertEqual((o['900003']['off'], o['900003']['price']), (1000.0, 1449.99))  # comma in both
        self.assertIn('900004', o)

    def test_offer_without_price(self):
        o = c.parse_booklet([BOOKLET])
        self.assertEqual(o['900005'], {'off': 12.0, 'price': None, 'name': 'Example Estate Shiraz 750ml'})
        self.assertIn('900006', o)

    def test_spaced_amounts(self):
        o = c.parse_booklet(["Example Thing\n$ 4\n99\nAfter $ 1.50 off\nItem 900020"])
        self.assertEqual((o['900020']['off'], o['900020']['price']), (1.5, 4.99))

    def test_dates_from_link(self):
        url = 'https://viewer.joomag.com/in-warehouse-savings-26-10-26-22-11-26/0314771001791333283'
        self.assertEqual(c.booklet_dates(url), (datetime.date(2026, 10, 26), datetime.date(2026, 11, 22)))


class Check(unittest.TestCase):
    def setUp(self):
        self.offers = c.parse_booklet([BOOKLET])
        self.receipt = c.parse_receipt(RECEIPT)
        self.today = datetime.date(2026, 10, 27)

    def test_receipt(self):
        r = self.receipt
        self.assertEqual(r['date'], datetime.date(2026, 10, 10))
        self.assertEqual(r['member'], '00000000000')
        # the discount line ("3.00-") and fuel (decimal litres) are not purchases
        self.assertEqual([i['item'] for i in r['items']], ['900002', '900010', '900001', '900003'])
        self.assertTrue(r['items'][2]['discounted'])

    def test_claims(self):
        claims, skipped, in_window = c.find_claims([self.receipt], self.offers, set(), self.today)
        # television: paid 1499.99, booklet price 1449.99, so $50 back, not the $1,000 the booklet takes off
        self.assertEqual([(it['item'], each) for _, it, _, each in claims], [('900002', 5.5), ('900003', 50.0)])
        self.assertEqual([why for _, _, why in skipped], ['the discount was already taken at the till'])
        self.assertEqual(len(in_window), 1)

    def test_paid_booklet_price_already(self):
        offers = {'900002': {'off': 5.5, 'price': 27.49, 'name': ''}}
        claims, skipped, _ = c.find_claims([self.receipt], offers, set(), self.today)
        self.assertEqual(claims, [])
        self.assertEqual([why for _, _, why in skipped], ['you already paid the booklet price or less'])

    def test_already_refunded(self):
        claims, skipped, _ = c.find_claims([self.receipt], self.offers, {('2026-10-10', '900002')}, self.today)
        self.assertEqual([it['item'] for _, it, _, _ in claims], ['900003'])
        self.assertIn('already refunded', [why for _, _, why in skipped])

    def test_refund_receipt_ignored(self):
        refund = "Member 00000000000\n900030\t1x\t24.99\t24.99 - 1\nTPD EXAMPLE\n900031\t1x\t5.01\t5.01 1\n" \
                 "TOTAL NUMBER OF ITEMS SOLD = -1\n22/10/2026 04:16:00 pm 108 000 0000 000\n"
        self.assertIsNone(c.parse_receipt(refund))

    def test_api_receipt(self):
        line = lambda n, kind, qty, price: {'type': kind, 'itemNumber': n, 'qty': qty, 'sellPrice': {'value': price},
                                            'itemDescription': ['ITEM ' + n]}
        r = c.receipt_from_api({'recordType': 'SALE', 'transactionDateTime': '2026-10-22T04:52:00.000Z',
                                'membershipNumber': '00000000000',
                                'lines': [line('900040', 'CAPTURED', 1.0, 59.99), line('900041', 'COUPON', 1.0, 12.0),
                                          line('900002', 'CAPTURED', 2.0, 27.49), line('900012', 'CAPTURED', 25.78, 1.54)]})
        self.assertEqual(r['date'], datetime.date(2026, 10, 22))
        self.assertEqual([(i['item'], i['qty'], i['discounted']) for i in r['items']],
                         [('900040', 1, True), ('900002', 2, False)])
        self.assertIsNone(c.receipt_from_api({'recordType': 'REFUND'}))

    def test_online_finding(self):
        today = datetime.date(2026, 10, 20)
        prod = lambda price, off=None, end=None: {'name': 'Thing', 'price': {'value': price},
                                                  'couponDiscount': {'discountValue': off, 'discountEndDate': end} if off else None}
        self.assertIsNone(c.online_finding(prod(62.99), 59.99, today))                     # dearer online: nothing
        self.assertEqual(c.online_finding(prod(54.99), 59.99, today)['now'], 54.99)          # plain price cut
        self.assertEqual(c.online_finding(prod(62.99, 13, '2026-10-25T12:59:00Z'), 59.99, today)['off'], 13.0)
        self.assertIsNone(c.online_finding(prod(62.99, 13, '2026-10-01T12:59:00Z'), 59.99, today))  # ended
        self.assertIsNone(c.online_finding({}, 59.99, today))                               # not sold online

    def test_outside_30_days(self):
        claims, _, in_window = c.find_claims([self.receipt], self.offers, set(), datetime.date(2026, 11, 10))
        self.assertEqual((claims, in_window), ([], []))


class Files(unittest.TestCase):
    def test_saved_files_are_private(self):
        with tempfile.TemporaryDirectory() as d:
            c.HOME = os.path.join(d, 'costco-au')
            path = os.path.join(c.HOME, 'receipts.json')
            os.makedirs(c.HOME)
            open(path, 'w').close()
            os.chmod(path, 0o644)  # left over from an older version
            c.write_private(path, [])
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(c.HOME).st_mode), 0o700)


if __name__ == '__main__':
    unittest.main()
