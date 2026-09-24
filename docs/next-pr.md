# Evidence contract hardening

Follow-up work from PR #2 final review.

- Extract Node evidence validation into `scripts/check_node_evidence.py`.
- Add regression tests for exact desktop/mobile project identity and retry artifacts.
- Keep browser cleanup best-effort so cleanup failures cannot mask the original failure.
- Merge additional evidence anti-patterns into the main catalog schema.
- Update GitHub Actions versions where compatible to remove Node 20 deprecation warnings.

This file seeds the follow-up PR; implementation should preserve the evidence contracts established by PR #2.
