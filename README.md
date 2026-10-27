# costco-au-price-adjust

Check your Costco Australia receipts against the current In-Warehouse Savings booklet. Find out what to ask the Membership counter to refund.

**Never used Terminal? Follow the [step-by-step guide for first-time users](docs/first-time-terminal.md).** You don't need coding knowledge or AI.

If something you bought goes on special soon after you bought it, you can ask for the difference back. Costco Australia's own [Pricing Adjustment Policy](https://www.costco.com.au/member-care/refunds-and-return/pricing-adjustment-policy) gives online orders 30 days. For warehouse purchases it says to ask at the membership counter, and refunds are at the warehouse's discretion. In practice members ask within about 30 days. This tool compares the two lists for you and gives you a table to show at the counter.

```
Receipts from the last 30 days: 3. Booklet 26/10 to 22/11/2026: 103 items.

Ask at the Membership counter (member 12345678901):

| Item # | Qty | Bought | Item | Paid each | $ off each | Refund | Ask by |
|---|---|---|---|---|---|---|---|
| 900002 | 2 | 10/10/2026 | EXAMPLE SOFT TISSUE 60X180 | 27.49 | 5.50 | 11.00 | 09/11/2026 |

Total to ask for: $11.00
  not counted: 900001 bought 10/10: the discount was already taken at the till
```

The tools I could find for this ([costco-cli](https://github.com/mdkocher/costco-cli), [costco-price-match](https://github.com/awsdataarchitect/costco-price-match) and others) work with costco.com in the US and Canada. Costco Australia runs on a different system: the receipts come from a different API, it needs a separate account, and the booklet is a Joomag flipbook. So this one is for Australian members. If you know of another one, open an issue.

## Not affiliated with Costco

This is an unofficial personal project. It is not affiliated with, endorsed by or supported by Costco Wholesale Australia. Costco's website and booklet can change at any time and break it.

Read Costco's [website terms](https://www.costco.com.au/terms-and-conditions) yourself before you use it. They allow personal, non-commercial use, and they restrict automated tools. The tool is built to stay close to normal browsing:

- **You sign in yourself, and only to your own account.** The tool never sees or stores your password.
- **There are two ways to get your data, and both stay on your computer.**
  - The browser snippet reads the receipts the page shows you, one at a time.
  - `sync` asks for your receipts directly. It makes the same requests the My Warehouse Receipts page makes, from inside your signed-in Chrome. It waits a second between receipts. These are undocumented Costco endpoints, so `sync` is the further of the two from ordinary browsing.
- **Few requests.** A sync is a few dozen requests: the last 30 days of receipts and one booklet. Online lookups (`--online`) are off unless you ask, and space out one item per second. `link` and `--online` identify themselves to costco.com.au as this tool.
- **Your saved files are private to your Mac account.** They hold your member number and a masked card number, so the tool saves them readable only by you. The snippet saves to your Downloads folder instead; delete those two files when you are done.
- **While `sync` runs, its Chrome is open to other programs on your Mac.** It listens on a random local port that the rest of your network can't reach, and `sync` quits that Chrome when it finishes.
- **Nothing from Costco is in this repository.** No booklet pages, prices or product data.
- **Personal use only.** Don't run it for other people, don't host it as a service and don't sell it.

Refunds are at the warehouse's discretion. A line in this table means "worth asking about", not "owed to you". Use at your own risk; see the [licence](LICENSE).

## Install

The tool is one file, `costco_au.py`, and needs Python 3.9 or newer. On a Mac, `python3` asks to install Apple's free command line developer tools the first time; say yes. [The first-time guide](docs/first-time-terminal.md) walks through it.

```bash
curl -fsSLO https://raw.githubusercontent.com/campbellsmurphy/costco-au-price-adjust/main/costco_au.py
python3 costco_au.py --help
```

If you use pipx, `pipx install git+https://github.com/campbellsmurphy/costco-au-price-adjust` installs it as a `costco-au` command instead. The examples below use `python3 costco_au.py`.

## Use it: sync (macOS, Google Chrome)

```bash
python3 costco_au.py sync     # saves the last 30 days of receipts and the current booklet
python3 costco_au.py check    # what to ask for
```

How `sync` works:
- It opens Chrome with a profile kept only for this tool (`~/.local/share/costco-au/chrome-profile`). Your normal Chrome is left alone.
- If Costco asks you to sign in, sign in in that window and `sync` carries on. Costco's sign-in only lasts about 25 minutes, so expect to sign in most times.
- The window stays open for about 30 seconds and then closes. It doesn't run hidden, because hidden (headless) Chrome gets a text-only booklet that leaves out half the pages.
- In that window it opens the receipts page and reads the session header the page itself sends. It holds the header in memory only, makes the same requests the page makes, and turns through the booklet.
- Receipts and the booklet are saved to `~/.local/share/costco-au/`.

## Or use it without sync: the browser snippet

This works in any desktop browser on any computer, with nothing installed but Python. You do steps 1 and 2 in your browser, and step 3 in a terminal. Both browser steps use the same snippet, [`costco-au-snippet.js`](costco-au-snippet.js). Open it, select all and copy.

**1. Save the booklet.** Open costco.com.au/warehouse-savings and click through to the booklet, or run `python3 costco_au.py link` to get the link. Wait for it to load. Open the browser console:
- Chrome: View > Developer > JavaScript Console.
- Safari: turn on Settings > Advanced > Show features for web developers, then Develop > Show JavaScript Console.

Paste the snippet and press Enter. It turns the pages for about 15 seconds and saves `costco-booklet.json` to your Downloads folder.

**2. Save your receipts.** Log in at costco.com.au and open My Account > Warehouse Receipts (`/my-account/receipts`). Paste the same snippet into the console. It opens the last 30 days of receipts and saves `costco-receipts.json`.

Browsers warn you about pasting code into the console, and you should take that warning seriously. Read the snippet first. It is short, and all it does is read the page and save a file. Chrome and Firefox make you type `allow pasting` before the first paste.

**3. Check.**

```bash
python3 costco_au.py check ~/Downloads/costco-receipts.json ~/Downloads/costco-booklet.json
```

Receipts file first, booklet file second. On Windows, use `py` instead of `python3`.

Options:

| Option | What it does |
|---|---|
| `--extra 122000=8.00` | Add a special that isn't in the booklet, such as a shelf sign you photographed. The format is item number = dollars off. Repeat it for more than one. |
| `--claimed refunds.csv` | Skip lines you have already been refunded. The CSV needs the columns `purchase_date,item`, with dates as YYYY-MM-DD. Refund receipts don't show on the website, so keep this yourself. |
| `--online` | Also look up what you bought on costco.com.au. It flags a live "$ off", or an online price (after any discount) below what you paid. Results are listed separately, because online prices usually run a few dollars above the warehouse and pack sizes can differ. |
| `--today 2026-10-07` | Run as if it were another day. |

## At the counter

Bring the table, on paper or your phone, and your membership card. The receipt is on your account, so staff can look it up. Ask before the **Ask by** date: 30 days after you bought it, or the day the booklet ends if that comes first. Staff check the current price on the shelf. If the item has sold out or the special has ended, they may say no.

The **Refund** column is never more than the gap between what you paid and the booklet price, even when the booklet's "$ off" is bigger.

## What it doesn't catch

- **Unadvertised markdowns and shelf-only specials.** Add the ones you see with `--extra`.
- **Lines where the till already took a discount** (TPD, MVM and IRC lines on the receipt). These are listed as "not counted".
- **"Item various" offers** (clothing and other ranges with no single item number).
- **Online orders.** These follow Costco's online 30-day policy through Member Care, not the counter.

## How it works

- `costco-au link` reads the booklet link from the same costco.com.au page data the website uses.
- `sync` talks to Chrome over its local DevTools port, using a small built-in client. It saves the receipt data the website receives, and the text the booklet viewer shows. Purchase dates use Sydney time, which can shift a late evening purchase in WA, QLD or SA by a day.
- The snippet saves the text the booklet viewer shows, and the text of each receipt as displayed.
- `costco_au.py` matches item numbers between the two files. It skips receipt lines that already carry a discount, refunds, fuel, and anything older than 30 days.

It uses only the Python standard library. Run the tests with `python3 -m unittest tests/test_costco_au.py`; the test data is made up.

## Licence

MIT
