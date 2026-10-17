# Shared browser execution ownership

`browser_execution.mjs` extracts the generic machinery first exercised by Flutter
PR #206. It imports Node standard libraries and the existing `interaction.mjs`
real-pointer helper; it does not launch/install a browser or add a dependency.

```js
import {workerBudget, explore} from './scripts/browser_execution.mjs';
// Playwright config: workers: workerBudget({override: process.env.MY_WORKERS})
const receipt = await explore(page, {
  route: '/sample', seed: 'recorded-seed', steps: 3,
  buttonName: /^(Add|Reset)$/,
  values: ['', '0', '日本語🙂'],
  ready: async page => { /* application readiness assertion */ },
});
```

Automatic worker count is min(4, available CPUs, reported/constrained memory per
2 GiB), minimum one. An explicit override accepts 1..32. Environment variable
names belong to callers; Playwright's own `--workers` still overrides its config.
Healthy worker/browser reuse, context teardown, failure replacement and queueing
remain Playwright responsibilities. No duplicate process supervisor is provided.

Exploration performs at most 20 operations, re-inventories visible controls each
step, and derives choices from seed + route + step independently of worker order.
`buttonName` defaults to no button presses. Only the caller's allowed buttons are
pressed. File/password inputs are excluded; unsupported native input types are
recorded as skipped. The caller supplies input values, including any xprobe
corpus it chooses to adapt. Numeric fields retain the initial conservative zero
input. No exhaustive coverage or business-output correctness is implied.

Receipts contain seed, route, step budget, action/value/label/URL and uncaught page
errors. `ExplorationError` retains the original cause and a partial `.receipt`;
listeners are removed on success and failure. Applications own screenshots,
attachments, JUnit annotations, build identity and assertion policy.

## Existing boundaries

| Owner | Responsibility |
| --- | --- |
| browser-test-kit | Worker budget, page interaction/inventory, seeded exploration, screenshots/evidence, `route_trail.py` emoji identities and ordered navigation |
| xprobe | Existing reproducible edge/factor corpora and JUnit failure-identity import; importing identity does not recreate inputs or execute the browser |
| BlueProbe (Aoi) | Existing saved-HTML extraction/comparison adapters and acquisition provenance; its `HtmlSource` explicitly does not own network acquisition |
| Flutter consumer | Its route catalogue, allowed buttons/values, Flutter readiness, expected business results and app/build evidence |

Do not add another emoji parser or route walker here. `route_trail.py` already
handles variation selectors, full ZWJ/skin-tone/flag/keycap identities, collisions
and ordered trails. `explore` operates on the current page; its route is an opaque
seed identity. Normalization and route selection remain with the existing tools.

## Verification ownership

`tests/browserless/browser_execution.spec.ts` checks CPU/memory caps, deterministic
choices, actual browserless Playwright worker overlap/replacement/remaining-case
completion, JUnit seed properties and partial-receipt/error cleanup. It uses the
existing browserless config and produces the existing lane's JUnit, without an
engine. `tests/node/browser_execution.spec.ts` checks real pointer and Unicode
input against HTML in the normal five-project lane. Existing emoji trail tests
remain the authority for identities; consumers do not duplicate these suites.

Consumers pin the exact upstream commit + blob SHA + SHA-256 and reuse the MIT
license. A checked-in source copy is immutable vendor input, not a second
implementation. Update upstream first and refresh the consumer lock. Flutter's
consumer PR depends on the upstream change in browser-test-kit PR #84.
