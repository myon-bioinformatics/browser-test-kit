# Python JUnit evidence

The primary Python lane uploads its ordinary pytest JUnit XML and the controlled
child's evidence as separate `junit-*` Actions artifacts (14 days, including
producer failure). Raw diagnostics are not published to Pages. The exact two XML
paths are inputs to the pinned shared JUnit identity collector; missing, malformed
or truncated reports fail collection. Ordinary pytest failures still fail the
producer and workflow.

The controlled child is intentionally red inside a green regression. It runs with
and without JUnit, checks both exit codes are 1, and uses the shared xprobe importer
to check failure/setup-error identities and sentinel redaction. Compact context
has `commit_sha=null`; this lane does not infer provenance from Git or connect the
canonical metadata producer.

The existing same-child bridge keeps native BTK status/phase evidence distinct from
JUnit identity. Its raw events, XML, exit receipt, compact output and evidence-board
summary are retained under `test-results/controlled-failure`. The wrapper/locked
lanes and Node reports are outside this collector's expected set.
