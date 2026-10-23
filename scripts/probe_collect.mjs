import {pathToFileURL} from 'node:url';
/** Node twin of probe_collect.py: the same read-only count, the same snapshot shape.
 * collect(page) takes a Playwright page that is already loaded. The count function reads the DOM and
 * open shadow-root references only; it calls no application code and changes nothing.
 * Limits match the Python twin: light-DOM interactive counts (partial when open shadow roots exist),
 * closed shadow roots are never seen, child frames are counted but not entered.
 */

export const INTERACTIVE_SELECTOR =
  'a[href], button, input:not([type=hidden]), select, textarea, ' +
  '[role=button], [role=link], [role=checkbox], [role=textbox], [role=combobox], [contenteditable=true]';

// Runs inside the page. Keep it self-contained: Playwright serializes this function's source.
function countInPage(selector) {
  let shadow = 0;
  const visit = root => {
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) { shadow += 1; visit(el.shadowRoot); }
    }
  };
  visit(document);
  return {interactive: document.querySelectorAll(selector).length, shadow_roots: shadow};
}

/** Return 'scheme://host[:port]' for an http(s) URL with a host, otherwise ''. */
export function originOf(url) {
  let parts;
  try { parts = new URL(url); } catch { return ''; }
  if ((parts.protocol !== 'http:' && parts.protocol !== 'https:') || !parts.host) return '';
  return `${parts.protocol}//${parts.host}`;
}

export async function collect(page) {
  const counted = await page.evaluate(countInPage, INTERACTIVE_SELECTOR);
  const shadow = counted.shadow_roots;
  return {
    origin: originOf(page.url()),
    interactive: {count: counted.interactive, collection: shadow > 0 ? 'partial' : 'complete'},
    shadow_roots: shadow,
    frames: Math.max(page.frames().length - 1, 0),
  };
}

/** CLI: node scripts/probe_collect.mjs URL  -> btk-probe-evidence/1 JSON on stdout.
 * Exit 0 OK; 2 bad URL, credentials, or browser/navigation failure. BTK_NODE_CHROMIUM may name a local Chromium.
 */
async function cli(argv) {
  const url = argv[0];
  let parts;
  try { parts = new URL(url ?? ''); } catch { parts = null; }
  if (!parts || (parts.protocol !== 'http:' && parts.protocol !== 'https:') || !parts.hostname || parts.username || parts.password) {
    process.stderr.write('probe_collect: an http(s) URL without credentials is required\n');
    return 2;
  }
  const {summarize} = await import('./probe_survey.mjs');
  const {to_json} = await import('./probe_evidence.mjs');
  let evidence;
  let browser;
  try {
    const {chromium} = await import('playwright');
    browser = await chromium.launch({headless: true, executablePath: process.env.BTK_NODE_CHROMIUM || undefined});
    const page = await browser.newPage();
    await page.goto(url, {waitUntil: 'load', timeout: 30000});
    evidence = summarize(await collect(page));
  } catch (error) {
    process.stderr.write(`probe_collect: ${error?.message ?? error}\n`);
    return 2;
  } finally {
    await browser?.close();
  }
  process.stdout.write(to_json(evidence) + '\n');
  return 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await cli(process.argv.slice(2));
}
