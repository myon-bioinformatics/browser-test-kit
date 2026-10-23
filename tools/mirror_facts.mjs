#!/usr/bin/env node
// Facts about a document as read by independent JS libraries, without a browser.
//
//   node tools/mirror_facts.mjs markdown README.md [--reader markdown-it|marked]
//   node tools/mirror_facts.mjs html page.html                     (linkedom)
//   node tools/mirror_facts.mjs xlsx book.xlsx [--reader exceljs|sheetjs]
//
// Prints one `mirror-facts/1` JSON line. markdown/html: headings [level, text], links [href],
// images [src, alt], code [language, text]. xlsx: sheets [name], cells [sheet, ref, value]
// (formula cells give their cached result; dates as Excel serial numbers),
// formulas [sheet, ref, formula], merges [sheet, range].
// Compare two or more fact files with `python -S tools/mirror_check.py A.json B.json ...`.
// Libraries resolve from this kit first, then from the current directory; none needs a browser.
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';

function load(name) {
  for (const base of [import.meta.url, process.cwd() + '/']) {
    try { return createRequire(base)(name); } catch {}
  }
  console.error(`mirror_facts: cannot load ${name}; install it with npm i --no-save ${name.split('/')[0]}`);
  process.exit(2);
}
const version = (name) => name + '@' + load(name + '/package.json').version;

const args = process.argv.slice(2);
const at = args.indexOf('--reader');
const reader = at >= 0 ? args.splice(at, 2)[1] : null;
const [kind, file] = args;
const READERS = {markdown: ['markdown-it', 'marked'], html: ['linkedom'], xlsx: ['exceljs', 'sheetjs']};
if (!READERS[kind] || (reader && !READERS[kind].includes(reader))) {
  console.error('usage: mirror_facts.mjs markdown|html|xlsx FILE|- [--reader ' +
    Object.entries(READERS).map(([k, v]) => `${k}:${v.join('/')}`).join(' ') + ']');
  process.exit(2);
}
const use = reader || READERS[kind][0];
const input = readFileSync(!file || file === '-' ? 0 : file);
const flat = (s) => s.replace(/\s+/g, ' ').trim();

function documentFacts(html, readers) {
  const {document} = load('linkedom').parseHTML(html);
  readers.push(version('linkedom'));
  const facts = {headings: [], links: [], images: [], code: []};
  for (const h of document.querySelectorAll('h1,h2,h3,h4,h5,h6')) facts.headings.push([Number(h.tagName[1]), flat(h.textContent)]);
  for (const a of document.querySelectorAll('a[href]')) facts.links.push(a.getAttribute('href'));
  for (const img of document.querySelectorAll('img')) facts.images.push([img.getAttribute('src'), img.getAttribute('alt') || '']);
  for (const c of document.querySelectorAll('pre > code')) {
    const lang = ((c.getAttribute('class') || '').match(/language-(\S+)/) || [, ''])[1];
    facts.code.push([lang, c.textContent.replace(/\n$/, '')]);
  }
  return facts;
}

// Excel serial date (1900 system) from a JS Date stored as UTC by the readers.
const serial = (d) => d.getTime() / 86400000 + 25569;
const scalar = (v) => (v instanceof Date ? serial(v) : v);

async function xlsxFacts(buffer, readers) {
  const facts = {sheets: [], cells: [], formulas: [], merges: []};
  if (use === 'exceljs') {
    const ExcelJS = load('exceljs');
    readers.push(version('exceljs'));
    const book = new ExcelJS.Workbook();
    await book.xlsx.load(buffer);
    book.eachSheet((ws) => {
      facts.sheets.push(ws.name);
      for (const range of ws.model.merges || []) facts.merges.push([ws.name, range]);
      ws.eachRow({includeEmpty: false}, (row) => row.eachCell({includeEmpty: false}, (cell) => {
        // ExcelJS repeats a merge's master value on every covered cell; report stored values only.
        if (cell.isMerged && cell.master !== cell) return;
        let v = cell.value;
        if (v && typeof v === 'object' && !(v instanceof Date)) {
          if ('formula' in v || 'sharedFormula' in v) {
            if (v.formula) facts.formulas.push([ws.name, cell.address, v.formula]);
            v = v.result;
          } else if ('richText' in v) v = v.richText.map((r) => r.text).join('');
          else if ('text' in v) v = v.text;
        }
        if (v !== null && v !== undefined && v !== '') facts.cells.push([ws.name, cell.address, scalar(v)]);
      }));
    });
  } else {
    const XLSX = load('xlsx');
    readers.push('sheetjs@' + XLSX.version);
    const book = XLSX.read(buffer, {type: 'buffer', cellFormula: true, sheetStubs: true});
    for (const name of book.SheetNames) {
      const ws = book.Sheets[name];
      facts.sheets.push(name);
      for (const m of ws['!merges'] || []) facts.merges.push([name, XLSX.utils.encode_range(m)]);
      for (const ref of Object.keys(ws).filter((k) => !k.startsWith('!'))) {
        const cell = ws[ref];
        if (cell.f) facts.formulas.push([name, ref, cell.f]);
        if (cell.t !== 'z' && cell.v !== undefined && cell.v !== '') facts.cells.push([name, ref, cell.v]);
      }
    }
  }
  return facts;
}

const readers = [];
let facts;
if (kind === 'xlsx') {
  facts = await xlsxFacts(input, readers);
} else {
  let html = input.toString('utf8');
  if (kind === 'markdown') {
    if (use === 'marked') {
      html = load('marked').marked.parse(html, {async: false});
      readers.push(version('marked'));
    } else {
      html = new (load('markdown-it'))({html: true}).render(html);
      readers.push(version('markdown-it'));
    }
    html = '<!doctype html><html><body>' + html + '</body></html>';
  }
  facts = documentFacts(html, readers);
}
process.stdout.write(JSON.stringify({schema: 'mirror-facts/1', kind, reader: readers.join('+'), ...facts}) + '\n');
