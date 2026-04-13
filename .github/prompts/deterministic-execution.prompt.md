---
mode: ask
description: "Use this before implementation work when you want deterministic execution, explicit acceptance gates, and proof of results."
---
# Deterministic Execution Contract

Use this prompt whenever you want strict, verifiable delivery with no ambiguity.

## Task
{{task}}

## Scope
- In scope: {{in_scope}}
- Out of scope: {{out_of_scope}}

## Acceptance Criteria
1. {{criterion_1}}
2. {{criterion_2}}
3. {{criterion_3}}

## Required Checks
Run these and report outcomes in the final response.

1. {{check_command_1}}
2. {{check_command_2}}
3. {{check_command_3}}

## Execution Rules
1. Restate the task and acceptance criteria before coding.
2. Make the smallest coherent change set.
3. If any criterion cannot be satisfied, stop and report blocker with evidence.
4. Do not claim completion without running required checks.
5. Final response must include:
- Changed files list
- Exact acceptance criteria status: pass/fail per criterion
- Validation evidence: command summary and key output
- Residual risks and next step options

## Output Format
Return output in this order:
1. Result
2. Files Changed
3. Acceptance Criteria Status
4. Validation Evidence
5. Risks / Open Items
