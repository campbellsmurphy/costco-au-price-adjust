# costco-au-price-adjust

Check your Costco Australia receipts against the current In-Warehouse Savings booklet. Find out what to ask the Membership counter to refund.

If something you bought goes on special soon after you bought it, you can ask for the difference back. Costco Australia's own [Pricing Adjustment Policy](https://www.costco.com.au/member-care/refunds-and-return/pricing-adjustment-policy) gives online orders 30 days. For warehouse purchases it says to ask at the membership counter, and refunds are at the warehouse's discretion. In practice members ask within about 30 days. This tool compares the two lists for you and gives you a table to show at the counter.

```
Receipts from the last 30 days: 3. Booklet 26/10 to 22/11/2026: 103 items.

Ask at the Membership counter (member 12345678901):

| Item # | Qty | Bought | Item | Paid each | $ off each | Refund | Ask by |
|---|---|---|---|---|---|---|---|
| 112472 | 2 | 10/10/2026 | KLEENEX BATH TISS 60X180 | 27.49 | 5.50 | 11.00 | 09/11/2026 |

Total to ask for: $11.00
  not counted: 173354 bought 10/10: the discount was already taken at the till
```

The tools I could find for this ([costco-cli](https://github.com/mdkocher/costco-cli), [costco-price-match](https://github.com/awsdataarchitect/costco-price-match) and others) work with costco.com in the US and Canada. Costco Australia runs on a different system: the receipts come from a different API, it needs a separate account, and the booklet is a Joomag flipbook. So this one is for Australian members. If you know of another one, open an issue.

## Not affiliated with Costco

This is an unofficial personal project. It is not affiliated with, endorsed by or supported by Costco Wholesale Australia. Costco's website and booklet can change at any time and break it.

Read Costco's [website terms](https://www.costco.com.au/terms-and-conditions) yourself before you use it. They allow personal, non-commercial use, and they restrict automated tools. The tool is built to stay close to normal browsing:

- **You sign in yourself, and only to your own account.** The tool never sees or stores your password.
- **There are two ways to get your data, and both stay on your computer.**
  - The browser snippet reads the receipts the page shows you, one at a time.
  - `costco-au sync` asks for your receipts directly. It makes the same requests the My Warehouse Receipts page makes, from inside your signed-in Chrome. It waits a second between receipts. These are undocumented Costco endpoints, so `sync` is the further of the two from ordinary browsing.
- **Few requests.** A sync is a few dozen requests: two months of receipts and one booklet. Online discount lookups (`--online`) are off unless you ask, and space out one item per second.
- **Nothing from Costco is in this repository.** No booklet pages, prices or product data.
- **Personal use only.** Don't run it for other people, don't host it as a service and don't sell it.

Refunds are at the warehouse's discretion. A line in this table means "worth asking about", not "owed to you". Use at your own risk; see the [licence](LICENSE).

## Install

You need Python 3.9 or newer (macOS and most Linux systems have it) and a desktop browser.

```bash
pipx install git+https://github.com/campbellsmurphy/costco-au-price-adjust
```

Or download `costco_au.py` and run it with `python3 costco_au.py`.

## Use it: sync (macOS, Google Chrome)

```bash
costco-au login    # a Chrome window opens: sign in to costco.com.au yourself, then close it
costco-au sync     # saves this and last month's receipts, and the current booklet
costco-au check    # what to ask for
```

How `sync` works:
- `login` opens Chrome with a profile kept only for this tool (`~/.local/share/costco-au/chrome-profile`). Your normal Chrome is left alone.
- `sync` reuses that sign-in in the background. It opens the receipts page and reads the session header the page itself sends. Then it requests your receipts and opens the booklet the way the page would.
- The header is held in memory only for the length of the sync. Receipts and the booklet are saved to `~/.local/share/costco-au/`.
- When Costco ends the session, `sync` says so; run `costco-au login` again.

## Or use it without sync: the browser snippet

This works in any desktop browser, with nothing installed but Python. You do steps 1 and 2 in your browser, and step 3 in a terminal. Both browser steps use the same snippet, [`costco-au-snippet.js`](costco-au-snippet.js). Open it, select all and copy.

**1. Save the booklet.** Open costco.com.au/warehouse-savings and click through to the booklet, or run `costco-au link` to get the link. Wait for it to load. Open the browser console:
- Chrome: View > Developer > JavaScript Console.
- Safari: turn on Settings > Advanced > Show features for web developers, then Develop > Show JavaScript Console.

Paste the snippet and press Enter. It turns the pages for about 15 seconds and saves `costco-booklet.json` to your Downloads folder.

**2. Save your receipts.** Log in at costco.com.au and open My Account > Warehouse Receipts (`/my-account/receipts`). Paste the same snippet into the console. It opens this month's and last month's receipts and saves `costco-receipts.json`.

Browsers warn you about pasting code into the console, and you should take that warning seriously. Read the snippet first. It is short, and all it does is read the page and save a file.

**3. Check.**

```bash
costco-au check ~/Downloads/costco-receipts.json ~/Downloads/costco-booklet.json
```

Options:

| Option | What it does |
|---|---|
| `--extra 122000=8.00` | Add a special that isn't in the booklet, such as a shelf sign you photographed. The format is item number = dollars off. |
| `--claimed refunds.csv` | Skip lines you have already been refunded. The CSV needs the columns `purchase_date,item`, with dates as YYYY-MM-DD. Refund receipts don't show on the website, so keep this yourself. |
| `--online` | Also look up costco.com.au online discounts on what you bought. They are listed separately, because online prices and pack sizes often differ from the warehouse. |
| `--today 2026-10-07` | Run as if it were another day. |

## At the counter

Bring the table, on paper or your phone, and your membership card. The receipt is on your account, so staff can look it up. Ask before the **Ask by** date. Staff check the current price on the shelf. If the item has sold out or the special has ended, they may say no.

## What it doesn't catch

- **Unadvertised markdowns and shelf-only specials.** Add the ones you see with `--extra`.
- **Lines where the till already took a discount** (TPD, MVM and IRC lines on the receipt). These are listed as "not counted".
- **"Item various" offers** (clothing and other ranges with no single item number).
- **Online orders.** These follow Costco's online 30-day policy through Member Care, not the counter.

## How it works

- `costco-au link` reads the booklet link from the same costco.com.au page data the website uses.
- `sync` talks to Chrome over its local DevTools port, using a small built-in client. It saves the receipt data the website receives, and the text the booklet viewer shows.
- The snippet saves the text the booklet viewer shows, and the text of each receipt as displayed.
- `costco_au.py` matches item numbers between the two files. It skips receipt lines that already carry a discount, refunds, fuel, and anything older than 30 days.

It uses only the Python standard library. Run the tests with `python3 -m unittest tests/test_costco_au.py`.

## Licence

MIT
