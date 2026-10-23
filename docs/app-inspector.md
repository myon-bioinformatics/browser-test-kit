# Electron & Browser Application State Inspector

`scripts/app_inspector.py` (Python stdlib-only) and `scripts/app_inspector.mjs` (Node ES module twin) provide structured state extraction, zero-dependency browser JS probe generation, and state diffing for inspecting and reverse-engineering Electron, React, or browser applications.

## Python Command-Line Usage

```sh
# Generate zero-dependency browser probe snippet
python -S scripts/app_inspector.py --generate-probe-script --out probe.js

# Extract structured app facts from JSON state or stdin
python -S scripts/app_inspector.py --file state.json

# Diff two app state snapshots for state mutations, url changes, or added globals
python -S scripts/app_inspector.py --diff state1.json state2.json
```

## Python One-Liners (`python -m` / `python -c`)

```sh
# Run installed module CLI to output probe JS
python -m app_inspector --generate-probe-script

# Python one-liner code snippet
python -c "import app_inspector; print(app_inspector.build_browser_probe_script())"
```

## Node ES Module Usage (`scripts/app_inspector.mjs`)

```js
import { extractAppFacts, buildBrowserProbeScript, diffAppStates } from './scripts/app_inspector.mjs';

const facts = extractAppFacts(rawState);
const probeScript = buildBrowserProbeScript();
const diff = diffAppStates(beforeState, afterState);
```

## Evidence Schema (`btk-app-inspector/1`)

Output state data adheres to schema `btk-app-inspector/1`:

```json
{
  "schema": "btk-app-inspector/1",
  "title": "Dashboard",
  "url": "https://localhost:8080/dashboard",
  "user_agent": "Mozilla/5.0 ...",
  "viewport": { "width": 1280, "height": 720 },
  "frameworks": ["electron", "react"],
  "is_electron": true,
  "has_electron_api": true,
  "global_keys": ["electronAPI", "myAppState"]
}
```
