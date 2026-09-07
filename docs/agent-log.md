# Agent decision log — Day 3

## Accepted: V-6 kept outside `POLICY_RULES`

What it produced: `POLICY_RULES` is `(V-2, V-7, V-3, V-4, V-5)` only. `submit_notification` runs `repository.find_matching` after `evaluate_notification` returns `None`, and only then records.

Decision: accepted.

Reason: Contract section 4.1 places V-6 last and states that a notification that fails any policy rule is refused without a duplicate check. WI-0151 AC-3 says a prior rejected submission is not a duplicate because nothing was recorded. Putting a repository lookup inside `POLICY_RULES` would either mix deciding with doing or risk comparing against storage before policy rules finish. Keeping V-6 in `submit_notification` preserves both the contract order and the deciding/doing split.

## Rejected or corrected: existing claim reference on `ValidationOutcome.claim_reference` for duplicates

What it produced: An early design put the existing recorded notification's `claim_reference` on `ValidationOutcome.claim_reference` when V-6 failed, because WI-0151 AC-2 requires that reference in the refusal.

Decision: corrected. The reference lives only in `RuleFailure.detail["claim_reference"]`. `ValidationOutcome.claim_reference` is set only when `accepted` is true.

Reason: Contract section 5.2 / WI-0151 AC-2 require the existing reference in the error `detail`, not as a success field. C3's `ValidationOutcome` uses `claim_reference` for the reference just issued on acceptance. Putting the duplicate's reference there would make a refused submission look accepted to tomorrow's HTTP layer (`accepted` false but a reference present), or would force an invalid state that `__post_init__` already forbids. A careless review that only checked "AC-2 includes claim_reference somewhere" would have accepted the wrong field.

## Pipeline gate observation

PR: not opened yet (deferred; opener will complete this entry).

Failing commit: —

What GitHub showed: —

Blocked: —

When the PR is opened: push a deliberate non-test failure (for example an unused import so ruff fails), record whether the merge button is blocked or only marked, then revert that commit and fill this section with the observation. If merge is not blocked, that is a finding about repository branch protection, not something to work around.
