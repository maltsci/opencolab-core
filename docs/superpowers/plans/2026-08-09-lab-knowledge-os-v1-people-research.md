# Lab Knowledge OS v1 — Phase 2: People and Research

**Goal:** Make the Phase 0 knowledge entities usable through controlled laboratory pages, beginning with the formal Research directory requested during Resources acceptance.

**Entry evidence:** Resources now links to the stable `ResearchDirection` API and the development database has applied the Lab Knowledge OS foundation migration.

## Durable decisions

- `/research` is the user-facing directory route; `/research/:directionId` is the stable detail route.
- `ResearchDirection` remains the sole formal long-term topic entity. `ResearchObject` stays process-oriented and will be linked through the approved suggestion path rather than merged into this UI.
- Everyone can browse active directions. Admin/PI can create, archive, and merge; a scoped Direction Steward can update allowed descriptive fields through the existing API.
- Direction details must distinguish no maintained content from permission-limited content and point the user to the relevant next action.

## Slice 1 — Research directory and lifecycle

**User stories:** 15, 16, 17, 24, 25.

Deliver the formal Research directory with search, active/archived state handling, accessible direction details, and Admin/PI creation. The page reuses the existing lifecycle API and cannot let a normal member create or alter formal directions.

**Acceptance criteria:**

- [ ] Every laboratory member can browse/search active directions and open their background, scope, owner, and freshness information.
- [ ] Admin/PI sees a create action; normal members do not.
- [ ] Empty state explains that no formal directions exist yet and directs eligible users to create one.
- [ ] Frontend uses localized en-US/zh-CN copy and passes production build.

## Slice 2 — Direction links and governed content

**User stories:** 18–23, 26–30.

Add related-direction context, resource links, learning-entry ordering, and the ResearchObject suggestion entry while preserving source permissions and explicit relationship reasons.

**Acceptance criteria:**

- [ ] Detail pages can show related directions and resources without exposing protected content.
- [ ] Maintainers can add/remove allowed relationships with an auditable reason.
- [ ] Missing, permission-limited, and awaiting-confirmation sections have distinct helpful states.

## Slice 3 — People directory and profile foundation

**User stories:** 1–14.

Add the People directory and initial profile details: verified organization information, current directions, contact topics, and the selected resource responsibilities supplied by existing governance data.

**Acceptance criteria:**

- [ ] Members can find colleagues by name, group, role, and confirmed direction.
- [ ] Profile pages explain empty and permission-limited activity states correctly.
- [ ] Self-edit and scoped governance actions enforce existing role boundaries.

## Slice 4 — Profile/direction projections

**User stories:** 4–8, 19, 23, 59, 65–67.

Deliver the minimal activity projection and maintenance states required for current/history views, freshness review, opt-out, and steward queues.

**Acceptance criteria:**

- [ ] Activity is traceable, permission-filtered, and independently refreshable.
- [ ] Historical relationships preserve source and time range.
- [ ] Stale or incomplete records provide an appropriate maintenance next step.
