/**
 * Electron & browser app state inspection, probe snippet generation, and state diffing.
 * Twin JavaScript ES Module for scripts/app_inspector.py.
 */

export const SCHEMA = "btk-app-inspector/1";

export const PROBE_SCRIPT_JS = `(function() {
  var globalKeys = [];
  try {
    for (var k in window) {
      if (Object.prototype.hasOwnProperty.call(window, k) && !k.startsWith('__')) {
        globalKeys.push(k);
      }
    }
  } catch(e) {}

  var frameworks = [];
  if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__ || document.querySelector('[data-reactroot]')) frameworks.push('react');
  if (window.__VUE__ || window.Vue) frameworks.push('vue');
  if (window.angular || document.querySelector('[ng-version]')) frameworks.push('angular');
  if (window.process && window.process.versions && window.process.versions.electron) frameworks.push('electron');

  var isElectron = !!(window.process && window.process.versions && window.process.versions.electron);
  var electronApi = !!(window.electronAPI || window.electron || (window.require && typeof window.require === 'function'));

  return JSON.stringify({
    schema: 'btk-app-inspector/1',
    title: document.title || '',
    url: window.location ? window.location.href : '',
    user_agent: navigator ? navigator.userAgent : '',
    viewport: { width: window.innerWidth || 0, height: window.innerHeight || 0 },
    frameworks: frameworks,
    is_electron: isElectron,
    has_electron_api: electronApi,
    global_keys: globalKeys.slice(0, 100)
  });
})();`;

export function extractAppFacts(rawState) {
  let raw = {};
  if (typeof rawState === 'string') {
    try { raw = JSON.parse(rawState); } catch(e) {}
  } else if (rawState && typeof rawState === 'object' && !Array.isArray(rawState)) {
    raw = rawState;
  }

  const title = String(raw.title ?? raw.page_title ?? '').trim();
  const url = String(raw.url ?? raw.href ?? '').trim();
  const userAgent = String(raw.user_agent ?? raw.userAgent ?? '').trim();

  const viewportRaw = (raw.viewport && typeof raw.viewport === 'object') ? raw.viewport : {};
  const vw = Number(viewportRaw.width ?? 0.0);
  const vh = Number(viewportRaw.height ?? 0.0);

  let frameworks = [];
  if (Array.isArray(raw.frameworks)) {
    const setF = new Set(raw.frameworks.map(f => String(f).toLowerCase()).filter(Boolean));
    frameworks = Array.from(setF).sort();
  }

  const isElectron = Boolean(raw.is_electron ?? raw.isElectron ?? frameworks.includes('electron'));
  const hasElectronApi = Boolean(raw.has_electron_api ?? raw.hasElectronApi ?? raw.electronAPI);

  let globalKeys = [];
  const globalsIn = raw.global_keys ?? raw.globalKeys ?? raw.globals;
  if (Array.isArray(globalsIn)) {
    const setG = new Set(globalsIn.map(k => String(k)).filter(Boolean));
    globalKeys = Array.from(setG).sort();
  }

  return {
    schema: SCHEMA,
    title,
    url,
    user_agent: userAgent,
    viewport: { width: vw, height: vh },
    frameworks,
    is_electron: isElectron,
    has_electron_api: hasElectronApi,
    global_keys: globalKeys,
  };
}

export function buildBrowserProbeScript(options) {
  return PROBE_SCRIPT_JS;
}

export function diffAppStates(before, after) {
  const b = extractAppFacts(before);
  const a = extractAppFacts(after);

  const bgSet = new Set(b.global_keys);
  const agSet = new Set(a.global_keys);

  const addedGlobals = Array.from(agSet).filter(x => !bgSet.has(x)).sort();
  const removedGlobals = Array.from(bgSet).filter(x => !agSet.has(x)).sort();

  const bfSet = new Set(b.frameworks);
  const afSet = new Set(a.frameworks);
  const addedFrameworks = Array.from(afSet).filter(x => !bfSet.has(x)).sort();

  const urlChanged = (b.url !== a.url);
  const titleChanged = (b.title !== a.title);
  const electronApiChanged = (b.has_electron_api !== a.has_electron_api);

  const hasChanges = Boolean(addedGlobals.length || removedGlobals.length || addedFrameworks.length || urlChanged || titleChanged || electronApiChanged);

  return {
    schema: SCHEMA,
    has_changes: hasChanges,
    title_changed: titleChanged,
    url_changed: urlChanged,
    electron_api_changed: electronApiChanged,
    before_url: b.url,
    after_url: a.url,
    added_globals: addedGlobals,
    removed_globals: removedGlobals,
    added_frameworks: addedFrameworks,
  };
}
