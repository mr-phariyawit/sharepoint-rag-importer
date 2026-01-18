# 🙋 Batched Questions for Human Review

## Metadata
**Project:** [PROJECT_NAME]
**Feature:** [FEATURE_NAME]
**Batch ID:** BQ-[TIMESTAMP]
**Date:** [YYYY-MM-DD HH:MM]
**Questions Count:** [N]
**Status:** Pending | Answered | Partially Answered

---

## Context Summary

[Brief 2-3 sentence summary of what the team is working on]

[Why these questions arose - what decision points were reached]

[What the team will do after receiving answers]

---

## Questions

### Q1: [CATEGORY] 
**Priority:** 🔴 High | 🟡 Medium | 🟢 Low
**Blocking:** Yes | No
**Asked by:** [ROLE]

**Question:**
> [Clear, specific question in one sentence]

**Context:**
[2-3 sentences explaining why this matters and what depends on it]

**Options (if applicable):**
| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A | [Description] | [Pros] | [Cons] |
| B | [Description] | [Pros] | [Cons] |
| C | [Description] | [Pros] | [Cons] |

**Team's Leaning:** 
> [If team has a preference: "Team leans toward Option B because..." OR "No strong preference"]

---

### Q2: [CATEGORY]
**Priority:** 🔴 High | 🟡 Medium | 🟢 Low
**Blocking:** Yes | No
**Asked by:** [ROLE]

**Question:**
> [Clear, specific question]

**Context:**
[Why this matters]

**Options (if applicable):**
- **A:** [Option description]
- **B:** [Option description]

**Team's Leaning:** 
> [Team's preference if any]

---

### Q3: [CATEGORY]
**Priority:** 🔴 High | 🟡 Medium | 🟢 Low
**Blocking:** Yes | No
**Asked by:** [ROLE]

**Question:**
> [Clear, specific question]

**Context:**
[Why this matters]

**Team's Leaning:** 
> [Team's preference if any]

---

## Response Format Requested

Please respond in this format for easy parsing:

```
Q1: [Your answer - option letter or free text]
Q2: [Your answer]
Q3: [Your answer]
```

**Optional:** Add any additional context or constraints we should know.

---

## What Happens Next

After receiving your answers:

1. ✅ Answers will be recorded in `team-history.md`
2. ✅ Relevant specs/plans will be updated
3. ✅ Team proceeds autonomously with implementation
4. ✅ Next batch (if any) at: [NEXT_CHECKPOINT]

**Estimated next interaction:** [After Phase X / After Feature Y / If blocking issues arise]

---

## Internal Tracking (Team Use Only)

### Question Queue Build-up

| Timestamp | Role | Question Added | Category |
|-----------|------|----------------|----------|
| [TIME] | [ROLE] | Q1 | [CAT] |
| [TIME] | [ROLE] | Q2 | [CAT] |
| [TIME] | [ROLE] | Q3 | [CAT] |

### Batch Trigger
- [ ] Reached minimum batch size (3)
- [ ] End of phase reached
- [ ] Blocking question encountered

---

## Human Response Record

**Answered on:** [YYYY-MM-DD HH:MM]

| Q# | Human Answer | Confidence | Notes |
|----|--------------|------------|-------|
| Q1 | | | |
| Q2 | | | |
| Q3 | | | |

**Additional Context from Human:**
> [Any extra info provided]

**Recorded by:** [ROLE]
**Applied to:** [List of affected documents/code]
