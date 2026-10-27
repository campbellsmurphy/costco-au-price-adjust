# First time using Terminal? Start here

This guide is for a Mac. It takes about 10 minutes the first time, then a minute or two each time after that. You don't need any coding knowledge or AI. You copy a line, paste it into Terminal and press Return.

You need:
- a Mac
- [Google Chrome](https://www.google.com/chrome/), installed in Applications
- your costco.com.au online login (the one you use to see your receipts)

## 1. Open Terminal

Press **Cmd + Space**, type `Terminal` and press **Return**. A window opens with a line ending in `%`. That is where you paste commands.

How it works:
- Paste a command with **Cmd + V**, then press **Return** to run it.
- Wait until the `%` line comes back before you paste the next command.
- Terminal only runs things on your Mac. Nothing you type here is sent to anyone.

## 2. Check you have Python

Paste this and press Return:

```bash
python3 --version
```

- If you see `Python 3.9` or a higher number, go to step 3.
- If a box asks you to install the **command line developer tools**, click **Install**. This is Apple's own free download and takes about 5 minutes. When it finishes, run `python3 --version` again.

## 3. Download the tool

Paste this whole line and press Return:

```bash
mkdir -p ~/costco-au && cd ~/costco-au && curl -fsSLO https://raw.githubusercontent.com/campbellsmurphy/costco-au-price-adjust/main/costco_au.py
```

This makes a folder called `costco-au` in your home folder and downloads one file into it, `costco_au.py`. That file is the whole tool. You can open it in TextEdit to read it.

## 4. Check for price adjustments

Run this whenever you want to check, for example once a week or when a new booklet comes out:

```bash
cd ~/costco-au && python3 costco_au.py sync && python3 costco_au.py check
```

A Chrome window opens. It uses a separate Chrome profile kept only for this tool, so your normal Chrome is not touched.

1. If Costco shows its login page, sign in there with your Costco email and password. If Costco sends you a code by SMS, type it in. Terminal says `Waiting up to 5 minutes...` while you do this. Costco's sign-in only lasts about 25 minutes, so expect to do this most times.
2. Then leave the window alone. It fetches your receipts from the last 30 days and the current In-Warehouse Savings booklet. After about 30 seconds it closes by itself.

Then you see something like this:

```
Receipts from the last 30 days: 3. Booklet 26/10 to 22/11/2026: 103 items.

Ask at the Membership counter (member 12345678901):

| Item # | Qty | Bought | Item | Paid each | $ off each | Refund | Ask by |
|---|---|---|---|---|---|---|---|
| 900002 | 2 | 10/10/2026 | EXAMPLE SOFT TISSUE 60X180 | 27.49 | 5.50 | 11.00 | 09/11/2026 |

Total to ask for: $11.00
```

If it says `Total to ask for: $0.00`, nothing you bought recently is on special. Check again when the next booklet starts.

If there is something to ask for, take the table to the Membership counter before the **Ask by** date. See [At the counter](../README.md#at-the-counter).

## Extras

Also check costco.com.au for discounts and price cuts on what you bought (takes about 30 seconds):

```bash
cd ~/costco-au && python3 costco_au.py check --online
```

Add a special you saw on a shelf sign but not in the booklet. Type the item number, then `=`, then the dollars off:

```bash
cd ~/costco-au && python3 costco_au.py check --extra 122000=8.00
```

## If something goes wrong

| You see | Do this |
|---|---|
| `command not found: python3` | Do step 2. |
| `No sign-in after 5 minutes` | Run step 4 again and sign in in the Chrome window when it opens. |
| `Google Chrome is not in your Applications folder` | Install Google Chrome from google.com/chrome, then try again. |
| `Chrome did not start` | Quit the Chrome window this tool opened (Chrome > Quit), then try again. |
| `Could not reach costco.com.au` | Check your internet connection, then try again. |
| `No such file or directory` | You are in the wrong folder. Start the command with `cd ~/costco-au &&` as shown. |
| `costco.com.au answered 401` (or another number) | Costco refused the request. Run step 4 again. If it keeps happening, Costco may have changed its website; please [open an issue](https://github.com/campbellsmurphy/costco-au-price-adjust/issues). |
| `This booklet ended` | Costco has not posted the next booklet yet. Try again in a day or two. |

## Update or remove the tool

To update to the newest version, run step 3 again.

To remove the tool, its separate Chrome profile and the receipts it saved:

```bash
rm -rf ~/costco-au ~/.local/share/costco-au
```

This deletes those two folders only. It does not touch your normal Chrome or your Costco account.

## Not on a Mac?

`sync` only works on a Mac for now. On Windows or Linux, use the [browser snippet](../README.md#or-use-it-without-sync-the-browser-snippet) to save your receipts and the booklet, then run the check. On Windows, install Python from [python.org](https://www.python.org/downloads/) and use `py` instead of `python3`.
