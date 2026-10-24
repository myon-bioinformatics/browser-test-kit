import {test, expect} from '@playwright/test';
import {spawnSync} from 'node:child_process';
import {writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';

// No page/browser fixture: this suite runs once without installing a browser engine.
const node = (...args: string[]) => spawnSync(process.execPath, [resolve('tools/mirror_facts.mjs'), ...args], {encoding: 'utf8'});
const check = (...files: string[]) => spawnSync('python', ['-S', 'tools/mirror_check.py', 'compare', ...files], {encoding: 'utf8'});

test('markdown-it and marked agree on the CommonMark fixture', async ({}, testInfo) => {
  const files = ['markdown-it', 'marked'].map((reader) => {
    const out = node('markdown', 'fixtures/mirror.md', '--reader', reader);
    expect(out.status, out.stderr).toBe(0);
    const path = testInfo.outputPath(`${reader}.json`);
    writeFileSync(path, out.stdout);
    return path;
  });
  const facts = JSON.parse(node('markdown', 'fixtures/mirror.md').stdout);
  expect(facts.headings).toEqual([[1, 'Mirror fixture'], [2, 'Section two'], [3, 'Third level']]);
  expect(facts.links).toEqual(['https://example.org/a', 'https://example.org/ref']);
  const result = check(...files);
  expect(result.status, result.stdout).toBe(0);
});

test('HTML reader emits complete facts accepted by compare', async ({}, testInfo) => {
  const html = testInfo.outputPath('page.html');
  writeFileSync(html, '<!doctype html><html><body><h1>Title</h1><a href="https://example.org">link</a>' +
    '<img src="a.png" alt="A"><pre><code class="language-js">x\n</code></pre></body></html>');
  const out = node('html', html);
  expect(out.status, out.stderr).toBe(0);
  const expected = {schema: 'mirror-facts/1', kind: 'html', headings: [[1, 'Title']],
    links: ['https://example.org'], images: [['a.png', 'A']], code: [['js', 'x']]};
  expect(JSON.parse(out.stdout)).toMatchObject(expected);
  const actualFile = testInfo.outputPath('linkedom.json');
  const expectedFile = testInfo.outputPath('expected.json');
  writeFileSync(actualFile, out.stdout);
  writeFileSync(expectedFile, JSON.stringify({...expected, reader: 'fixture-contract'}));
  const result = check(actualFile, expectedFile);
  expect(result.status, result.stderr).toBe(0);
});

test('ExcelJS writes, ExcelJS and the stdlib OOXML reader read the same cells', async ({}, testInfo) => {
  const ExcelJS = createRequire(resolve('package.json'))('exceljs');
  const book = new ExcelJS.Workbook();
  const ws = book.addWorksheet('売上');
  ws.addRow(['商品', '金額', '有効']);
  ws.addRow(['A', 1000, true]);
  ws.getCell('D1').value = new Date(Date.UTC(2026, 9, 16));
  ws.getCell('E1').value = {formula: 'SUM(B2:B2)', result: 1000};
  ws.mergeCells('A4:C4');
  ws.getCell('A4').value = '合計';
  const xlsx = testInfo.outputPath('book.xlsx');
  await book.xlsx.writeFile(xlsx);
  const js = testInfo.outputPath('exceljs.json');
  writeFileSync(js, node('xlsx', xlsx, '--reader', 'exceljs').stdout);
  const py = testInfo.outputPath('stdlib.json');
  const facts = spawnSync('python', ['-S', 'tools/mirror_check.py', 'facts', 'xlsx', xlsx], {encoding: 'utf8'});
  expect(facts.status, facts.stderr).toBe(0);
  writeFileSync(py, facts.stdout);
  const result = check(js, py);
  console.log(`::notice title=mirror xlsx::${result.stdout.trim().split('\n').pop()}`);
  expect(result.status, result.stdout).toBe(0);
  expect(JSON.parse(facts.stdout).merges).toEqual([['売上', 'A4:C4']]);
});
