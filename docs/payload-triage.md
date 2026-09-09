# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification

| Payload | Outcome | Rule | Code | Status |
| --- | --- | --- | --- | --- |
| EDGE-01 | accepted | - | - | - |
| EDGE-02 | accepted | - | - | - |
| EDGE-03 | accepted | - | - | - |
| EDGE-04 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-05 | rejected | V-2 | LOSS_BEFORE_INCEPTION | 422 |
| EDGE-06 | rejected | V-4 | AMOUNT_EXCEEDS_LIMIT | 422 |
| EDGE-07 | rejected | V-1 | POLICY_NOT_FOUND | 422 |
| EDGE-08 | rejected | - | MISSING_REQUIRED_FIELD | 400 |
| EDGE-09 | rejected | V-5 | TYPE_NOT_COVERED | 422 |
| EDGE-10 | rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-11 | rejected | - | INVALID_FIELD_VALUE | 400 |
| EDGE-12 | rejected | - | INVALID_FIELD_VALUE | 400 |

## Decision log

Three payloads could not be classified against the contract as it shipped. Each paragraph states the ambiguity, the decision, the authority for it, and the reading that was rejected. The same decisions are written into `docs/api-contract.md`; they are not made here.

### Decision 1 — EDGE-07

The contract called `policy_number` the identifier as held in the policy master but did not say whether V-1 compares that identifier exactly or folds letter case, so `mot-4471` could be `POLICY_NOT_FOUND` or an accepted notification against `MOT-4471`. The service compares character for character, including case: `mot-4471` is not held in the master, so V-1 fails with `POLICY_NOT_FOUND` at `422` and no later rule runs. That follows WI-0142 AC-4 (an unknown `policy_number` is `POLICY_NOT_FOUND` and is not evaluated against later policy rules) and section 2.2 (the identifier as held). The rejected reading is to case-fold and accept. That would record a claim against a policy number the caller did not send, which is the same defect section 2.2 already refuses when it rejects unknown fields rather than ignoring them.

### Decision 2 — EDGE-11

Section 2.3 fixes the claim-type vocabulary and says V-5 evaluates the permitted subset, while section 2.4 splits an uninterpretable body (`400`) from an interpreted body that is not admissible (`422`). `flood` could therefore be `INVALID_FIELD_VALUE` at `400` or `TYPE_NOT_COVERED` at `422`. The service treats a string outside the five values in 2.3 as a value it cannot interpret: `INVALID_FIELD_VALUE` at `400`, and no rule in section 4 runs. That follows section 2.2 (`claim_type` is one of the values in 2.3), section 2.4 (the caller's code is wrong), and the 2.3 split between a vocabulary the contract owns and a product subset V-5 owns. The rejected reading is `TYPE_NOT_COVERED`. That code means a recognized claim type is not on the product; `flood` is not a recognized claim type, and returning it would send a handler to investigate cover for a portal vocabulary defect.

### Decision 3 — EDGE-12

Section 2.2 requires `estimated_amount` to be a decimal with two decimal places, but it did not say what happens when the value has three, so `3499.999` could be `INVALID_FIELD_VALUE` at `400` or parsed (and perhaps rounded) and then accepted on `MOT-4476`. The service refuses it as `INVALID_FIELD_VALUE` at `400` and does not round, truncate, or otherwise coerce the amount. That follows section 2.2 (two decimal places) and section 2.4 (a field whose value is not the required type is `400`; the caller's code is wrong). The rejected reading is to repair the scale and continue. Rounding `3499.999` to `3500.00` would record a notification built from an amount the caller did not send, which is the same reason section 2.2 rejects unknown fields rather than ignoring them.

## Day 2 reconciliation — model refusals against section 6

Checked every refusal `NotificationRequest` and `Policy` produce against contract section 6.1.

| Model refusal | Section 6.1 code | Status |
| --- | --- | ---: |
| Required field absent (EDGE-08) | `MISSING_REQUIRED_FIELD` | 400 |
| Extra / unknown field | `UNKNOWN_FIELD` | 400 |
| Empty `policy_number` | `INVALID_FIELD_VALUE` | 400 |
| `claim_type` outside section 2.3 (EDGE-11) | `INVALID_FIELD_VALUE` | 400 |
| Wrong-case `claim_type` | `INVALID_FIELD_VALUE` | 400 |
| `estimated_amount` as JSON number | `INVALID_FIELD_VALUE` | 400 |
| `estimated_amount` wrong scale / ≤ 0 (EDGE-12) | `INVALID_FIELD_VALUE` | 400 |
| `loss_date` with time component or `datetime` | `INVALID_FIELD_VALUE` | 400 |

`MALFORMED_JSON` is not a model outcome; it belongs at the HTTP boundary when the body cannot be read as JSON, or when it is valid JSON that is not an object (section 6.1).

Nothing was missing from section 6. No codes or statuses were added. How checked: enumerated the validators and `extra="forbid"` / `Field(min_length=1)` / `ClaimType` constraints in `src/claims/models.py`, mapped each to section 6.1, and confirmed the closed set in 6.5 already names every code those refusals become.
