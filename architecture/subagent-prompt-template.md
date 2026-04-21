# Subagent prompt template

Paste this **at the end** of every Agent() prompt. Without this, subagent work is lost when the agent returns — its edits persist on disk but its reasoning, decisions, and open questions evaporate.

---

```
REPORT CONTRACT (mandatory — do not skip):

Before your final message, call `ingest_subagent_report` via the claudeorch-comms MCP. Fields:

- did: one-line summary of what you accomplished (required)
- changed_files: paths of files you Edited/Wrote
- decisions: each non-trivial choice as {category, chosen, alternatives?, reason}
  — library picks, interface shapes, trade-offs. Skip if you made no non-trivial
  choices; don't fabricate entries.
- questions: anything you couldn't resolve and need opus to decide
- memory_notes: facts worth remembering *permanently* (goes into shared memory).
  Only include observations future sessions will benefit from — not obvious
  or transient details.

If you didn't change any code (e.g. research-only task), still call the tool
with did + any decisions/notes. The report is what makes your work durable.

In your final message body, summarize the *outcome* for opus in plain prose —
do not re-emit the report JSON there.
```

---

## Why this contract exists

In the solo-opus model, subagents are ephemeral — they run during an `Agent()` call and die when it returns. Anything that isn't (a) a file on disk or (b) written through `ingest_subagent_report` or `log_decision` is lost.

The contract ensures:
- **Chronology survives** — `memory/session-log.md` gets one block per completion.
- **Decisions are queryable** — `.claudeorch/decisions.duckdb` via DecisionLog.
- **Long-term wisdom accumulates** — `memory/shared.md` collects durable notes.
- **Opus sees gaps** — `questions[]` surface unresolved items before they're forgotten.

Rule #1 of the Groft charter ("user doesn't explain twice") depends on this. If subagents don't report, memory has holes; if memory has holes, next session starts from scratch.
