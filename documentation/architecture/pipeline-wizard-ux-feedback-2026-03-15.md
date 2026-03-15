# Pipeline Wizard UX Feedback

Date: 2026-03-15

## Context

The current Pipeline Wizard is functionally capable, but the operator experience
still feels disjointed. The main issue is not missing backend capability. The
main issue is operator confidence and continuity while moving through the
workflow.

There are three linked problems:

- the wizard assumes too much pipeline knowledge
- the wizard makes it easy to lose context when leaving the flow
- the wizard makes it too easy to repeat a completed step by accident

## Core Usability Problem

The wizard is currently better at orchestrating pipeline actions than it is at
teaching, orienting, and protecting the operator.

This matters because the user may not already have a precise mental model for:

- what each step actually does
- why the steps are separated
- which steps mutate system state
- what should happen next after a step succeeds

## Theme 1: Step Understanding

### Item 1

- Problem: each pipeline step currently assumes prior knowledge of the media
  pipeline.
- Why it hurts usability: the operator can lose confidence and may not know why
  a step exists or whether it is safe to run.
- Desired behavior: every step should explain in plain English what it does, why
  it exists, what changes after success, and whether it is review-only,
  planning-only, or mutating.
- Priority: high

### Item 2

- Problem: the current flow does not help users reconcile the current wizard
  model with earlier workflows where ingest may not have been a visible phase.
- Why it hurts usability: users may question whether the new flow is correct or
  whether they are repeating work.
- Desired behavior: step copy should explicitly explain the purpose of ingest,
  plan, apply, canonical recompute, and tag enrichment in operator language.
- Priority: high

## Theme 2: Workflow Orientation

### Item 1

- Problem: the wizard does not create a strong “where am I in the process?”
  feeling.
- Why it hurts usability: even with a sidebar step list, the experience can feel
  segmented instead of continuous.
- Desired behavior: add stronger progress framing such as breadcrumb context or
  equivalent current/previous/next step orientation.
- Priority: high

### Item 2

- Problem: the relationship between completed, current, and upcoming steps is
  not prominent enough during execution and review.
- Why it hurts usability: operators can lose their place or feel unsure what the
  correct next action should be.
- Desired behavior: make progress state, current position, and next-step intent
  more explicit throughout the wizard.
- Priority: medium

## Theme 3: Context Switching

### Item 1

- Problem: checkpoint links to pages such as Gallery and Duplicates are useful,
  but leaving the wizard can break the user’s mental thread.
- Why it hurts usability: users may inspect related data and then feel unsure
  how to return to the workflow.
- Desired behavior: review whether linked pages should open in a new tab, in a
  contained preview surface, or with a very explicit return-to-wizard path.
- Priority: high

### Item 2

- Problem: the current design optimizes access to related views more than flow
  continuity.
- Why it hurts usability: the wizard can stop feeling like a guided process and
  start feeling like a collection of disconnected pages.
- Desired behavior: linked review affordances should support the workflow rather
  than compete with it.
- Priority: medium

## Theme 4: Action Safety

### Item 1

- Problem: after a step succeeds, the wizard still presents “run same step”
  prominently enough that the operator could repeat the step in error.
- Why it hurts usability: this increases the chance of accidental duplicate
  execution and weakens trust in the success state.
- Desired behavior: after success, `Continue` should become the primary action
  and casual rerun should be visually demoted or disabled.
- Priority: high

### Item 2

- Problem: rerunning a completed step does not currently feel protected enough.
- Why it hurts usability: operators can trigger repeat work without a strong
  moment of reconfirmation.
- Desired behavior: rerun should require an explicit confirmation modal once a
  step has already completed successfully.
- Priority: high

## Phase Order

### Phase 1: Comprehension

Focus only on instructional clarity:

- plain-English step purpose
- why the step exists
- what changes after success
- whether the step is mutating
- risk and outcome language

Do not mix this phase with navigation redesign.

### Phase 2: Orientation

Focus on workflow continuity:

- breadcrumb or equivalent progress framing
- stronger current/previous/next step cues
- clear return-to-wizard behavior after linked review actions

### Phase 3: Action Safety

Focus on reducing accidental repeat execution:

- make `Continue` primary after success
- demote or disable casual rerun
- require explicit reconfirmation for rerun

### Optional Later Phase

Run a polish and consistency pass once the first three phases are stable.

## Acceptance Signals

- Phase 1 success: a new operator can explain what each wizard step does without
  prior pipeline knowledge.
- Phase 2 success: a user can inspect related pages and confidently return to
  the wizard without losing their place.
- Phase 3 success: a user cannot easily rerun a completed step by accident.

## Working Assumptions

- The best way to avoid overwhelm is to treat this as iterative UX refinement,
  not a full redesign in one pass.
- Step Understanding is the first implementation phase because it improves the
  whole wizard before deeper navigation and action changes.
- This note should stay lightweight and decision-driving rather than expanding
  into a long product specification.
