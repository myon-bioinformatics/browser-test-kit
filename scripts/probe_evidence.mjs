/** Node twin of probe_evidence.py (btk-probe-evidence/1). No runtime dependencies.
 * Same names, same accept/reject rules and same JSON output as the Python module;
 * scripts/twin_parity.py checks the two agree. Missing or truncated observations are
 * never equivalent: coverage says what was examined, and skipped scope goes in not_examined.
 */

export const SCHEMA = 'btk-probe-evidence/1';
export const COVERAGE = ['complete', 'partial', 'unknown'];

function text(name, value) {
  if (typeof value !== 'string' || value.trim() === '') throw new TypeError(`${name} must be a non-empty string`);
  return value;
}
function texts(name, values) {
  if (!Array.isArray(values)) throw new TypeError(`${name} must be a list`);
  return values.map(value => text(name, value));
}

/** Return the value if it is a bare http(s) origin (scheme, host, optional port), without a trailing slash. */
export function origin(value) {
  text('origin', value);
  let url;
  try { url = new URL(value); } catch { throw new TypeError('origin must be an http(s) URL with a host'); }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new TypeError('origin must be an http(s) URL with a host');
  if (!url.host) throw new TypeError('origin must be an http(s) URL with a host');
  const rest = value.slice(value.indexOf(url.host) + url.host.length);
  const path = rest.split(/[?#]/, 1)[0];
  if (path !== '' && path !== '/') throw new TypeError('origin must not carry a path, query, fragment or credentials');
  if (rest.includes('?') || rest.includes('#')) throw new TypeError('origin must not carry a path, query, fragment or credentials');
  if (url.username || url.password) throw new TypeError('origin must not carry a path, query, fragment or credentials');
  return value.replace(/\/+$/, '');
}

/** One claim with its source, coverage ('complete' | 'partial' | 'unknown') and limits. */
export function finding(claim, source, coverage, limitations = []) {
  if (!COVERAGE.includes(coverage)) throw new TypeError(`coverage must be one of ${COVERAGE.join(', ')}`);
  return {
    claim: text('claim', claim),
    source: text('source', source),
    coverage,
    limitations: texts('limitation', limitations),
  };
}

/** Assemble the evidence. overall is 'complete' only when every finding is complete and nothing was skipped;
 * no findings means 'unknown'; anything else is 'partial'. */
export function envelope(target_origin, findings, not_examined = []) {
  if (!Array.isArray(findings)) throw new TypeError('findings must be a list');
  const items = findings.map(f => finding(f?.claim, f?.source, f?.coverage, f?.limitations));
  const skipped = texts('not_examined', not_examined);
  let overall;
  if (items.length === 0) overall = 'unknown';
  else if (items.every(item => item.coverage === 'complete') && skipped.length === 0) overall = 'complete';
  else overall = 'partial';
  return {
    schema: SCHEMA,
    target: {origin: origin(target_origin)},
    overall,
    findings: items,
    not_examined: skipped,
  };
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, sortKeys(value[key])]));
  }
  return value;
}

/** Deterministic JSON text (sorted keys, no extra whitespace), matching the Python to_json. */
export function to_json(evidence) {
  return JSON.stringify(sortKeys(evidence));
}
