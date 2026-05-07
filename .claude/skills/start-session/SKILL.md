---
name: start-session
description: Use when starting a new Claude Code session on the Airbnb DW project to orient the session, load project state, and surface what to work on next.
---

# Start Session

## Overview

Session startup routine for the Airbnb Cross-City Analytics DW project. Loads project context, checks AWS/git state, and orients the session to the current team member's next task.

## Steps (run in this order)

### 1. Load project context

Read `CLAUDE.md` — it has the full phase tracker, team roles, AWS credentials, and common commands. This is required before any other step.

### 2. Check git state

```bash
git status
git log --oneline -3
```

Note any uncommitted changes or unpushed commits to surface to the team member.

### 3. Check AWS SSO session

```bash
aws sts get-caller-identity
```

If it returns an error, tell the team member to run:
```bash
aws sso login
```
Do not proceed with AWS tasks until auth is confirmed.

### 4. Ask who is starting the session

If not already known, ask: **"Who is starting this session — Kiak, Sun, Pluck, or Jop?"**

Then look up their current tasks in the CLAUDE.md phase tracker and surface:
- Their ✅ Done phases (context only)
- Their ⬜ Next / unblocked phase (what to work on today)
- Any ⬜ Blocked phases and what they're waiting on

### 5. Check RDS if relevant

RDS is needed by: **Kiak** (loading data) and **Sun** (spot-checking source_listings).

If the team member is Kiak or Sun, check RDS status:
```bash
aws rds describe-db-instances \
  --db-instance-identifier airbnb-source-db \
  --region ap-southeast-1 \
  --query "DBInstances[0].DBInstanceStatus" \
  --output text
```

If `stopped`, remind them to start it before connecting:
```bash
aws rds start-db-instance --db-instance-identifier airbnb-source-db --region ap-southeast-1
```

If their IP has changed since last session, they'll also need a new SG rule for port 5432 — offer to add it.

### 6. Confirm ready

Summarise in 3–5 bullet points:
- Who is in the session
- Git state (clean / uncommitted changes)
- AWS auth status
- RDS status (if relevant)
- Their next unblocked task

---

## Quick Role Reference

| Person | Next unblocked task | Needs RDS? |
|--------|--------------------|----|
| Kiak | Glue Python Shell job + Scheduler (Automation 1%) | Yes |
| Sun | Star schema DDL → Glue Job 1 (Raw → Cleaned) | For spot-checks |
| Pluck | S3 lake zones + Glue Crawlers on raw | No |
| Jop | Waiting on Phase 8 (Cleaned Parquet) | No |

> Full phase details and handoff context are in `CLAUDE.md` and `handoff.md`.
