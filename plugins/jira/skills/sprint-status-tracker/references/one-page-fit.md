# Keeping the tracker to one page

`render_tracker.py` ships with CSS already tuned to fit ~22-24 tickets across
4 groups on one A4-landscape page. Always verify this on the actual output
rather than assuming it still holds — ticket counts, title lengths, and group
counts all vary.

## Preflight: is verification even available here?

Verification needs Playwright's Chromium (for the PDF) and poppler's `pdfinfo` /
`pdftoppm` (for the page count and the rasterised look). Both are present in
Claude's analysis sandbox and often absent on a local machine, so **check before
you rely on them**:

```bash
node -e "require('playwright').chromium.launch().then(b=>b.close()).then(
  ()=>console.log('PLAYWRIGHT_OK'),
  e=>{console.log('PLAYWRIGHT_MISSING:', e.message.split('\n')[0]); process.exit(1)})" \
  2>/dev/null || echo PLAYWRIGHT_MISSING
command -v pdfinfo >/dev/null && echo POPPLER_OK || echo POPPLER_MISSING
```

Then take the matching branch:

- **Both OK** — run the full verification below. This is the only path that ends
  with you saying the page was verified.
- **Playwright OK, poppler missing** — you can't count PDF pages, but you can ask
  the browser directly whether the content overflows one page. Use the height
  measurement in "Measure instead of counting" below. Tell the user you checked
  overflow by measurement rather than by rendering a PDF.
- **Playwright missing** — you cannot verify the fit at all. Deliver the HTML and
  **say so plainly in your reply**: the one-page fit is unverified, and a dataset
  of this size may overflow. Offer the fix rather than performing it —
  `npx playwright install chromium` (plus poppler via `brew install poppler` or
  `apt install poppler-utils`) enables verification on the next run.

**Never report the page as verified when the preflight failed.** An unverified
tracker described as one page is worse than one honestly flagged, because the
reader only finds out at the printer.

## Verify

After rendering:

```bash
node -e "
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + process.cwd() + '/output.html');
  await page.pdf({ path: 'output.pdf', format: 'A4', landscape: true, printBackground: true });
  await browser.close();
})();
"
pdfinfo output.pdf | grep Pages
```

Don't pass an explicit `executablePath` — the installed browser lives under a
versioned directory (e.g. `/opt/pw-browsers/chromium-1194/...`) that will
drift across environments and shouldn't be hardcoded. Playwright's default
`chromium.launch()` resolves its own bundled browser correctly without it.

If `Pages: 1`, render it to a JPEG and actually look at it before calling it
done — layout bugs (overlapping text, a row that wrapped awkwardly) don't
show up in a page count:

```bash
pdftoppm -jpeg -r 130 output.pdf page
```

Then read the resulting `page-1.jpg`.

## Measure instead of counting

When poppler is missing (or you want to know *which* element overflowed rather
than just that something did), ask the browser for the rendered heights:

```bash
node -e "
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + process.cwd() + '/output.html');
  console.log(await p.evaluate(() => {
    const o = { page: document.querySelector('.page').getBoundingClientRect().height };
    for (const s of ['.masthead','.flow','.footnote']) {
      const el = document.querySelector(s);
      if (el) o[s] = +el.getBoundingClientRect().height.toFixed(1);
    }
    return o;
  }));
  await b.close(); })();
"
```

Usable height for `.page` is about 733px (A4 landscape, 210mm less the 8mm
`@page` margins). A `.page` height above that means it will spill onto a second
sheet. This tells you nothing about *visual* bugs — truncated labels, wrapped
legends — so prefer the PDF-and-look path whenever poppler is available.

## If it doesn't fit on one page

`render_tracker.py` prints a warning to stderr once ticket count exceeds ~26,
since that's past what the tuned sizing comfortably holds at a readable font
size. If you hit this:

1. **First choice: trim what's shown, not the font.** A tracker that's
   technically one page but unreadable at 6px type has failed its purpose.
   Consider whether every ticket needs its own row — could sub-tasks or
   near-duplicate items collapse into one row with a combined status, or
   could a "done" group from earlier in the week move to a compact one-line
   summary instead of full rows?
2. **Second choice: shrink deliberately, in small steps.** The CSS in
   `render_tracker.py` has padding and font-size values on `tr.tkt td`,
   `.grp-row td`, `.chip`, and the `.page` padding — the same knobs that were
   tuned to fit 22 tickets. Reduce `tr.tkt td` padding first (it has the most
   headroom), re-render, re-check the PDF page count, and stop as soon as it
   fits — don't over-shrink past what's needed. In testing, `tr.tkt td`
   padding alone wasn't always enough to close a small overflow (e.g. 22
   tickets with 3 reported days, where the extra day column adds a line to
   the summary bar) — `.masthead`, `.flow`, and `.footnote` all carry a few
   more px of margin/padding that are safe to trim next in the same small
   increments before reaching for font-size.
3. **Last resort: it's not a one-pager anymore.** If the sprint genuinely has
   40+ tickets, forcing everything onto one page stops being the right
   answer. Say so, and offer either a two-page version (repeat the masthead,
   split groups across pages) or ask the user whether they'd rather see only
   the tickets that moved this week plus a rolled-up count for the rest.
