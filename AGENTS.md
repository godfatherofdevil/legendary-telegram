# AGENTS.md

## 1. Purpose

This file defines mandatory agent instructions for implementing the Online Chat Server project.

It is authoritative for all coding agents, planning agents, review agents, and refactoring agents working in this repository.

All agents MUST follow this file exactly.

If any instruction in this file conflicts with ad hoc agent behavior, this file takes precedence.

If any instruction in this file conflicts with another repository document, agents MUST follow the order of precedence defined in this file.

---

## 2. Document Precedence

Agents MUST use the following precedence order, highest first:

1. `AGENTS.md`
2. `API_CONTRACT.md`
3. `SCHEMA.md`
4. `ARCHITECTURE.md`
5. `DEPLOYEMENT.md`
6. `TASKS.md`
7. `DJANGO_MODELS_MAPPING.md`
7. source code and tests
8. any generated notes or temporary plans

Rules:

- Agents MUST NOT ignore a higher-precedence document in favor of a lower-precedence document.
- If two documents conflict, the higher-precedence document MUST win.
- If a conflict is detected, the agent MUST align implementation to the higher-precedence document.
- If a lower-precedence document appears outdated, agents MUST update or flag it as part of their work when relevant.

---

## 3. General Operating Rules

- Agents MUST behave deterministically and conservatively.
- Agents MUST prefer correctness over speed.
- Agents MUST prefer explicitness over cleverness.
- Agents MUST prefer small verifiable changes over large speculative rewrites.
- Agents MUST NOT invent product requirements.
- Agents MUST NOT silently change externally visible behavior unless required by a controlling spec.
- Agents MUST work within a venv when running or validating backend locally, use `source .venv/bin/activate` to activate the virtual environment
- 
- Agents MUST keep the codebase buildable.
- Agents MUST keep the codebase runnable by `docker compose up` from repository root.
- Agents MUST produce code that is understandable by a human maintainer.
- Agents MUST NOT leave partially implemented flows hidden behind dead code unless explicitly marked and tracked.
- Agents MUST NOT commit placeholder logic presented as complete.
- Agents MUST NOT claim a feature is complete if any required happy path, failure path, or authorization rule is missing.

---

## 4. Required Repository Inputs

Agents MUST treat the following repository files as required sources of truth:

- `API_CONTRACT.md`
- `SCHEMA.md`
- `ARCHITECTURE.md`
- `DEPLOYEMENT.md`

### 4.1 SCHEMA Rules

- Agents MUST use `SCHEMA.md` as the database source of truth.
- Agents MUST NOT invent database schema independently when `SCHEMA.md` defines it.
- Agents MUST generate database migrations from `SCHEMA.md` requirements via Django migrations
- Agents MUST NOT introduce schema objects that contradict `SCHEMA.md`.
- If `SCHEMA.md` is incomplete, agents MAY add only the minimum schema needed to satisfy the existing contract, and MUST document that addition clearly.

### 4.2 ARCHITECTURE Rules

- Agents MUST follow `ARCHITECTURE.md` for system boundaries and component responsibilities.
- Agents MUST NOT collapse architecture layers unless explicitly allowed there.
- Agents MUST align real-time, REST, database, and storage flows with the defined architecture.

### 4.3 DEPLOYMENT Rules

- Agents MUST ensure the project runs according to `DEPLOYEMENT.md`.
- Agents MUST keep the deployment path compatible with Docker Compose.
- Agents MUST update deployment instructions when implementation changes deployment requirements.

---

## 5. Required Technology Stack

Agents MUST implement the project using the following required technologies unless a higher-precedence document explicitly overrides them:

- Python 3.12 or higher
- PostgreSQL
- Django
- Django REST Framework
- Django Channels
- Redis
- Django migrations for schema migration generation where the repository requires it
- React with Typescript for UI tasks
- Docker Compose for local orchestration

Rules:

- Agents MUST NOT substitute another primary backend language.
- Agents MUST NOT substitute another relational database.
- Agents MUST NOT replace Channels + Redis with another websocket stack.
- Agents MUST NOT introduce infrastructure that makes local `docker compose up` non-functional.
- Agents MAY add compatible libraries only when they reduce implementation risk or complexity.

---

## 6. System Scope

Agents MUST implement a classic web-based online chat application with:

- registration and authentication
- public and private rooms
- one-to-one dialogs
- contacts/friends
- attachments
- moderation
- message history
- presence
- session management

Agents MUST treat the system as a classic chat application, not a social network, project management tool, or collaboration suite.

Agents MUST NOT add unrelated product concepts such as:

- feeds
- reactions unless explicitly required elsewhere
- threaded forums
- story-like content
- algorithmic recommendation systems
- follower/subscriber systems in place of friendship

---

## 7. Work Sequencing Rules

Agents MUST implement in this order unless blocked by repository state:

1. project scaffolding and local execution
2. data model and migrations
3. authentication and session handling
4. room and dialog domain models
5. REST API contract compliance
6. websocket protocol compliance
7. presence and unread state
8. attachments and file access control
9. moderation and bans
10. UI integration
11. deployment hardening
12. optional advanced features

Rules:

- Agents MUST complete foundational layers before advanced ones.
- Agents MUST NOT start federation or Jabber support before core chat functionality is operational.
- Agents MUST NOT optimize prematurely before contract coverage exists.

---

## 8. Implementation Discipline

### 8.1 Before Coding

Agents MUST:

- read `AGENTS.md`
- read `API_CONTRACT.md`
- read relevant sections of `SCHEMA.md`
- read relevant sections of `ARCHITECTURE.md`
- identify affected modules before editing
- verify whether an existing abstraction already supports the needed change

### 8.2 During Coding

Agents MUST:

- make the minimum correct change
- preserve backward compatibility within the same version
- keep interfaces explicit
- keep authorization checks close to business actions
- keep validation explicit and testable
- keep websocket and REST behavior aligned where contract requires parity

Agents MUST NOT:

- duplicate business logic across endpoints and consumers when shared services are appropriate
- bury authorization logic in templates or client-only checks
- implement core rules only in frontend code
- bypass service-layer validation for convenience
- hardcode environment-specific secrets or addresses

### 8.3 After Coding

Agents MUST:

- run relevant tests
- add or update tests for changed behavior
- verify linters or static checks where configured
- verify migrations are coherent
- verify new endpoints match `API_CONTRACT.md`
- verify permission and access-control rules
- verify imports and module boundaries remain clean

---

## 9. API Compliance Rules

- Agents MUST implement the REST and WebSocket interfaces exactly as defined in `API_CONTRACT.md`.
- Agents MUST NOT rename endpoints without updating the contract.
- Agents MUST NOT rename payload fields without updating the contract.
- Agents MUST NOT change enum values without updating the contract.
- Agents MUST preserve the documented error model.
- Agents MUST ensure WebSocket events reflect persisted state.
- Agents MUST ensure authorization behavior matches the documented matrix.

If implementation reveals that the contract is impossible or contradictory:

- agents MUST NOT silently diverge
- agents MUST minimally reconcile code and contract
- agents MUST document the change in the repository update

---

## 10. Data and Migration Rules

- Database changes MUST be represented through migrations.
- Agents MUST keep migrations reproducible and ordered.
- Agents MUST generate migrations from the schema requirements, not by ad hoc drift.
- Agents MUST NOT mutate applied migrations retroactively unless repository policy explicitly allows it.
- Agents MUST preserve data integrity constraints.
- Agents MUST enforce uniqueness requirements for:
  - email
  - username
  - room name

Agents MUST explicitly model and enforce:

- room ownership
- room admin membership
- room bans
- friendship state
- peer bans
- dialog participant constraints
- attachment ownership and binding
- session records if session listing/revocation depends on them

---

## 11. Authorization Rules

Agents MUST treat authorization as a first-class concern.

The implementation MUST enforce all of the following server-side:

- only authenticated users may access authenticated APIs
- only room members may read room messages
- only authorized dialog participants may read dialog messages
- only room owner/admin may perform room moderation actions permitted by contract
- only message author may edit own messages
- only message author or room moderator may delete room messages
- only dialog message author may delete own dialog messages
- only room owner may delete a room
- only room owner may perform owner-only role changes unless the contract explicitly permits admin action
- removed or banned users MUST lose room access immediately
- peer-banned users MUST be unable to contact the banning user in any way supported by the product

Agents MUST NOT rely on hidden UI controls as authorization.

---

## 12. Presence Rules

Agents MUST implement presence exactly as defined by contract:

- online if active in at least one open tab
- AFK if all open tabs are inactive for more than one minute
- offline if all application tabs are closed/offloaded

Rules:

- presence MUST be computed at user level across tabs/sessions
- presence updates SHOULD propagate quickly
- presence state MUST NOT be guessed solely by last login time
- websocket presence flow MUST be robust to multi-tab behavior

---

## 13. Messaging Rules

Agents MUST preserve message invariants:

- messages are persisted before broadcast
- message ordering is chronological
- infinite scroll must be supportable
- offline delivery relies on persistent storage
- message text must support UTF-8
- message text must not exceed 3 KB
- replies must reference valid messages within the same chat context unless explicitly documented otherwise
- edited messages must expose edited state
- deleted messages are not required to be recoverable

Agents MUST ensure room and dialog messaging feature parity where required.

---

## 14. Attachment Rules

Agents MUST implement attachments with strict access control.

Rules:

- only authorized users may download attachments
- original filename MUST be preserved
- image size limit MUST be enforced
- file size limit MUST be enforced
- attachment access MUST be revoked immediately when room access is lost
- files MAY remain stored after uploader loses access, as long as room still exists
- deleting a room MUST delete room attachments permanently

Agents MUST NOT expose direct unguarded filesystem paths.

---

## 15. Session Rules

Agents MUST support:

- persistent login
- current-session logout
- active session listing
- targeted session revocation

Rules:

- logout of current browser MUST invalidate only current session
- revoking another session MUST not revoke current one unless explicitly requested
- session handling MUST be secure and server-controlled
- session data shown to users MUST be safe and useful, such as browser and IP metadata where available

---

## 16. Performance and Scale Expectations

Agents MUST keep the documented target scale in mind:

- up to 300 simultaneous users
- rooms up to 1000 participants
- very large histories, including at least 10,000 messages per room

Rules:

- agents MUST avoid obviously unscalable polling designs where websocket/pubsub is expected
- agents MUST paginate list/history endpoints
- agents MUST avoid loading entire history into memory for standard reads
- agents SHOULD use indexed queries for common lookups
- agents SHOULD avoid N+1 query patterns in hot paths

Agents MUST NOT sacrifice correctness for speculative micro-optimizations.

---

## 17. Testing Rules

Agents MUST add or update tests for every meaningful behavior change.

At minimum, agents MUST cover:

- authentication happy paths and rejection paths
- room creation and uniqueness
- public/private room join rules
- friendship request/accept/reject flows
- peer ban behavior
- room ban behavior
- message send/edit/delete flows
- unread state clearing
- attachment access rules
- session listing and revocation
- websocket authorization and event broadcast behavior
- presence aggregation rules for multi-tab behavior where testable

Agents MUST prefer targeted automated tests over manual-only verification.

Agents MUST NOT mark work complete without testing the main contract path.

---

## 18. Review Rules

When reviewing code, agents MUST check:

- spec compliance
- authorization correctness
- migration safety
- API compatibility
- websocket consistency
- data deletion rules
- room access revocation behavior
- absence of duplicate business logic
- deployment impact
- test adequacy

Review agents MUST NOT approve code that:

- violates the API contract
- skips server-side authorization
- introduces schema drift against `SCHEMA.md`
- breaks `docker compose up`
- leaves required flows untested

---

## 19. Refactoring Rules

Agents MAY refactor when necessary, but MUST obey these constraints:

- behavior MUST remain unchanged unless spec requires change
- public contract MUST remain unchanged unless contract is intentionally updated
- tests MUST remain green
- migrations MUST remain coherent
- deployment instructions MUST remain valid

Agents MUST NOT perform broad stylistic rewrites unrelated to the task unless the repository explicitly requests them.

---

## 20. Documentation Rules

Agents MUST keep documentation aligned with implementation.

Agents MUST update relevant docs when changing:

- endpoints
- websocket events
- environment variables
- migration steps
- service dependencies
- local run instructions
- storage behavior
- permission behavior

Agents MUST NOT leave stale examples in authoritative docs.

If code and docs temporarily diverge during a task, the final state MUST be reconciled before considering the task complete.

---

## 21. Logging and Observability Rules

Agents SHOULD implement useful server-side logs for:

- authentication failures
- websocket connection lifecycle
- moderation actions
- session revocations
- critical delivery failures
- storage failures

Rules:

- logs MUST NOT expose plaintext passwords
- logs MUST NOT expose secret tokens
- logs SHOULD include identifiers useful for debugging
- logs SHOULD be structured where the project already uses structured logging

---

## 22. Security Rules

Agents MUST apply standard secure defaults.

Required rules:

- passwords MUST be hashed securely
- authenticated cookies MUST be `HttpOnly`
- authenticated cookies MUST be `Secure` in production
- CSRF protections MUST be respected for cookie-authenticated unsafe HTTP methods where applicable
- uploads MUST be validated for size and type handling
- authorization MUST be checked on every protected resource access
- private room visibility MUST be protected
- removed users MUST lose room file/message access immediately

Agents MUST NOT:

- store plaintext passwords
- expose raw internal storage paths
- trust client-supplied role claims
- use client-only enforcement for bans or access control

---

## 23. UI Rules

If the repository contains UI implementation, agents MUST preserve the classic web chat interaction model.

The UI MUST support:

- sign in / registration
- room navigation
- contacts list
- chat history
- multiline input
- attachments
- reply flow
- unread indicators
- room member list with statuses
- admin/moderation dialogs
- session management screens

Agents MUST keep behavior consistent with backend rules.

Agents MUST NOT implement UI-only shortcuts that violate server behavior.

---

## 24. Optional Advanced Features

Jabber/XMPP and federation are optional advanced scope unless promoted by a higher-precedence task.

Rules:

- agents MUST NOT start optional advanced scope before core features are stable
- agents MUST isolate optional advanced functionality from core chat correctness
- agents SHOULD treat federation support as integration-heavy and deployment-sensitive
- agents MUST add explicit docker-compose support if federation is implemented
- agents MUST add dedicated admin UI surfaces for Jabber/federation only if that feature is actually implemented

---

## 25. Definition of Done

A task is complete only if all of the following are true:

- implementation matches the applicable spec
- code is buildable
- code is runnable through repository-local workflow
- tests covering changed behavior pass
- migrations are present and coherent if schema changed
- docs are updated if contract or behavior changed
- authorization and access control rules are enforced
- no known critical placeholder logic remains in the affected path

Agents MUST NOT mark a task complete if any required item above is missing.

---

## 26. Forbidden Shortcuts

Agents MUST NOT:

- skip migrations for schema changes
- hardcode fake data as production behavior
- bypass permissions to make tests pass
- silence failing tests instead of fixing root causes
- implement API fields differently from contract names
- broadcast websocket events before persistence
- expose private room existence to unauthorized users unless contract allows it
- keep room access after ban/removal
- allow peer-banned users to continue sending DMs
- replace required technology choices with alternatives without explicit approval in repository docs

---

## 27. Preferred Change Pattern

Agents SHOULD follow this sequence for non-trivial work:

1. read relevant spec/docs
2. identify impacted modules
3. update schema/migrations if needed
4. implement domain/service logic
5. implement API layer
6. implement websocket flow if applicable
7. add/update tests
8. verify local run path
9. update docs

This is the default execution pattern unless the task is purely documentation.

---

## 28. Agent Output Expectations

When an agent completes work, its summary MUST be concrete.

It MUST include:

- what changed
- which contract areas were implemented or affected
- whether migrations were added
- what tests were added or updated
- any remaining explicit gaps

It MUST NOT include vague claims such as:

- "done"
- "implemented everything"
- "should work"

without concrete supporting detail.

---

## 29. Ambiguity Handling

If repository instructions are ambiguous, agents MUST:

- prefer the strictest interpretation consistent with existing docs
- prefer preserving security and access control
- prefer preserving API stability
- avoid speculative feature expansion

If an ambiguity materially affects implementation, agents SHOULD resolve it in the smallest spec-consistent way and document that resolution.

Agents MUST NOT invent broad new behavior to fill small gaps.

---

## 30. Final Rule

When in doubt, agents MUST implement the smallest secure, testable, spec-compliant solution that preserves:

- contract fidelity
- data integrity
- authorization correctness
- deployability
- maintainability

No agent is permitted to trade away those properties for convenience.

---

