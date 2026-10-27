import datetime
import unittest

import costco_au as c

# Made-up booklet text in the layout the snippet saves (name lines, $dollars, cents, After $X off, Item line).
BOOKLET = """Brookfarm
Supergrains Granola
1.3kg
$11
99
After $3 oﬀ
Item 173354 | $0.92 per 100g
Kleenex
Bath Tissue
60 x 180 sheets
$21
99
After $5.50 off
Item 112472 | $0.20 per 100sheets
* Available in select warehouses
Sony
Bravia 75" TV
$1,449
99
After $350 oﬀ
Item 2026203
Item 2026204
Terms and Conditions: Only valid in Costco warehouses located in Australia and while stock lasts."""

RECEIPT = """In-Warehouse Receipt
Member 00000000000
KLEENEX BATH TISS 60X180
112472\t2x\t27.49\t54.98
KS ROTISSERIE CHICKEN
11080\t1x\t7.99\t7.99
BROOKFARM GRANOLA
173354\t1x\t14.99\t14.99
TPD BROOKFARM GRANOLA
SBS 01.10.26-11.10.26
999999\t1x\t3.00\t3.00-
KIRKLAND ULP91
29531\t44.11x\t1.54\t67.93
TOTAL NUMBER OF ITEMS SOLD = 4
10/10/2026 05:12:00 pm 108 000 0000 000
"""


class Booklet(unittest.TestCase):
    def test_offers(self):
        o = c.parse_booklet([BOOKLET])
        self.assertEqual(o['112472'], {'off': 5.5, 'price': 21.99, 'name': 'Kleenex Bath Tissue 60 x 180 sheets'})
        self.assertEqual(o['173354']['off'], 3.0)
        self.assertEqual(o['2026203']['price'], 1449.99)
        self.assertIn('2026204', o)

    def test_dates_from_link(self):
        url = 'https://viewer.joomag.com/in-warehouse-savings-26-10-26-22-11-26/0314771001791333283'
        self.assertEqual(c.booklet_dates(url), (datetime.date(2026, 10, 26), datetime.date(2026, 11, 22)))


class Check(unittest.TestCase):
    def setUp(self):
        self.offers = c.parse_booklet([BOOKLET])
        self.receipt = c.parse_receipt(RECEIPT)

    def test_receipt(self):
        r = self.receipt
        self.assertEqual(r['date'], datetime.date(2026, 10, 10))
        self.assertEqual(r['member'], '00000000000')
        self.assertEqual([i['item'] for i in r['items']], ['112472', '11080', '173354', '999999'])  # fuel skipped
        self.assertTrue(r['items'][2]['discounted'])

    def test_claims(self):
        claims, skipped, in_window = c.find_claims([self.receipt], self.offers, set(), datetime.date(2026, 10, 27))
        self.assertEqual([(it['item'], it['qty'] * o['off']) for _, it, o in claims], [('112472', 11.0)])
        self.assertEqual([why for _, _, why in skipped], ['the discount was already taken at the till'])
        self.assertEqual(len(in_window), 1)

    def test_already_refunded(self):
        claims, skipped, _ = c.find_claims([self.receipt], self.offers, {('2026-10-10', '112472')}, datetime.date(2026, 10, 27))
        self.assertEqual(claims, [])
        self.assertIn('already refunded', [why for _, _, why in skipped])

    def test_refund_receipt_ignored(self):
        refund = "Member 00000000000\n249314\t1x\t24.99\t24.99 - 1\nTPD CHAMPION BOXER\n286845\t1x\t5.01\t5.01 1\n" \
                 "TOTAL NUMBER OF ITEMS SOLD = -1\n22/10/2026 04:16:00 pm 108 000 0000 000\n"
        self.assertIsNone(c.parse_receipt(refund))

    def test_api_receipt(self):
        line = lambda n, kind, qty, price: {'type': kind, 'itemNumber': n, 'qty': qty, 'sellPrice': {'value': price},
                                            'itemDescription': ['ITEM ' + n]}
        r = c.receipt_from_api({'recordType': 'SALE', 'transactionDateTime': '2026-10-22T04:52:00.000Z',
                                'membershipNumber': '00000000000',
                                'lines': [line('11356', 'CAPTURED', 1.0, 59.99), line('284856', 'COUPON', 1.0, 12.0),
                                          line('112472', 'CAPTURED', 2.0, 27.49), line('29531', 'CAPTURED', 25.78, 1.54)]})
        self.assertEqual(r['date'], datetime.date(2026, 10, 22))
        self.assertEqual([(i['item'], i['qty'], i['discounted']) for i in r['items']],
                         [('11356', 1, True), ('112472', 2, False)])
        self.assertIsNone(c.receipt_from_api({'recordType': 'REFUND'}))

    def test_outside_30_days(self):
        claims, _, in_window = c.find_claims([self.receipt], self.offers, set(), datetime.date(2026, 11, 10))
        self.assertEqual((claims, in_window), ([], []))


if __name__ == '__main__':
    unittest.main()
