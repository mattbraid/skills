# Keeping it to one page

The CSS in `render_defect_flow.py` is tuned to fit an A4-landscape sheet with
roughly a dozen distinct statuses and up to six named deferred items. Always
verify on the actual output — status counts, ticket-summary lengths and the
number of heatmap week-rows all vary between exports.

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
- **Playwright OK, poppler missing** — skip the page count and use the height
  measurement in "Measure before you trim" instead; `.page` over ~733px means it
  will spill. Say you checked by measurement rather than by rendering a PDF.
- **Playwright missing** — you cannot verify the fit at all. Deliver the HTML and
  **say so plainly in your reply**: the one-page fit is unverified. Offer the fix
  rather than performing it — `npx playwright install chromium` (plus poppler via
  `brew install poppler` or `apt install poppler-utils`) enables verification next
  run. The `PIL` crop below also needs Pillow, which may likewise be absent.

**Never report the page as verified when the preflight failed.** This page in
particular hides its failures well — the four defects listed below were all
invisible in a page count, and every one of them shipped at least once.

## Verify

After rendering:

```bash
node -e "
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + process.cwd() + '/out.html');
  await p.pdf({ path: 'out.pdf', format: 'A4', landscape: true, printBackground: true });
  await b.close();
})();
"
pdfinfo out.pdf | grep Pages
```

Don't pass an explicit `executablePath` — the installed browser lives under a
versioned directory that drifts between environments. Playwright's default
`chromium.launch()` resolves its own bundled browser.

If `Pages: 1`, rasterise it and **actually look at it**:

```bash
pdftoppm -jpeg -r 150 out.pdf pg
```

Then view `pg-1.jpg`. A page count of 1 will not catch:
- a status label truncated to `In Customer QA / Custo…`
- the heatmap's Fewer→More legend wrapping onto two lines
- a CSS escape rendering as a tofu box instead of a glyph
- a panel that's stretched tall next to one with three rows in it

All four of those happened while building this. Crop into the panels at higher
resolution if a region looks suspect:

```bash
python3 -c "
from PIL import Image
im = Image.open('pg-1.jpg'); w, h = im.size
im.crop((int(w*0.66), int(h*0.60), w, int(h*0.90))).save('crop.jpg')"
```

## Measure before you trim

Guessing at which element overflowed wastes iterations. Ask the browser:

```bash
node -e "
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + process.cwd() + '/out.html');
  console.log(await p.evaluate(() => {
    const o = { page: document.querySelector('.page').getBoundingClientRect().height };
    for (const s of ['.masthead','.kpis','.kpinote','.flow','.split','.footnote'])
      o[s] = +document.querySelector(s).getBoundingClientRect().height.toFixed(1);
    return o;
  }));
  await b.close(); })();
"
```

Usable height for `.page` is about 733px (A4 landscape, 210mm less the 8mm
`@page` margins). The `@media print` rule already zeroes the on-screen 3mm page
margin, which is worth ~23px — don't remove it.

## If it overflows

In order of preference:

1. **Trim content, not type.** A page that's technically one page at 6px is a
   failed page. Ask whether the deferred panel should aggregate rather than
   name items (lower `deferred_detail_max`), or whether `heat_days` can drop to
   21 and save a week-row.
2. **Shrink deliberately, in small steps.** The knobs with the most headroom,
   in the order to reach for them: `.srow` padding (the Development card
   usually has the most rows, so this compounds), `.drow` padding, `.cell`
   height in the heatmap, `.sect` margins, then `.footnote` margin-top.
   Re-render and re-check the page count after each — stop as soon as it fits.
3. **Font sizes last.** Below about 8px the sub-status labels stop being
   readable in print.
4. **Accept it isn't a one-pager.** If an export has 25+ distinct statuses, the
   layout has stopped being the right answer. Say so and offer to group the
   rarer statuses into an "other" row per phase.

## Two layout invariants worth preserving

- **Phase cards are equal height**, driven by whichever has the most
  sub-statuses. The priority-mix footer is pinned to the bottom with
  `margin-top:auto`, which is what stops the shorter cards looking unfinished.
- **The two lower panels stretch to match** (`align-items:stretch`), with the
  deferred rows distributed via `justify-content:space-around`. Without that,
  removing content from one panel leaves a visible block of dead space beside
  a full one.
