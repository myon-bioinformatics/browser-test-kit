# Flutter diagnostics #128: scroll and failure preservation

Source repository: [flutter_navigation_basic](https://github.com/myon-bioinformatics/flutter_navigation_basic).
Source PR: [#128](https://github.com/myon-bioinformatics/flutter_navigation_basic/pull/128).
This record preserves the measured failure and its reusable lessons. It does not
declare the repair verified.

## Measured failure

- Source head: `ef5f10a50f5368561743fceae922e9cd956650ea`.
- Run: [36699102564](https://github.com/myon-bioinformatics/flutter_navigation_basic/actions/runs/36699102564).
- Job: `109834049543`, `evidence`; capture/assert step failed.
- Chromium, Firefox and WebKit timed out waiting for the exact
  `Metadata generated <canonical.generated_at>` text to pass `toBeVisible()`.
- mobile-webkit failed at `page.mouse.wheel(0, 400)` with
  `Mouse wheel is not supported in mobile WebKit`.
- The run reported four failed tests. This does not establish a timestamp-producer
  bug: the text lookup failed after the attempted scroll, and the underlying
  framework scroll/render behavior needs separate investigation.
- Failure upload succeeded: artifact
  `diagnostics-evidence-ef5f10a50f5368561743fceae922e9cd956650ea`,
  ID `11088912427`, 6,491,883 bytes, retention to 2026-10-14.
  The artifact listing establishes upload/preservation; it does not establish
  eight successful captures or four completed receipts.

The facts above were checked against the job log and artifact metadata on
2026-09-30. Raw bundles may expire; the textual incident remains in this repository.

## Repair state at documentation time

Head `8586e724988634764d863a94c85cecad3b5dd7aa` changed the target handling to
`scrollIntoViewIfNeeded()` followed by `toBeInViewport()` assertions.
That source change is an implementation attempt, not proof of successful Flutter
scrolling across all four projects. No successful repaired run is asserted here.

The workflow's intended success contract is Home plus Build diagnostics per project:
eight PNGs and four multi-capture receipts for chromium / firefox / webkit /
mobile-webkit. Receipts record SHA, commit timestamp, metadata generation timestamp,
viewport, browser version and PNG size/hash. The workflow keeps evidence upload
under `if: always()`.

## Portable lessons

- Choose interactions supported by every declared engine/profile. Mouse-wheel support
  cannot be assumed for mobile WebKit.
- Flutter may render/virtualize scrollable content independently of ordinary document
  scrolling and accessibility geometry. Prove that the operation moves the actual
  application scrollable; neither wheel dispatch nor DOM scrolling alone is proof.
- Require the intended content to intersect the screenshot viewport. A semantics node
  can exist without supplying the requested visual evidence.
- Keep Home and diagnostics as separate named scenarios. Screen/route confusion must
  be ruled out before attributing missing text to framework or producer behavior.
- Preserve failed captures/reports even while required success receipts are absent.
  Upload success and scenario success are distinct observations.
- Validate project × scenario identities and retry attempts. The initial workflow's
  raw four-receipt count is a consumer implementation detail, not the generic kit rule.
- Keep the scrolling helper in Flutter until a repaired run measures it across the
  declared projects. Share the incident and proof contract first.

## Verification to append after repair

Record the new head, run URL and artifact; require both named captures and completed
receipts for each project, with canonical SHA/timestamps asserted in the intended
viewport. Inspect the captured Home and diagnostics screens. Record skips or missing
projects explicitly. mobile-webkit remains device emulation.

Use the [shared screenshot guide](../screenshot-evidence.md) for receipt validation,
provenance, publishing and cross-repository adoption.
