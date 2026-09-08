# Tool comparison: Cursor vs Grok 4.6

Bounded task for this lab: wire `POST /notifications` error mapping in
`src/claims/api/routes.py` (Cursor), and write the `Dockerfile` / `.dockerignore`
that keep `src/claims/` and `data/` as siblings under `/app` (Grok 4.6, in a
separate worktree so the file sets did not intersect).

## What each tool made easy

**Cursor (routes mapping).** The hard part of Day 4 is not FastAPI boilerplate.
It is deciding what a `ValidationError` becomes when pydantic returns several
errors at once, what a JSON array body becomes when section 5.2 guarantees a
`field` key for `INVALID_FIELD_VALUE`, and how to keep FastAPI's own 422 envelope
from leaking onto the wire. Cursor kept the contract, the models, and the
failing integration tests in one session. The mapping landed as a small function
with an explicit precedence list (`MISSING_REQUIRED_FIELD`, then
`INVALID_FIELD_VALUE`, then `UNKNOWN_FIELD`) and a note naming the rejected
alternative (pydantic's field order). The integration suite went green in the
same turn, which is what you want when the defect you fear is "a structural
failure returns a rule code."

**Grok 4.6 (Dockerfile).** The Dockerfile is mostly transcription: base image,
copy `uv`, two-layer `uv sync`, non-root user, `EXPOSE`, `CMD`. Grok produced a
working file quickly and caught two things the plan under-specified: the first
layer needs `--no-install-project` when source is not present yet, and
`uv run` as a non-root user re-syncs and pulls dev deps unless `UV_NO_DEV=1` and
`UV_NO_SYNC=1` are set. That is the kind of concrete gap a build-focused pass
is good at finding.

## What each tool made awkward

**Cursor.** For the Dockerfile alone, Cursor is overkill. The risk is not
design; it is whether the image boots. Spending a long session reasoning about
layer order without a build daemon in the loop wastes time.

**Grok 4.6.** Asking it to invent the section 6.1 precedence decision from a
short prompt is the wrong ask. The decision needs the contract open next to the
test that will fail if precedence is wrong. Without that shared context, a
fast model tends to follow pydantic's error order and call it done — which is
exactly the alternative this lab rejects.

## Preference

For **contract-bound HTTP boundary work** — mapping statuses, envelopes, and
detail shapes where a wrong code misleads a handler — I reach for Cursor. The
task lives in the distance between the document and the test suite, and that
distance needs a long-lived workspace.

For **mechanical packaging work** — Dockerfile, `.dockerignore`, lockfile-driven
install layers — I reach for Grok 4.6. The feedback loop is "does the image
build and does `__file__` still point at `/app/src/...`", not "does this
refusal match section 5.2," and a fast transcription pass with a build check is
enough.
