# Claims Intake Service: API Contract

Version 0.4. Owned by the claims intake team. Consumed by the claims portal team.

This document is the authority on what the service accepts, what it returns, and under what conditions it refuses. Where the code and this document disagree, the document is correct and the code is a defect.

Sections 1 through 3 are fixed. Do not edit them.

## 1. Purpose and scope

The claims intake service accepts a first notice of loss from the claims portal, validates it against the policy master and a table of business rules, and either records a notification and issues a claim reference or refuses the submission with a specific reason.

**In scope.** Accepting a notification, validating it, and recording it. Issuing a claim reference. Reporting the reason a notification was refused.

**Out of scope.** Adjusting, reserving, payment, and any decision about coverage beyond the rules in section 4. The service decides whether a notification is well formed and admissible. It does not decide whether the claim will be paid.

**The policy master is a dependency, not part of this service.** The service reads policy records from it and does not write to it. A policy that cannot be read is a condition this contract specifies, and it is specified separately from a policy that does not exist, because the two require different action from the caller.

**Compatibility.** Adding a field to a response is a compatible change and callers must ignore fields they do not recognize. Adding a new error code is a compatible change and callers must fall through to default handling for a code they do not recognize. Changing the meaning of an existing code, removing a field, or changing a status code for an existing condition is not compatible and does not happen without a version increment agreed with the portal team.

## 2. Request

### 2.1 Endpoint

```
POST /notifications
Content-Type: application/json
```

### 2.2 Body

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `policy_number` | string | yes | Identifier as held in the policy master. Not empty. |
| `loss_date` | string | yes | Calendar date, `YYYY-MM-DD`. |
| `claim_type` | string | yes | One of the values in 2.3. Not empty. |
| `estimated_amount` | decimal | yes | United States dollars, two decimal places. Greater than zero. |
| `description` | string | no | Free text. Absent and `null` are equivalent. |

The service rejects a body carrying a field not listed above. A misspelled field name is a defect in the caller's code, and accepting the payload with the field ignored would record a notification built from data the caller did not send.

### 2.3 Claim type vocabulary

`collision`, `theft`, `glass`, `liability`, `weather`.

Which of these are admissible on a given notification depends on the product the policy is written on. The vocabulary is fixed by this contract. The permitted subset is a property of the policy record and is evaluated by rule `V-5`.

### 2.4 Well formed against acceptable

A request that cannot be interpreted is refused with status `400`. This means the body was not valid JSON, a required field was absent, a field carried a value of the wrong type, or a field was present that this contract does not define. The caller's code is wrong.

A request that was interpreted and whose content is not admissible is refused with status `422`. The caller's data is wrong, and a person needs to see the reason.

This split is stated here once and holds without exception everywhere else in this document.

## 3. Success response

A notification that passes every rule in section 4 is recorded and the service responds:

```
201 Created
Content-Type: application/json

{
  "claim_reference": "CLM-2026-000317",
  "status": "recorded"
}
```

**`claim_reference`** matches the pattern `CLM-YYYY-NNNNNN`, where `YYYY` is the calendar year in which the notification was recorded and `NNNNNN` is a zero padded sequence. A claim reference is unique across all recorded notifications and is never reissued. It is the value the claims handler quotes and the value every downstream system keys on.

**`status`** is `recorded` on every success response this contract defines. It exists because the portal displays it and because a future state that is not `recorded` is foreseeable. Callers must not treat it as constant.

A refused notification is never recorded and no claim reference is issued. There is no partial outcome: either a notification exists with a reference, or nothing was written.

## 4. Validation

### 4.1 Evaluation order

Rules are evaluated in the order listed below, not in ascending
identifier order. Evaluation stops at the first failure. The caller
receives that rule's error code and status. When more than one rule
would fail, only the first failure in this order is reported; the
service does not collect or return multiple violations.

```
V-1 → V-2 → V-7 → V-3 → V-4 → V-5 → V-6
```

V-1 short circuits. If it fails, no rule that reads a policy field is
evaluated.

V-7 is evaluated before V-3. A policy that is cancelled and whose
original term has also ended can fail both rules, but the handler must
be told the policy was cancelled, not that the loss is after expiry
(WI-0158, AC-4). Ascending identifier order would report
`LOSS_AFTER_EXPIRY` first and send the handler to the wrong system to
investigate.

V-6 is evaluated last. It compares against recorded notifications, not
policy fields. A notification that fails any policy rule is refused
without a duplicate check; a prior rejected submission with the same
triple is not recorded and cannot be a duplicate (WI-0151, AC-3).

**Concurrent failures.** Beyond the V-1 short circuit, the same rule
applies throughout: the service evaluates rules in the order above and
stops at the first whose pass condition is not met. Every rule that
follows the failure is skipped. The caller receives exactly one
refusal, not a summary of every rule that would have failed.

The response is the standard error envelope defined in section 5. Its
`code` is the error code of the rule that failed. Its HTTP status is
that rule's status from section 4.2. No other failed rule contributes
a code, a status, or an entry in `detail`. The notification is not
recorded and no claim reference is issued.

Where several rules would fail, the order in this section is the only
authority on which code the caller sees. A loss before inception and an
amount above the limit fails V-2 and V-4; the caller receives
`LOSS_BEFORE_INCEPTION` at status `422` because V-2 precedes V-4. A
cancelled policy whose original term has ended fails V-7 and V-3; the
caller receives `POLICY_CANCELLED` at status `422` because V-7
precedes V-3 (WI-0158, AC-4).

### 4.2 Rule table

| ID  | Condition                                      | Code                    | Status |
| --- | ---------------------------------------------- | ----------------------- | ------ |
| V-1 | `policy_number` exists in the policy master as an exact character match, including letter case | `POLICY_NOT_FOUND`      | 422    |
| V-2 | `loss_date` >= policy `effective_date`         | `LOSS_BEFORE_INCEPTION` | 422    |
| V-3 | `loss_date` <= policy `expiry_date`            | `LOSS_AFTER_EXPIRY`     | 422    |
| V-4 | `estimated_amount` <= policy `limit`           | `AMOUNT_EXCEEDS_LIMIT`  | 422    |
| V-5 | `claim_type` is a section 2.3 vocabulary value permitted on the policy's product | `TYPE_NOT_COVERED`      | 422    |
| V-6 | no recorded notification N exists with N.`policy_number` = `policy_number` and N.`loss_date` = `loss_date` and N.`claim_type` = `claim_type` | `DUPLICATE_NOTIFICATION` | 409    |
| V-7 | policy `cancellation_date` is null or `loss_date` < policy `cancellation_date` | `POLICY_CANCELLED` | 422    |

Boundaries are inclusive as written. A loss on the inception date is
covered (WI-0142, AC-3). An amount equal to the limit is within cover.
A loss on the cancellation date is not covered; cancellation takes effect
at the start of that date (WI-0158, AC-2). A notification matching a
previous submission that was rejected is not a duplicate; only recorded
notifications are compared (WI-0151, AC-3).

V-1 compares `policy_number` to the identifier as held in the policy
master as an exact character sequence. The comparison is case-sensitive.
A value that differs only in letter case is not that identifier. The
policy master answers with no match, and the caller receives
`POLICY_NOT_FOUND`.

V-5 is reached only when `claim_type` is one of the five values in
section 2.3. A string outside that vocabulary is not a claim type this
service can interpret. It is refused as `INVALID_FIELD_VALUE` during
request interpretation (section 6.1) and no rule in this section runs.
V-5 decides whether a vocabulary value is permitted on the product. It
does not decide whether a string is a claim type.

## 5. Error envelope

Every refusal defined in this contract returns a JSON body with the same
top-level shape:

```
Content-Type: application/json

{
  "code": "<error code>",
  "message": "<human-readable explanation>",
  "detail": { ... }
}
```

The HTTP status is not carried in the body. It is the status line of the
response and is determined by the error code according to section 6.

### 5.1 Stable and unstable fields

**`code`** is a stable promise. It identifies the condition that caused
the refusal. The portal branches on `code`. The set of codes this
contract defines is fixed for version 0.4. A caller that receives a code
it does not recognize must fall through to default handling (section 1,
compatibility).

**`message`** is not a stable promise. It exists for display and for
operators reading logs. The service may change its wording without a
version increment. Callers must not parse `message`, match it against
strings, or use it to decide what happened.

**`detail`** is a stable promise at the level of presence: every error
response includes a `detail` object. The keys inside `detail` are not
uniform across codes. A caller may rely only on the keys this section
or section 6 explicitly guarantees for the `code` it received. Keys
present for one code may be absent for another, and code that assumes a
fixed `detail` schema across all failures will mis-handle refusals
whose `detail` shape differs.

### 5.2 What callers may rely on inside `detail`

**Validation rule failures** (`LOSS_BEFORE_INCEPTION`,
`LOSS_AFTER_EXPIRY`, `AMOUNT_EXCEEDS_LIMIT`, `TYPE_NOT_COVERED`,
`POLICY_CANCELLED`, `POLICY_NOT_FOUND`). The caller may rely on
`policy_number`, present on every code in this group. The caller may
also rely on the field or date that caused the refusal when this
section names it for that code:

| Code | Additional keys the caller may rely on |
| --- | --- |
| `LOSS_BEFORE_INCEPTION` | `loss_date`, `effective_date` |
| `LOSS_AFTER_EXPIRY` | `loss_date`, `expiry_date` |
| `AMOUNT_EXCEEDS_LIMIT` | `estimated_amount`, `limit` |
| `TYPE_NOT_COVERED` | `claim_type`, `permitted_claim_types` |
| `POLICY_CANCELLED` | `loss_date`, `cancellation_date` |
| `POLICY_NOT_FOUND` | none beyond `policy_number` |

The caller may not rely on any other key in `detail` for these codes.
The service does not return a rule identifier in `detail`; the mapping
from code to rule is defined in section 4.2.

**`DUPLICATE_NOTIFICATION`.** The caller may rely on `policy_number`,
`loss_date`, `claim_type`, and `claim_reference`. The
`claim_reference` value is the reference of the existing recorded
notification (WI-0151, AC-2). The caller may not rely on any other key.

**Request interpretation failures** (status `400`, section 2.4). The
caller may rely on `code` to distinguish which interpretation check
failed. For `MISSING_REQUIRED_FIELD` and `UNKNOWN_FIELD`, the caller may
rely on `field`, naming the body field at issue. For
`INVALID_FIELD_VALUE`, the caller may rely on `field` and `reason`. For
`MALFORMED_JSON`, the caller may not rely on any key in `detail`; the
body could not be read as JSON and no field name is available. The
caller may not rely on policy master fields appearing in `detail` for
these codes; the request was not admissible for evaluation.

**Policy master dependency failures** (status in the `5xx` family,
section 6). The caller may rely on `dependency`, which is always
`policy_master`. The caller may not rely on `field`, `policy_number`, or
any value taken from a policy record. The failure is not in the
notification the portal sent; including caller field names would imply
a defect in the submission when the dependency did not answer.

### 5.3 Worked examples

The three examples below are refusals the service produces through
different handling paths. Their `detail` objects do not share the same
keys.

**Example 1 — validation rule failure.** A loss on the day cancellation
takes effect. Rule V-7 fails.

```
422 Unprocessable Entity
Content-Type: application/json

{
  "code": "POLICY_CANCELLED",
  "message": "Cover ended when the policy was cancelled.",
  "detail": {
    "policy_number": "MOT-4497",
    "cancellation_date": "2026-01-15",
    "loss_date": "2026-01-15"
  }
}
```

**Example 2 — request the service could not interpret.** The portal
omitted a required field. Section 2.4 applies; no rule in section 4 is
evaluated.

```
400 Bad Request
Content-Type: application/json

{
  "code": "MISSING_REQUIRED_FIELD",
  "message": "Required field estimated_amount is absent.",
  "detail": {
    "field": "estimated_amount"
  }
}
```

**Example 3 — policy master did not answer.** The service attempted to
read the policy master for rule V-1 and the dependency timed out. The
notification was not evaluated against business rules.

```
504 Gateway Timeout
Content-Type: application/json

{
  "code": "POLICY_MASTER_TIMEOUT",
  "message": "The policy master did not respond within the allowed time.",
  "detail": {
    "dependency": "policy_master"
  }
}
```

## 6. Status code mapping

Every refusal the service produces has exactly one error code. Every
error code maps to exactly one HTTP status. Two codes never describe
the same condition.

Interpretation of the body (section 2.4) is evaluated before any rule
in section 4. Policy master dependency failures are evaluated when the
service attempts V-1. They are distinct from V-1 itself: a policy that
does not exist is a 422; a policy master that does not answer is a 5xx.

### 6.1 Request interpretation — 400

The caller's code is wrong. No rule in section 4 is evaluated. No
notification is recorded.

| Condition | Code | Status |
| --- | --- | ---: |
| Body is not valid JSON | `MALFORMED_JSON` | 400 |
| A required field is absent | `MISSING_REQUIRED_FIELD` | 400 |
| A field carries a value of the wrong type, or a value that does not satisfy the type constraints in section 2.2 | `INVALID_FIELD_VALUE` | 400 |
| A field is present that section 2.2 does not define | `UNKNOWN_FIELD` | 400 |

`INVALID_FIELD_VALUE` is the code for a named field whose value the
service cannot treat as the type section 2.2 requires. That includes a
JSON value of the wrong JSON type, a `claim_type` that is not one of
the five values in section 2.3, and an `estimated_amount` that does not
have exactly two decimal places. The service does not round, truncate,
or otherwise coerce a value onto the required type; doing so would
record a notification built from data the caller did not send. The
`field` and `reason` keys in `detail` distinguish those cases for
operators. Callers branch on `code`, not on `reason`.

`estimated_amount` is checked on its written form. It must arrive as a
JSON string with exactly two fractional digits. A JSON number is the
wrong type; a string with any other scale is `INVALID_FIELD_VALUE`. The
service does not coerce either case onto a two-place decimal, because a
JSON number has no scale to preserve and a mis-scaled string is not the
amount the caller sent.

### 6.2 Validation rules — 409 and 422

The request was interpreted. The content is not admissible, or it
conflicts with a recorded notification. The mapping is the Status
column of section 4.2, restated here so that section 6 is complete
without a cross-read.

| Condition | Code | Status |
| --- | --- | ---: |
| `policy_number` is not present in the policy master as an exact character match, including letter case | `POLICY_NOT_FOUND` | 422 |
| `loss_date` is earlier than policy `effective_date` | `LOSS_BEFORE_INCEPTION` | 422 |
| Policy `cancellation_date` is not null and `loss_date` >= `cancellation_date` | `POLICY_CANCELLED` | 422 |
| `loss_date` is later than policy `expiry_date` | `LOSS_AFTER_EXPIRY` | 422 |
| `estimated_amount` is greater than policy `limit` | `AMOUNT_EXCEEDS_LIMIT` | 422 |
| `claim_type` is one of the values in section 2.3 but is not in the policy's `permitted_claim_types` | `TYPE_NOT_COVERED` | 422 |
| `policy_number`, `loss_date`, and `claim_type` match a recorded notification | `DUPLICATE_NOTIFICATION` | 409 |

`POLICY_NOT_FOUND` is the policy master answering with no match. The
match is the identifier as held, character for character, including
letter case. That is the caller's data: the identifier they sent is not
a policy. It is not a dependency failure. `TYPE_NOT_COVERED` applies
only to a `claim_type` already in the section 2.3 vocabulary. A string
outside that vocabulary is `INVALID_FIELD_VALUE` under section 6.1 and
never reaches this table.

### 6.3 Policy master dependency — 5xx

The service could not complete V-1 because the policy master did not
return a usable answer. These three conditions are not the caller's
fault. No notification is recorded. No rule after V-1 is evaluated.

| Condition | Code | Status |
| --- | --- | ---: |
| The policy master did not respond within the allowed time | `POLICY_MASTER_TIMEOUT` | 504 |
| The policy master could not be reached | `POLICY_MASTER_UNREACHABLE` | 503 |
| The policy master returned a response the service could not parse | `POLICY_MASTER_INVALID_RESPONSE` | 502 |

These three codes are not interchangeable. Timeout, unreachability, and
an unparseable response require different operational action. They
share the 5xx family because retrying the same well-formed request can
succeed once the dependency recovers. They do not share a status,
because 504, 503, and 502 name those three conditions respectively.

### 6.4 Success

A notification that is well formed and passes every rule in section 4
returns status `201` with the body in section 3. That outcome has no
error code.

### 6.5 Closed set

The error codes this contract defines are:

```
MALFORMED_JSON
MISSING_REQUIRED_FIELD
INVALID_FIELD_VALUE
UNKNOWN_FIELD
POLICY_NOT_FOUND
LOSS_BEFORE_INCEPTION
POLICY_CANCELLED
LOSS_AFTER_EXPIRY
AMOUNT_EXCEEDS_LIMIT
TYPE_NOT_COVERED
DUPLICATE_NOTIFICATION
POLICY_MASTER_TIMEOUT
POLICY_MASTER_UNREACHABLE
POLICY_MASTER_INVALID_RESPONSE
```

A failure that is not in this list is a defect in the service, not an
unspecified condition the caller must handle. Adding a code is a
compatible change (section 1). Changing the status mapped to an
existing code is not.

### 6.6 Routing-level responses

The codes in section 6.5 describe refusals of a notification submission
on `POST /notifications`. A request that does not reach that surface —
an undefined path, or a method other than `POST` on `/notifications` —
is answered by the HTTP framework with its ordinary status
(`404 Not Found`, `405 Method Not Allowed`). Those responses are not
error codes in the closed set above and do not use the section 5
envelope. Inventing a portal-branchable code for them would grow the
set callers must handle for a condition that is not a notification
refusal.
