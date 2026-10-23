/** Python page_inspect.py companion. No runtime dependency for offline commands.
 * Survey imports playwright when that command is used. Scores are the longest
 * common substring divided by the shorter UTF-16 length, after simple lowercasing.
 * Exit codes: 0 success; 1 no match or a shared top score; 2 usage or runtime failure.
 */
import {existsSync, statSync, readFileSync, realpathSync, writeFileSync} from "node:fs";
import {dirname} from "node:path";
import {platform} from "node:os";
import {fileURLToPath, pathToFileURL} from "node:url";

export const SCHEMA_INSPECT = "btk-page-inspect/1";
export const SCHEMA_SURVEY = "btk-page-survey/1";
export const HARD_CAP = 500;
export const SURVEY_LIMIT_DEFAULT = 50;
export const SURVEY_LIMIT_MAX = 200;
export const PAGE_LIMIT_DEFAULT = 20;
export const PAGE_LIMIT_MAX = 100;
export const CONTEXT_DEFAULT = 1;
export const CONTEXT_MAX = 5;
export const SUGGESTIONS = 3;
export const THRESHOLD_DEFAULT = 1;
export const PROFILES = {desktop: null, iphone: "iPhone 13", pixel: "Pixel 7"};
const DESKTOP_VIEWPORT = {width: 1280, height: 800};
const SAFE = /^[A-Za-z_][A-Za-z0-9_-]*$/;
const ROLE_ADDRESS = /^([^/]*)\/([^#]*)#(\d+)$/;
const ROLE_EQ = /^role=([A-Za-z0-9_-]+)\[name="([^"]*)"\](?:#(\d+))?$/;
const GET_BY_ROLE = /^getByRole\(\s*['"]([A-Za-z0-9_-]+)['"]\s*,\s*\{\s*name\s*:\s*['"]([^'"]*)['"]\s*\}\s*\)$/;
const QUOTED_ROLE = /^([A-Za-z0-9_-]+)\s+"([^"]*)"$/;
const HASH_ID = /^#([A-Za-z_][A-Za-z0-9_-]*)$/;
const TESTID_ATTR = /^\[data-testid="([^"]+)"\]$/;
const EQ_ID = /^(id|testid)=([A-Za-z_][A-Za-z0-9_-]*)$/;
const here = dirname(fileURLToPath(import.meta.url));
export const COLLECT_JS = readFileSync(`${here}/page_inspect_collect.js`, "utf8");

export class InspectError extends Error {
  constructor(error, hint, stage = "input", code = 2, suggestions = []) {
    super(error);
    this.error = error;
    this.hint = hint;
    this.stage = stage;
    this.code = code;
    this.suggestions = suggestions;
  }
}

export function osName() {
  return {darwin: "macOS", win32: "Windows", linux: "Linux"}[platform()] || platform();
}

export function unitLen(text) {
  return String(text).length;
}

export function lcsLength(left, right) {
  const first = String(left).toLowerCase();
  const second = String(right).toLowerCase();
  if (!first.length || !second.length) return 0;
  let previous = new Array(second.length + 1).fill(0);
  let best = 0;
  for (let i = 0; i < first.length; i += 1) {
    const unit = first.charCodeAt(i);
    const current = new Array(second.length + 1).fill(0);
    for (let j = 0; j < second.length; j += 1) {
      if (unit === second.charCodeAt(j)) {
        current[j + 1] = previous[j] + 1;
        if (current[j + 1] > best) best = current[j + 1];
      }
    }
    previous = current;
  }
  return best;
}

export function round6(value) {
  return Math.floor(value * 1000000 + 0.5) / 1000000;
}

export function similarity(left, right) {
  if (!left || !right) return 0;
  const first = String(left).toLowerCase();
  const second = String(right).toLowerCase();
  return round6(lcsLength(first, second) / Math.min(first.length, second.length));
}

function clip(value, limit = 120) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
}

function requireStr(item, key) {
  const value = item[key] ?? "";
  if (typeof value !== "string") {
    throw new InspectError(`${key} must be a string`, "the survey payload was modified; run survey again", "inspect");
  }
  return value;
}

function requireBool(item, key, fallback = undefined) {
  if (!(key in item) && fallback !== undefined) return fallback;
  if (typeof item[key] !== "boolean") {
    throw new InspectError(`${key} must be a boolean`, "the survey payload was modified; run survey again", "inspect");
  }
  return item[key];
}

function boxOf(item) {
  const raw = item.box;
  if (!raw || typeof raw !== "object") {
    throw new InspectError("box must be an object", "the survey payload was modified; run survey again", "inspect");
  }
  const box = {};
  for (const key of ["x", "y", "width", "height"]) {
    const value = raw[key] ?? 0;
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new InspectError(`box.${key} must be a finite number`, "the survey payload was modified; run survey again", "inspect");
    }
    box[key] = Math.floor(value);
  }
  return box;
}

export function encodeAddress(value) {
  return encodeURIComponent(value);
}

export function decodeAddress(value) {
  if (/%(?![0-9A-Fa-f]{2})/.test(value)) {
    throw new InspectError("role address has a bad percent escape", "copy the address from survey or locate");
  }
  try {
    return decodeURIComponent(value);
  } catch (error) {
    throw new InspectError("role address has a bad percent escape", "copy the address from survey or locate");
  }
}

function roleAddress(role, name, nth) {
  return `role:${encodeAddress(role)}/${encodeAddress(name)}#${nth}`;
}

function locator(kind, selector, unique, nth) {
  return {kind, selector, unique, nth};
}

function checkPage(start, limit, limitMax) {
  if (!Number.isInteger(start) || start < 0 || start > 100000) {
    throw new InspectError("start must be an integer from 0 to 100000", "pass --start as a whole number");
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > limitMax) {
    throw new InspectError(`limit must be an integer from 1 to ${limitMax}`, "lower --limit and page with --start");
  }
}

function checkThreshold(threshold) {
  if (typeof threshold !== "number" || !Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
    throw new InspectError("threshold must be a number from 0 to 1", "pass --threshold 1 for containment, or a lower score");
  }
}

export function normalizeElements(raw, {start = 0, limit = SURVEY_LIMIT_DEFAULT} = {}) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.elements)) {
    throw new InspectError("survey payload has no elements list", "run survey again", "inspect");
  }
  checkPage(start, limit, SURVEY_LIMIT_MAX);
  const prepared = [];
  const counts = new Map();
  const nths = [];
  for (const item of raw.elements) {
    if (!item || typeof item !== "object") {
      throw new InspectError("survey element must be an object", "run survey again", "inspect");
    }
    const role = clip(requireStr(item, "role"), 40) || "generic";
    const name = clip(requireStr(item, "name"));
    const key = `${role}\0${name}`;
    const nth = counts.get(key) || 0;
    nths.push(nth);
    counts.set(key, nth + 1);
    prepared.push({item, role, name, key});
  }
  const built = prepared.map((entry, index) => {
    const nth = nths[index];
    const elementId = clip(requireStr(entry.item, "id"), 200);
    const testid = clip(requireStr(entry.item, "testid"), 200);
    const css = requireStr(entry.item, "css");
    const idUnique = requireBool(entry.item, "id_unique", false) && SAFE.test(elementId);
    const testidUnique = requireBool(entry.item, "testid_unique", false) && SAFE.test(testid);
    const cssUnique = requireBool(entry.item, "css_unique", false) && !!css;
    const locators = [];
    if (idUnique) locators.push(locator("id", `#${elementId}`, true, null));
    if (testidUnique) locators.push(locator("testid", `[data-testid="${testid}"]`, true, null));
    const roleSafe = entry.role && entry.role !== "generic" && entry.name && !/["\\\n\]]/.test(entry.name);
    if (roleSafe) {
      locators.push(locator("role", `role=${entry.role}[name="${entry.name}"]`, counts.get(entry.key) === 1, nth));
    }
    if (css) locators.push(locator("css", css, cssUnique, null));
    let address;
    if (idUnique) address = `id:${elementId}`;
    else if (testidUnique) address = `testid:${testid}`;
    else if (roleSafe) address = roleAddress(entry.role, entry.name, nth);
    else if (css) address = `css:${css}`;
    else address = `h:${index}`;
    return {
      handle: `h:${index}`, index, address, tag: clip(requireStr(entry.item, "tag"), 40),
      role: entry.role, name: entry.name, text: clip(requireStr(entry.item, "text")),
      id: elementId, testid, href: requireStr(entry.item, "href").slice(0, 500),
      visible: requireBool(entry.item, "visible"), enabled: requireBool(entry.item, "enabled"),
      in_viewport: requireBool(entry.item, "in_viewport"), obscured: requireBool(entry.item, "obscured"),
      box: boxOf(entry.item), parent_tag: clip(requireStr(entry.item, "parent_tag"), 40), locators,
    };
  });
  let reported = raw.total ?? built.length;
  if (typeof reported !== "number" || !Number.isInteger(reported) || reported < built.length) reported = built.length;
  const page = built.filter((element) => element.index >= start && element.index < start + limit);
  const truncated = !!raw.truncated || built.length < reported || start + page.length < built.length || start + page.length < reported;
  return {elements: page, total: reported, truncated, start, limit, collected: built.length};
}

export function fieldScore(element, query) {
  let best = 0;
  let matched = null;
  for (const key of ["name", "text", "id", "testid", "role"]) {
    const value = element[key] || "";
    if (!value) continue;
    const score = similarity(query, value);
    if (score > best) {
      best = score;
      matched = key;
    }
  }
  return [best, matched];
}

function roleOk(element, role) {
  return !role || String(element.role || "").toLowerCase() === role.toLowerCase();
}

function view(element) {
  return {role: "", name: "", text: "", id: "", testid: "", index: 0, ...element, index: Number.isInteger(element.index) ? element.index : 0};
}

export function suggest(elements, query, limit = SUGGESTIONS) {
  if (!query) return [];
  const ranked = [];
  for (const element of elements) {
    const [score] = fieldScore(element, query);
    if (score > 0) ranked.push([score, element]);
  }
  ranked.sort((left, right) => right[0] - left[0] || (left[1].index || 0) - (right[1].index || 0));
  return ranked.slice(0, limit).map(([score, element]) => ({
    address: element.address, handle: element.handle, name: element.name || "", role: element.role || "", score,
  }));
}

function suggestFrom(elements) {
  return elements.slice(0, SUGGESTIONS).map((element) => ({
    address: element.address, handle: element.handle, name: element.name || "", role: element.role || "", score: element.score ?? null,
  }));
}

function locateHint(query, total, nextStart) {
  if (!query) {
    const extra = nextStart != null ? ` Pass --start ${nextStart} for the next page.` : "";
    return `pass --query to rank by longest-common-substring similarity.${extra}`;
  }
  if (nextStart != null) return `showing a page of ${total}. Pass --start ${nextStart} for the next page, or count for totals only`;
  return `${total} match(es). describe one address to read a single control`;
}

export function locate(elements, {query = "", role = "", threshold = THRESHOLD_DEFAULT, start = 0, limit = PAGE_LIMIT_DEFAULT, unique = false} = {}) {
  checkPage(start, limit, PAGE_LIMIT_MAX);
  checkThreshold(threshold);
  const chosen = elements.filter((element) => roleOk(element, role)).map(view);
  let scored;
  if (query) {
    scored = [];
    for (const element of chosen) {
      const [score, matched] = fieldScore(element, query);
      if (score + 1e-9 >= threshold) scored.push({...element, score, matched});
    }
    const queryLower = query.toLowerCase();
    scored.sort((left, right) => (
      right.score - left.score
      || ((left.name || "").toLowerCase() === queryLower ? 0 : 1) - ((right.name || "").toLowerCase() === queryLower ? 0 : 1)
      || unitLen(left.name || "") - unitLen(right.name || "")
      || left.index - right.index
    ));
  } else {
    scored = chosen.map((element) => ({...element, score: null, matched: null}));
  }
  const total = scored.length;
  const page = scored.slice(start, start + limit);
  const nextStart = start + page.length >= total ? null : start + page.length;
  const payload = {
    schema: SCHEMA_INSPECT, ok: true, operation: "locate",
    pagination: {start, limit, returned: page.length, total, next_start: nextStart},
    items: page, hint: locateHint(query, total, nextStart),
  };
  if (query && total === 0) {
    return {
      ...payload, ok: false, stage: "input", error: "no element matches",
      hint: "lower --threshold, or reuse a suggest address. count lists role totals without element bodies",
      suggestions: suggest(role ? chosen : elements.map(view), query),
    };
  }
  if (unique && query && total) {
    const top = scored[0].score;
    const tied = scored.filter((element) => element.score === top);
    if (tied.length > 1) {
      const shown = tied.slice(0, limit);
      return {
        ...payload, ok: false, stage: "input", error: "more than one element shares the top score",
        hint: "pass one address to describe; do not guess", items: shown, suggestions: suggestFrom(tied),
        pagination: {start: 0, limit, returned: shown.length, total: tied.length, next_start: null},
      };
    }
    payload.items = scored.slice(0, 1);
    payload.pagination = {start: 0, limit, returned: 1, total: 1, next_start: null};
    payload.hint = "unique top score; lower scores were omitted. Omit --unique to see the whole page";
  }
  return payload;
}

export function countElements(elements, {query = "", role = "", threshold = THRESHOLD_DEFAULT} = {}) {
  checkThreshold(threshold);
  let chosen = elements.filter((element) => roleOk(element, role)).map(view);
  if (query) {
    chosen = chosen.filter((element) => fieldScore(element, query)[0] + 1e-9 >= threshold);
  }
  const byRole = {};
  let visible = 0;
  let enabled = 0;
  for (const element of chosen) {
    const key = element.role || "";
    byRole[key] = (byRole[key] || 0) + 1;
    if (element.visible) visible += 1;
    if (element.enabled) enabled += 1;
  }
  const ordered = {};
  for (const key of Object.keys(byRole).sort()) ordered[key] = byRole[key];
  return {
    schema: SCHEMA_INSPECT, ok: true, operation: "count", total: chosen.length, visible, enabled,
    by_role: ordered, hint: "locate --start 0 --limit 20 returns one page of controls; count does not",
  };
}

function storedNth(elements, element) {
  for (const item of element.locators || []) {
    if (item.kind === "role" && typeof item.nth === "number" && Number.isInteger(item.nth)) return item.nth;
  }
  let nth = 0;
  for (const other of elements) {
    if (other === element || other.handle === element.handle) return nth;
    if (other.role === element.role && other.name === element.name) nth += 1;
  }
  return nth;
}

function byRoleName(elements, role, name, nth) {
  const found = [];
  for (const element of elements) {
    if ((element.role || "").toLowerCase() === role.toLowerCase() && (element.name || "") === name) {
      if (nth == null || storedNth(elements, element) === nth) found.push(element);
    }
  }
  return found;
}

function splitRoleAddress(value) {
  const match = ROLE_ADDRESS.exec(value);
  if (!match) throw new InspectError("role address must look like role:button/Save%20draft#0", "copy an address from locate or survey");
  return [decodeAddress(match[1]), decodeAddress(match[2]), Number(match[3])];
}

function hasSelector(element, selector) {
  return (element.locators || []).some((item) => item.selector === selector);
}

function matchTarget(elements, text) {
  if (text.startsWith("h:")) return ["handle", elements.filter((element) => element.handle === text)];
  if (text.startsWith("id:")) return ["id", elements.filter((element) => element.id === text.slice(3))];
  if (text.startsWith("testid:")) return ["testid", elements.filter((element) => element.testid === text.slice(7))];
  if (text.startsWith("role:")) {
    const [role, name, nth] = splitRoleAddress(text.slice(5));
    return ["role", byRoleName(elements, role, name, nth)];
  }
  if (text.startsWith("css:")) {
    const selector = text.slice(4);
    return ["css", elements.filter((element) => element.address === text || hasSelector(element, selector))];
  }
  let match = HASH_ID.exec(text);
  if (match) return ["id", elements.filter((element) => element.id === match[1])];
  match = TESTID_ATTR.exec(text);
  if (match) return ["testid", elements.filter((element) => element.testid === match[1])];
  match = ROLE_EQ.exec(text);
  if (match) return ["role", byRoleName(elements, match[1], match[2], match[3] == null ? null : Number(match[3]))];
  match = GET_BY_ROLE.exec(text);
  if (match) return ["role", byRoleName(elements, match[1], match[2], null)];
  match = QUOTED_ROLE.exec(text);
  if (match) return ["role", byRoleName(elements, match[1], match[2], null)];
  match = EQ_ID.exec(text);
  if (match) {
    const key = match[1] === "id" ? "id" : "testid";
    return [key, elements.filter((element) => element[key] === match[2])];
  }
  let exact = elements.filter((element) => element.id === text);
  if (exact.length) return ["id", exact];
  exact = elements.filter((element) => element.testid === text);
  if (exact.length) return ["testid", exact];
  exact = elements.filter((element) => element.address === text);
  if (exact.length) return ["address", exact];
  return ["bare", elements.filter((element) => element.name === text)];
}

export function resolveTarget(elements, target) {
  const text = String(target || "").trim();
  if (!text) throw new InspectError("target is empty", "pass an address from locate, such as id:save-draft");
  if (/^0x[0-9A-Fa-f]+$/.test(text)) {
    throw new InspectError("memory addresses are not element addresses", "use id:, testid:, role:, css:, or a snapshot h:N handle");
  }
  const views = elements.map(view);
  const [kind, matches] = matchTarget(views, text);
  if (matches.length === 1) return {ok: true, element: matches[0], resolved_as: kind};
  if (matches.length > 1) {
    return {
      schema: SCHEMA_INSPECT, ok: false, operation: "describe", stage: "input",
      error: "target matches more than one element", hint: "pass one full address, including the role nth",
      suggestions: matches.slice(0, SUGGESTIONS).map((element) => ({
        address: element.address, handle: element.handle, name: element.name || "", role: element.role || "", score: null,
      })),
    };
  }
  const lowered = text.toLowerCase();
  const folded = kind === "bare" ? views.filter((element) => (element.name || "").toLowerCase() === lowered || (element.id || "").toLowerCase() === lowered) : [];
  if (folded.length === 1) return {ok: true, element: folded[0], resolved_as: "name-casefold"};
  return {
    schema: SCHEMA_INSPECT, ok: false, operation: "describe", stage: "input",
    error: "target is not in this snapshot",
    hint: "h:N is valid only in the snapshot that minted it; reuse an address or run survey again",
    suggestions: suggest(views, text),
  };
}

export function elementLine(element, marker = false) {
  const score = element.score;
  const scoreText = typeof score === "number" ? ` score=${score.toFixed(6)}` : "";
  return `${marker ? "* " : ""}${element.handle} ${element.role} "${element.name || ""}" ${element.address}${scoreText}`;
}

export function describeElement(elements, target, {context = CONTEXT_DEFAULT} = {}) {
  if (!Number.isInteger(context) || context < 0 || context > CONTEXT_MAX) {
    throw new InspectError(`context must be an integer from 0 to ${CONTEXT_MAX}`, "pass --context 1 for one neighbor on each side");
  }
  const resolved = resolveTarget(elements, target);
  if (!resolved.ok) return {...resolved, operation: "describe"};
  const element = resolved.element;
  const position = elements.findIndex((item) => item.handle === element.handle);
  const lines = [];
  for (let index = Math.max(0, position - context); index < Math.min(elements.length, position + context + 1); index += 1) {
    lines.push(elementLine(elements[index], index === position));
  }
  return {
    schema: SCHEMA_INSPECT, ok: true, operation: "describe", resolved_as: resolved.resolved_as, item: element, context: lines,
    hint: `resolved as ${resolved.resolved_as}. Neighbors are adjacent controls in this snapshot, not DOM siblings. Reuse ${element.address}`,
  };
}

export function operations() {
  const items = [
    {name: "survey", needs: "playwright", summary: "Collect visible controls from one page into a snapshot", limit_default: SURVEY_LIMIT_DEFAULT, limit_max: SURVEY_LIMIT_MAX},
    {name: "count", needs: "snapshot", summary: "Count matches and roles without element bodies", limit_default: null, limit_max: null},
    {name: "locate", needs: "snapshot", summary: "Rank controls by longest-common-substring similarity and page them", limit_default: PAGE_LIMIT_DEFAULT, limit_max: PAGE_LIMIT_MAX},
    {name: "describe", needs: "snapshot", summary: "Return one control, its locators, and a few neighbor lines", limit_default: CONTEXT_DEFAULT, limit_max: CONTEXT_MAX},
    {name: "operations", needs: "none", summary: "List these commands", limit_default: null, limit_max: null},
  ];
  return {
    schema: SCHEMA_INSPECT, ok: true, operation: "operations", items,
    hint: "count before locate on a large snapshot; describe one address instead of printing every control",
  };
}

export function contextOptions(devices, browserName, profile, headed) {
  const device = PROFILES[profile];
  if (device === undefined) throw new InspectError("unknown profile", "use desktop, iphone, or pixel");
  let args;
  if (device) args = {...devices[device]};
  else if (headed) args = {viewport: null};
  else args = {viewport: {...DESKTOP_VIEWPORT}};
  delete args.defaultBrowserType;
  if (browserName === "firefox") delete args.isMobile;
  return args;
}

export const SURVEY_PORT = 8080;
const NETWORK_TARGET = new RegExp(String.raw`^https?://(?:127\.0\.0\.1|\[::1\]):${SURVEY_PORT}(?=[/?#]|$)`, "i");

export function targetUrl(target) {
  const hint = "use an existing local HTML file or http(s)://127.0.0.1:8080 / http(s)://[::1]:8080; hostnames and other ports are not allowed";
  if ((/[\x00-\x20\x7f]/.test(target) && target.includes("://")) || target.includes("\\")) {
    throw new InspectError("URL is outside the survey boundary", hint);
  }
  if (target.includes("://")) {
    if (NETWORK_TARGET.test(target)) return target;
    try {
      const url = new URL(target);
      if (/^file:\/\/\//i.test(target) && url.protocol === "file:" && !url.host && existsSync(fileURLToPath(url)) && statSync(fileURLToPath(url)).isFile()) return target;
    } catch {}
    throw new InspectError("URL is outside the survey boundary", hint);
  }
  if (!existsSync(target) || !statSync(target).isFile()) throw new InspectError(`page not found: ${target}`, "pass an existing HTML file or an http(s) or file URL");
  return pathToFileURL(target).href;
}

export async function restrictRequest(route) {
  try { targetUrl(route.request().url()); } catch {
    await route.abort("blockedbyclient");
    return;
  }
  if (route.request().url().startsWith("file:")) { await route.continue(); return; }
  const response = await route.fetch({maxRedirects: 0});
  if (response.status() >= 300 && response.status() < 400) await route.abort("blockedbyclient");
  else await route.fulfill({response});
}


export function assembleSurvey(raw, {environment, url, start, limit}) {
  const normalized = normalizeElements(raw, {start, limit});
  const hints = [];
  if (raw.child_frames) hints.push("child frames were counted and not surveyed");
  if (raw.shadow_roots === true) hints.push("open shadow roots were detected and not entered");
  if (raw.shadow_scan === "partial") hints.push("the shadow scan stopped at 2000 elements");
  if (normalized.truncated) hints.push("this snapshot is a page of the survey; raise --limit or pass --role");
  hints.push("h:N is valid only in this snapshot; reuse address with describe and locate");
  const childFrames = raw.child_frames || 0;
  if (typeof childFrames !== "number" || !Number.isInteger(childFrames)) {
    throw new InspectError("child_frames must be an integer", "run survey again", "inspect");
  }
  return {
    schema: SCHEMA_SURVEY, ok: true, url, title: clip(String(raw.title || ""), 200), environment,
    child_frames: childFrames, shadow_roots: raw.shadow_roots ?? null, shadow_scan: raw.shadow_scan || "complete",
    truncated: normalized.truncated, total: normalized.total, start, limit, hint: hints.join(". "), elements: normalized.elements,
  };
}

function dumps(payload) {
  return `${JSON.stringify(payload, null, 2)}\n`;
}

function errorEnvelope(operation, error) {
  const payload = {
    schema: SCHEMA_INSPECT, ok: false, operation, stage: error.stage || "input", error: error.error || error.message, hint: error.hint,
  };
  if (error.suggestions && error.suggestions.length) payload.suggestions = error.suggestions;
  return payload;
}

function errorText(payload) {
  const lines = [`stage: ${payload.stage || "input"}`, `error: ${payload.error}`, `hint: ${payload.hint}`];
  for (const item of payload.suggestions || []) {
    const score = typeof item.score === "number" ? ` ${item.score.toFixed(6)}` : "";
    lines.push(`suggest: ${item.address}${score} ${item.name}`);
  }
  return `${lines.join("\n")}\n`;
}

function emit(payload, text, code, args) {
  const raw = dumps(payload);
  if (args.out) {
    const parent = dirname(args.out);
    if (parent && parent !== "." && !existsSync(parent)) {
      process.stderr.write(`error: directory does not exist: ${parent}\nhint: create the directory before --out\n`);
      return 2;
    }
    try { writeFileSync(args.out, raw); } catch (error) {
      process.stderr.write(`error: cannot write ${args.out}: ${error.message}\nhint: choose a writable file path\n`);
      return 2;
    }
  }
  if (args.json) process.stdout.write(raw);
  else if (payload.ok === false) process.stderr.write(text);
  else process.stdout.write(text);
  return code;
}

function helpText() {
  return `page_inspect.mjs — survey a page and rank locators.

offline: node scripts/page_inspect.mjs locate SNAPSHOT --query TEXT --json
live:    node scripts/page_inspect.mjs survey PAGE --browser chromium --json --out survey.json

commands: survey, count, locate, describe, operations
`;
}

function parseArgs(argv) {
  const args = {_: [], json: false, unique: false, includeHidden: false, headed: false};
  const flags = new Set(["json", "unique", "include-hidden", "headed", "help"]);
  const options = new Set(["out", "browser", "profile", "channel", "role", "start", "limit", "query", "threshold", "target", "context"]);
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--") {
      args._.push(...argv.slice(index + 1));
      break;
    }
    if (!token.startsWith("--")) {
      args._.push(token);
      continue;
    }
    const body = token.slice(2);
    if (!body || body.startsWith("-")) throw new InspectError(`unknown option ${token}`, "pass --help");
    const eq = body.indexOf("=");
    const name = eq >= 0 ? body.slice(0, eq) : body;
    const inline = eq >= 0;
    if (flags.has(name)) {
      if (inline) throw new InspectError(`--${name} does not take a value`, "pass the flag on its own");
      if (name === "json") args.json = true;
      else if (name === "unique") args.unique = true;
      else if (name === "include-hidden") args.includeHidden = true;
      else if (name === "headed") args.headed = true;
      else args.help = true;
      continue;
    }
    if (!options.has(name)) throw new InspectError(`unknown option --${name}`, "abbreviations are not accepted; pass the full option name");
    const value = inline ? body.slice(eq + 1) : argv[++index];
    if (value === undefined || (!inline && value.startsWith("--"))) {
      throw new InspectError(`--${name} needs a value`, "pass the value immediately after the option");
    }
    args[name] = value;
  }
  return args;
}

function whole(name, value, max, min) {
  if (!/^(?:0|[1-9][0-9]*)$/.test(String(value))) throw new InspectError(`${name} must be a whole number`, "pass digits");
  const number = Number(value);
  if (number < min || number > max) throw new InspectError(`${name} is out of range`, `use ${min}..${max}`);
  return number;
}

function readSnapshot(path) {
  if (!existsSync(path)) throw new InspectError(`snapshot not found: ${path}`, "run survey --out this path first");
  let data;
  try { data = JSON.parse(readFileSync(path, "utf8")); } catch (error) {
    throw new InspectError("snapshot is not JSON", "run survey again and pass that file");
  }
  if (!data || data.schema !== SCHEMA_SURVEY) {
    throw new InspectError("snapshot schema is not btk-page-survey/1", "pass a file written by survey, not a locate result");
  }
  if (!Array.isArray(data.elements)) throw new InspectError("snapshot has no elements list", "run survey again");
  for (const element of data.elements) {
    if (!element || typeof element.address !== "string" || typeof element.handle !== "string") {
      throw new InspectError("snapshot element is missing address or handle", "run survey again");
    }
  }
  return data;
}

async function closeBrowser(browser) {
  if (!browser) return null;
  try { await browser.close(); } catch (error) { return `${error.name}: ${error.message}`; }
  return null;
}

export async function surveyBrowser(options) {
  options = {...options, url: targetUrl(options.url)};
  let playwright;
  try { playwright = await import("playwright"); } catch (error) {
    throw new InspectError(
      "Playwright is not available to Node",
      "install playwright in this project; offline commands need only a snapshot",
      "launch",
    );
  }
  const browserType = playwright[options.browser];
  if (!browserType || typeof browserType.launch !== "function") {
    throw new InspectError("unknown browser", "use chromium, firefox, or webkit");
  }
  let browser = null;
  let failure = null;
  let result = null;
  try {
    try {
      browser = await browserType.launch({headless: !options.headed, ...(options.channel ? {channel: options.channel} : {})});
    } catch (error) {
      throw new InspectError(
        `${error.name}: ${error.message}`,
        "install the browser that matches this Playwright build. Headless survey uses the shell build; --headed needs the full browser",
        "launch",
      );
    }
    try {
      const context = await browser.newContext({...contextOptions(playwright.devices, options.browser, options.profile, options.headed), serviceWorkers: "block"});
      await context.route("**/*", restrictRequest);
      await context.routeWebSocket("**/*", websocket => websocket.close());
      const page = await context.newPage();
      page.setDefaultTimeout(15000);
      page.setDefaultNavigationTimeout(30000);
      try {
        await page.goto(options.url, {waitUntil: "load", timeout: 30000});
      } catch (error) {
        throw new InspectError(`${error.name}: ${error.message}`, "check the URL and that the page finishes loading. Core checks should use a local fixture", "navigate");
      }
      const collect = (0, eval)(COLLECT_JS);
      let raw;
      try {
        raw = await page.evaluate(collect, {includeHidden: !!options.includeHidden, role: options.role || "", hardCap: HARD_CAP});
      } catch (error) {
        throw new InspectError(`${error.name}: ${error.message}`, "the page script failed in this engine; the snapshot was not written", "inspect");
      }
      const viewport = page.viewportSize();
      result = assembleSurvey(raw, {
        environment: {
          os: osName(), browser: options.browser, version: browser.version(), channel: options.channel || null,
          headless: !options.headed, profile: options.profile,
          viewport: {width: viewport ? viewport.width : null, height: viewport ? viewport.height : null},
        },
        url: page.url(), start: options.start, limit: options.limit,
      });
    } catch (error) {
      if (error instanceof InspectError) failure = error;
      else throw error;
    }
    const closeNote = await closeBrowser(browser);
    browser = null;
    if (failure) {
      if (closeNote) failure.hint += ` Browser close also failed: ${closeNote}`;
      throw failure;
    }
    if (closeNote) throw new InspectError("browser close failed", closeNote, "cleanup");
    return result;
  } finally {
    if (browser) await closeBrowser(browser);
  }
}

function render(command, payload) {
  if (payload.ok === false) return errorText(payload);
  if (command === "operations") {
    return `${payload.items.map((item) => `${item.name}: ${item.summary}`).join("\n")}\nhint: ${payload.hint}\n`;
  }
  if (command === "count") {
    const roles = Object.entries(payload.by_role).map(([role, count]) => `role ${role}=${count}`);
    return [`total=${payload.total} visible=${payload.visible} enabled=${payload.enabled}`, ...roles, `hint: ${payload.hint}`].join("\n") + "\n";
  }
  if (command === "describe") {
    return [`resolved_as=${payload.resolved_as}`, ...payload.context, `hint: ${payload.hint}`].join("\n") + "\n";
  }
  if (command === "survey") {
    const env = payload.environment;
    const mode = env.headless ? "headless" : "headed";
    const lines = [
      `btk-page-survey/1 ${env.os} ${env.browser} ${env.profile} ${mode} elements=${payload.total} showing=${payload.elements.length}`,
      ...payload.elements.map((element) => elementLine(element)),
      `hint: ${payload.hint}`,
    ];
    return `${lines.join("\n")}\n`;
  }
  const page = payload.pagination;
  return [...payload.items.map((element) => elementLine(element)), `returned ${page.returned} of ${page.total}; start ${page.start}`, `hint: ${payload.hint}`].join("\n") + "\n";
}

export async function main(argv) {
  if (argv.length === 0 || argv.includes("--help") || argv.includes("-h")) {
    if (argv.includes("-h")) {
      process.stderr.write("error: short options are not accepted\nhint: pass --help\n");
      return 2;
    }
    process.stdout.write(helpText());
    return argv.length === 0 ? 2 : 0;
  }
  let args;
  try { args = parseArgs(argv); } catch (error) {
    const payload = errorEnvelope(argsCommand(argv), error);
    return emit(payload, errorText(payload), error.code || 2, {json: argv.includes("--json"), out: null});
  }
  const command = args._[0];
  try {
    if (command === "operations") {
      const payload = operations();
      return emit(payload, render(command, payload), 0, args);
    }
    if (command === "survey") {
      const target = args._[1];
      if (!target) throw new InspectError("survey needs a page", "pass an HTML file or a URL");
      const payload = await surveyBrowser({
        url: targetUrl(target), browser: args.browser || "chromium", profile: args.profile || "desktop",
        headed: args.headed, channel: args.channel || null, includeHidden: args.includeHidden, role: args.role || "",
        start: whole("start", args.start ?? "0", 100000, 0),
        limit: whole("limit", args.limit ?? String(SURVEY_LIMIT_DEFAULT), SURVEY_LIMIT_MAX, 1),
      });
      return emit(payload, render(command, payload), 0, args);
    }
    const snapshotPath = args._[1];
    if (!snapshotPath) throw new InspectError(`${command || "command"} needs a snapshot`, "pass the survey JSON path");
    if (!["count", "locate", "describe"].includes(command)) {
      throw new InspectError(`unknown command ${command}`, "use survey, count, locate, describe, or operations");
    }
    const elements = readSnapshot(snapshotPath).elements;
    let payload;
    if (command === "count") {
      payload = countElements(elements, {
        query: args.query || "", role: args.role || "", threshold: args.threshold === undefined ? 1 : Number(args.threshold),
      });
    } else if (command === "locate") {
      payload = locate(elements, {
        query: args.query || "", role: args.role || "",
        threshold: args.threshold === undefined ? 1 : Number(args.threshold),
        start: whole("start", args.start ?? "0", 100000, 0),
        limit: whole("limit", args.limit ?? String(PAGE_LIMIT_DEFAULT), PAGE_LIMIT_MAX, 1),
        unique: args.unique,
      });
    } else {
      if (!args.target) throw new InspectError("describe needs --target", "pass an address from locate or survey");
      payload = describeElement(elements, args.target, {context: whole("context", args.context ?? String(CONTEXT_DEFAULT), CONTEXT_MAX, 0)});
    }
    if (args.threshold !== undefined && (typeof payload === "object")) {
      // threshold already validated inside count/locate; describe ignores it
    }
    return emit(payload, render(command, payload), payload.ok ? 0 : 1, args);
  } catch (error) {
    const payload = errorEnvelope(command || "operations", error instanceof InspectError ? error : new InspectError(
      `${error.name}: ${error.message}`, "the command failed before it could write a result", "inspect",
    ));
    return emit(payload, errorText(payload), error instanceof InspectError ? error.code || 2 : 2, args);
  }
}

function argsCommand(argv) {
  const command = argv.find((token) => !token.startsWith("--"));
  return command || "operations";
}

const invoked = process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
if (invoked) {
  main(process.argv.slice(2)).then((code) => process.exit(code));
}
