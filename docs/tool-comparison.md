# Tool comparison: Cursor vs Grok 4.6

For this lab I split one bounded piece of work across two tools. In Cursor I
wired the `POST /notifications` error mapping in `src/claims/api/routes.py`. In
Grok 4.6, on a separate worktree so the edits could not collide, I wrote the
`Dockerfile` and `.dockerignore` that keep `src/claims/` and `data/` as siblings
under `/app`.

## What each tool made easy

**Cursor (routes mapping).** Day 4 is not hard because FastAPI is hard. It is hard
because you have to decide what a `ValidationError` means when pydantic returns
several errors at once, what to do with a JSON array when section 5.2 promises a
`field` key on `INVALID_FIELD_VALUE`, and how to stop FastAPI’s own 422 envelope
from leaking onto the wire. Cursor kept the contract, the models, and the
failing integration tests in one place. The mapping came out as a small function
with an explicit precedence list (`MISSING_REQUIRED_FIELD`, then
`INVALID_FIELD_VALUE`, then `UNKNOWN_FIELD`) and a clear note that we rejected
pydantic’s field order. The suite went green in the same pass, which is exactly
what you want when the failure mode you care about is “a structural problem came
back as a rule code.”

**Grok 4.6 (Dockerfile).** A Dockerfile is mostly careful transcription: base
image, copy `uv`, two-layer `uv sync`, non-root user, `EXPOSE`, `CMD`. Grok got a
working file out quickly and caught two gaps the plan had left vague. The first
layer needs `--no-install-project` while source is not on disk yet, and `uv run`
as a non-root user will re-sync and pull dev deps unless `UV_NO_DEV=1` and
`UV_NO_SYNC=1` are set. That is the kind of concrete miss a build-focused pass is
good at finding.

## What each tool made awkward

**Cursor.** Pointing Cursor at the Dockerfile alone is overkill. The risk is not
design taste; it is whether the image actually boots. Sitting in a long reasoning
session about layer order without a build daemon in the loop is a waste of time.

**Grok 4.6.** Asking it to invent the section 6.1 precedence call from a short
prompt is the wrong job. That decision needs the contract open next to the test
that fails if precedence is wrong. Without that shared context, a fast model
leans on pydantic’s error order and treats the job as done. That is the
alternative this lab is meant to reject.

## Preference

For **contract-bound HTTP boundary work** (status codes, envelopes, detail shapes
where a wrong code sends a handler down the wrong path) I reach for Cursor. The
real work lives in the gap between the document and the test suite, and that gap
needs a workspace that stays open.

For **mechanical packaging** (Dockerfile, `.dockerignore`, lockfile-driven install
layers) I reach for Grok 4.6. The feedback loop is “does the image build, and does
`__file__` still resolve under `/app/src/...`?”, not “does this refusal match
section 5.2.” A fast pass plus a build check is enough.
