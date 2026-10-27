// costco-au-price-adjust browser snippet.
// Paste into the browser console (View > Developer > JavaScript Console) on either page:
//   1. the In-Warehouse Savings booklet (the viewer.joomag.com link on costco.com.au/warehouse-savings)
//      -> saves costco-booklet.json
//   2. your receipts, costco.com.au/my-account/receipts (logged in)
//      -> saves costco-receipts.json (this month and last month)
// It only reads what the page already shows you, at about the speed you would click, and saves a file
// to your Downloads folder. Nothing is sent anywhere.
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const save = (name, data) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/json' }));
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  };

  if (location.host === 'viewer.joomag.com') {
    // flip through the booklet; each view's text is kept, so every page is captured once
    const pages = {};
    let last = '';
    for (let n = 0; n < 40; n++) {
      await sleep(1800);
      pages[location.pathname] = document.body.innerText;
      if (location.pathname === last) break;
      last = location.pathname;
      document.querySelector('.j-button-next')?.click();
    }
    save('costco-booklet.json', { url: location.href.replace(/\/p\d+$/, ''), pages });
    return console.log(`Saved costco-booklet.json (${Object.keys(pages).length} views).`);
  }

  if (location.host.endsWith('costco.com.au') && location.pathname.includes('/my-account/receipts')) {
    const dialog = () => document.querySelector('.cdk-dialog-container');
    const buttons = text => [...document.querySelectorAll('button')].filter(b => b.innerText.trim() === text);
    const close = async () => { buttons('Close')[0]?.click(); for (let k = 0; k < 20 && dialog(); k++) await sleep(100); };
    const select = document.querySelector('select');
    if (!select) return console.log('No month list found. Wait for the receipts to load and paste again.');
    const receipts = [];
    // the 30-day window never reaches further back than last month
    for (const label of [...select.options].slice(0, 2).map(o => o.text.trim())) {
      await close();
      select.selectedIndex = [...select.options].findIndex(o => o.text.trim() === label);
      select.dispatchEvent(new Event('change', { bubbles: true }));
      await sleep(3000);
      const count = buttons('View Receipt').length;
      for (let i = 0; i < count; i++) {
        buttons('View Receipt')[i].click();
        let d = null;
        for (let k = 0; k < 40; k++) { await sleep(150); d = dialog(); if (d && /Items Sold|TOTAL NUMBER OF ITEMS/i.test(d.innerText)) break; }
        if (d) receipts.push({ month: label, text: d.innerText });
        await close();
      }
      console.log(`${label}: ${count} receipts`);
    }
    save('costco-receipts.json', receipts);
    return console.log(`Saved costco-receipts.json (${receipts.length} receipts).`);
  }

  console.log('Open the In-Warehouse Savings booklet or costco.com.au/my-account/receipts, then paste this again.');
})();
