# Agent decision log

## Day 4 — HTTP boundary

### Accepted: section 6.1 precedence over pydantic error order

What it produced:
`_map_validation_error` reports the first interpretation failure in section 6.1
table order: `MISSING_REQUIRED_FIELD`, then `INVALID_FIELD_VALUE`, then
`UNKNOWN_FIELD`. A body that is both missing a required field and carrying an
unknown field returns `MISSING_REQUIRED_FIELD`.

Decision: accepted.

Reason:
Contract section 6.1 lists the interpretation codes in that order. Section 4.1
already establishes that when more than one rule could fail, the contract fixes
which code the caller sees. The same reasoning applies at the interpretation
boundary. Rejected: returning whichever error pydantic listed first. That order
is a library detail the portal cannot rely on, and it would make the response
depend on field declaration order rather than on the contract.

### Accepted: non-object JSON body is MALFORMED_JSON

What it produced:
A body that parses as JSON but is not an object (a list, a string, a number)
returns `MALFORMED_JSON` at status `400`.

Decision: accepted.

Reason:
Section 5.2 says the caller may rely on `field` for `INVALID_FIELD_VALUE`. A
non-object body has no field to name. Inventing a field name the caller never
sent would put a lie in `detail`. `MALFORMED_JSON` is the code whose `detail`
guarantees no keys, which matches the situation. Rejected: inventing
`INVALID_FIELD_VALUE` with a synthetic `field`.

### Accepted: document routing-level responses in section 6.6

What it produced:
Contract section 6.6 states that a 404 on an undefined path or a 405 on a wrong
method is the framework's ordinary response, not a code in the 6.5 closed set
and not the section 5 envelope.

Decision: accepted.

Reason:
The acceptance criterion requires every response the service can produce to
appear in section 6. Sections 1–3 are fixed; section 6 is editable. Naming the
routing responses as outside the closed set meets the criterion without growing
the set of codes the portal branches on. Rejected: inventing an
`UNKNOWN_ENDPOINT` code. That would be a compatible change under section 1, but
it would force every caller to handle a condition that is not a notification
refusal.

### Accepted: dependency detail is built, not forwarded

What it produced:
`PolicyLookupFailed` maps to 504 / 503 / 502 with
`detail == {"dependency": "policy_master"}`. The exception's `policy_number` is
not included.

Decision: accepted.

Reason:
Section 5.2 forbids caller field names on dependency failures. Including
`policy_number` would imply a defect in the submission when the dependency did
not answer. Rejected: dumping the exception attributes into `detail`.

## Day 3

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

Failing commit: `07a47430fa7342c50738927d39ce0edb5ca84115` (added `tests/unit/test_gate_probe.py` with `assert False`; same commit reappears on this branch after history rewrite as `711d2b790524168f9b6ded553f114335f82486e6`)

What GitHub showed:
- Checks: workflow `checks` concluded **FAILURE** (red). Job: https://github.com/atharvcoforge/claim-intake-atharv/actions/runs/34241244625/job/102111660710
- Merge state via `gh pr view`: `mergeable=MERGEABLE`, `mergeStateStatus=UNSTABLE` (Able to merge; not blocked)
- The failed check is listed on the PR rollup as `checks`, but branch-protection / ruleset APIs returned 403 on this private free-plan repo, so the check is **not** enforced as a required status that prevents merge

Blocked: no

If no: branch protection does not require the checks workflow, so a failing check marks the PR but does not block merge. That is a repository configuration finding, not something to work around in code.
