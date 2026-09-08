# Agent decision log (Day 3)

## Accepted: keep V-6 out of POLICY_RULES

What it produced:
POLICY_RULES holds only the pure policy-field rules in contract order: V-2, V-7, V-3, V-4, V-5. submit_notification calls repository.find_matching after evaluate_notification returns None, then records only if that check also passes.

Decision: accepted.

Reason:
Contract section 4.1 puts V-6 last and says a notification that fails any policy rule is refused without a duplicate check. WI-0151 AC-3 says a prior rejected submission is not a duplicate because nothing was recorded. Putting find_matching inside POLICY_RULES would either pull the repository into the decision list or run a storage check before policy rules finish. Keeping V-6 in submit_notification keeps deciding separate from doing and still matches the contract order V-1 through V-6.

## Corrected: duplicate claim_reference on ValidationOutcome

What it produced:
An early draft put the existing recorded claim_reference on ValidationOutcome.claim_reference when V-6 failed, because WI-0151 AC-2 requires that reference on the refusal.

Decision: corrected. The existing reference is only in RuleFailure.detail["claim_reference"]. ValidationOutcome.claim_reference is set only when accepted is true (the reference just issued).

Reason:
Contract section 5.2 and WI-0151 AC-2 place the existing claim_reference in the error detail object, not on the success field. Day 3's ValidationOutcome uses claim_reference for an accepted recording. Putting the prior reference there on a refusal would either violate the accepted/failure invariant enforced by __post_init__, or hand Day 4 an outcome that looks like it issued a reference when accepted is false. A skim that only checked "AC-2 mentions claim_reference somewhere" would have missed the wrong field.

## Pipeline gate observation

PR: https://github.com/atharvcoforge/claim-intake-atharv/pull/1

Failing commit: `07a47430fa7342c50738927d39ce0edb5ca84115` (added `tests/unit/test_gate_probe.py` with `assert False`)

What GitHub showed:
- Checks: workflow `checks` concluded **FAILURE** (red). Job: https://github.com/atharvcoforge/claim-intake-atharv/actions/runs/34241244625/job/102111660710
- Merge state via `gh pr view`: `mergeable=MERGEABLE`, `mergeStateStatus=UNSTABLE` (Able to merge; not blocked)
- The failed check is listed on the PR rollup as `checks`, but branch-protection / ruleset APIs returned 403 on this private free-plan repo, so the check is **not** enforced as a required status that prevents merge

Blocked: no

If no: branch protection does not require the checks workflow, so a failing check marks the PR but does not block merge. That is a repository configuration finding, not something to work around in code.
