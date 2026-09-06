# Prompt for Cursor: Sales Playbook UI

Use this prompt only after backend API contracts for sales profiles, playbooks, knowledge cards, and approvals have been merged or supplied as an explicit fixture.

```text
Read AGENTS.md, CLAUDE.md, docs/sales-agent-implementation-plan-ru.md,
docs/architecture/adr-0001-sales-conversation-layer.md, and the merged API
schemas/client types for the sales feature.

Work only in web/app. Do not change Python, migrations, domain enums, API
schemas, generated contracts, Business DNA schema, or backend tests. If an API
field needed by the UI does not exist, stop and report the missing contract;
do not invent it in frontend code.

Build the first Sales Playbook UI using the existing Flywheel design system:
1. Settings → Sales Playbook navigation and page shell.
2. Read-only overview of active playbook version and status.
3. Knowledge-card list with status, source, applicable condition and version.
4. Candidate review view with approve/reject controls only when the API exposes
   those actions.
5. Conversation sales panel showing SalesStage, customer goal, active
   objection, last SalesMove, next action and human-review reason.
6. Provenance display for knowledge IDs, business facts and customer evidence.
7. Loading, empty, error, permission-denied and read-only states.
8. Responsive behavior matching the existing mobile cabinet.

Constraints:
- UI and customer-facing text are English; owner-facing handoff is Russian.
- Do not imply that AI controls prices, discounts, bookings or policy.
- Clearly distinguish SalesStage from ProcessState.
- Do not expose raw internal prompts, secrets, hidden reasoning, tokens, phone
  numbers, email addresses or internal identifiers beyond existing safe API
  fields.
- Reuse existing components and styles before adding abstractions.
- Add focused component tests where the existing test setup supports them.
- Run the relevant frontend tests, typecheck and production build.

Before editing, list the exact API contracts and files you will use. At
handoff, report changed files, screenshots or visual verification performed,
commands run, results and missing backend contracts. Do not run git push.
```

