# Project instructions

## Scope and ownership

- Codex owns repository exploration, business-logic analysis, implementation, and review.
- The `ui` Codex role owns authorized UX/UI work: CSS, Tailwind, responsive layout, spacing, typography, colors, cards, tables, modals, visual hierarchy, and frontend styling. It uses `gpt-6.1-terra` with medium reasoning. The coordinator owns the final technical report.
- Do not change styling unless explicitly requested or necessary for functionality. In mixed PHP/HTML/CSS/JS files, edit only the requested logic or UI portion and preserve the other portion. Never format or rewrite the whole file to make a small fix.
- Still provide concise technical handoffs, changed files, and actual validation results so the coordinator and UI role can use them.

## Understand before changing

- Inspect the existing implementation before editing. Trace the actual frontend -> JavaScript -> API -> PHP -> database flow before modifying business logic.
- If information is missing, inspect relevant code/schema instead of guessing. Never invent tables, columns, APIs, business rules, or expected behavior.
- Prefer root-cause fixes, minimal changes, backward compatibility, and preservation of unrelated behavior. Do not change architecture without a request.
- Preserve existing user edits. Assign one writer per file and coordinate any overlapping changes.
- Never execute destructive database operations without explicit permission, including DROP, TRUNCATE, and bulk DELETE. Propose migrations and their effects before executing them.

## Coordinate business logic and UX/UI from one user request

The main Codex coordinator may delegate the UI portion of an authorized project task to the `ui` Codex role, using the existing Codex account. Do not invoke the Gemini/Antigravity bridge for project work.

1. Inspect the real implementation and dependencies, determine scope, and finish necessary business-logic work first. For UI-only tasks, assign scoped UI work directly after inspection. For small changes, the coordinator may edit directly. Do not call every role automatically.
2. Give the UI role a concise task with relevant file paths, existing behavior, constraints, and any API/field/handler contracts it must preserve. Assign one writer per file; finish dependent edits before the UI role writes the same file. Never send credentials, `.env`, or unrelated source.
3. Use the native `ui` role when available. Otherwise run `python .codex/run_agent.py ui "scoped task"` from the project root. The role uses `gpt-6.1-terra`, medium reasoning, workspace-write, and the current Codex login. Do not run both routes for the same work.
4. Review the actual diff against the authorized task and existing PHP/JS/business logic, IDs, field names, event handlers, and API contracts. Correct any regression. Validate the affected flow with relevant syntax checks or tests, and inspect desktop/mobile rendering when a runnable UI is available.
5. Report changed files, behavior, actual validation, and any remaining gaps. Do not treat an agent's claimed checks as proof without inspecting their results.

The UI role should favor simple, familiar interfaces: clear hierarchy, readable type, consistent spacing, restrained colors, and obvious controls. Preserve an existing product design system. Avoid decorative gradients, excessive colors, glowing effects, gratuitous cards, and visual changes that add no usability value. Check keyboard access, focus visibility, contrast, responsive behavior, and useful empty/error/loading states where relevant.

## Choose only necessary agents

Use the project agents selectively when delegation is useful; this instruction authorizes scoped delegation for future project tasks. Do not automatically spawn every role, duplicate an investigation, or spawn agents for work the coordinator can finish more cheaply. Custom agents must not spawn further agents.

| Task | Roles when delegation is useful |
| --- | --- |
| Find the file that calculates Storage Charge | explorer only |
| Find why Storage Charge is wrong | explorer if location is unknown, then logic; no implementation without a fix request |
| Implement a known small fix or typo | coder, or coordinator directly; reviewer only if risk warrants it |
| Implement a complex business requirement | explorer if needed -> logic -> coder -> reviewer |
| Check an existing change | reviewer only; use deeper logic analysis for complex business risks |
| Improve authorized UX/UI | ui, or coordinator directly for a small edit; reviewer only if risk warrants it |

Wait for dependent findings before implementation. Run only independent tasks in parallel. Close completed agent threads before starting replacement agents; the config allows at most two concurrently open subagent threads.

- `explorer`: read-only, `gpt-6-luna`, low reasoning; locate files and map flow.
- `logic`: read-only, `gpt-6.2-sol`, high reasoning; separate root cause from solution and provide a minimal plan.
- `coder`: workspace-write, `gpt-6.2-sol`, medium reasoning; verify and implement the authorized plan.
- `reviewer`: read-only, `gpt-6-luna`, medium reasoning; review the diff and affected flow for bugs. Escalate complex financial or status-flow uncertainty to deeper analysis instead of treating it as passed.
- `ui`: workspace-write, `gpt-6.1-terra`, medium reasoning; implement scoped UX/UI and responsive improvements while preserving behavior.

Only use models available to the current account. Recheck availability if authentication or workspace changes. Do not silently replace an unavailable model with a guessed slug. Role files set model/reasoning explicitly; changing a spawn override alone may not override those files.

Standalone role files follow Codex's custom-agent format. If the current client's delegation tools cannot select a custom role, use `python .codex/run_agent.py ROLE "scoped task"` to invoke that role with its exact instructions, model, reasoning, and sandbox. This launches one separate Codex CLI session, inherits authentication/provider settings, and disables further delegation in that session. For diagnosis requests use explorer/logic only; invoke coder or ui only for authorized implementation. Do not launch both a native subagent and the CLI runner for the same work. Keep these separate CLI invocations sequential unless the user requests independent parallel work; their process count is not controlled by the native subagent thread limit.

## Context and usage

- Search with `rg` before reading; start with narrow paths/symbols and read relevant ranges only.
- Avoid unnecessary repository-wide scans, vendor/, node_modules/, build/, generated files, and unrelated assets. Expand scope only with a clear reason.
- Reuse existing findings. Handoff file paths, function names, line references, and concise evidence instead of large code blocks.
- Use low reasoning for routine file lookup. Reserve deeper reasoning for complex analysis and risk.

## PHP / JavaScript / SQL checks

Apply these only where the project actually uses the relevant technology:

- Verify relative paths and PHP require/include paths.
- Preserve JSON response contracts and HTTP status semantics; prevent PHP warnings/notices from corrupting JSON.
- Check PDO/mysqli parameter binding, SQL injection, XSS, appropriate validation/escaping, and transaction boundaries.
- Check null database fields, empty/unexpected input, duplicate records, relationships, and frontend/backend field name mismatches.
- Verify date boundaries, database/server/frontend timezones, and Asia/Bangkok where applicable. Preserve established timezone behavior unless the task requires changing it.
- Verify VAT/WHT, financial units, rounding precision/order, inventory rules, and status transitions against existing implementation and requirements.

## Validation and reporting

- After implementation, inspect the diff and review the affected flow, syntax, and obvious runtime errors.
- Run relevant existing tests. If none exist, perform targeted checks and clearly state what was not tested.
- Review independently when the business/security/regression risk warrants it; routine low-impact edits do not require extra agents or new tests.
- Report changed files, behavioral changes, actual checks/results, and remaining gaps concisely. Never claim a check passed without running or inspecting it.
