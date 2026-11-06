# Architecture principles

Generic rules for code in this repo, distilled from code reviews. They apply to every
language here (Python, TypeScript, Kotlin, JS). `CLAUDE.md` holds the repo-specific
conventions (comments, quoting, scope of changes); this file is about structure.

Each rule names the mistake it prevents. Reviews cite rules by number.

## Modules and boundaries

1. **Pure core, thin shell.** Parsing, state machines, classification, formatting and
   policy live in plain modules with no I/O and no framework imports. Sockets, files,
   HTTP, timers and framework hooks (Flask routes, extension lifecycle, ViewModels) sit
   in a thin layer that calls the core. *Prevents:* logic that can only be tested by
   running the whole program.
2. **Entry points only wire.** A main/index/route file subscribes to events, builds
   objects and forwards calls. File reads, argument parsing, data mapping and text
   formatting each go to a named module. *Prevents:* the entry file becoming the place
   every new feature lands.
3. **Dependencies point one way:** wiring → domain/state → protocol → transport/storage.
   Lower layers never import upper ones; only the transport module imports the network
   library. *Prevents:* cycles and framework types leaking into logic.
4. **Small units.** New files stay under ~200–300 lines, functions under ~50 lines,
   nesting at most 3 levels. Test files too; shared test helpers (fake clocks, fake
   servers) get their own files. Over the limit needs a stated reason. *Prevents:* files
   nobody can hold in their head.
5. **One responsibility per module, stated in one sentence.** If adding the next planned
   feature would push a module past its sentence (e.g. a connection manager starting to
   hold an event queue), the seam is designed now and the new part gets its own module.

## Ownership

6. **One owner per contract.** Wire paths, field names, error codes, schemas and status
   classifications are defined in exactly one module. Other code imports them; docs point
   to them. *Prevents:* two copies that drift (it happened: the plan's field list and the
   code disagreed within one issue).
7. **One owner per rule.** A behaviour rule ("disabled by config", "unknown session →
   re-register") is decided in one place; other places ask that owner instead of
   re-checking the inputs.
8. **Types are defined once and derived.** Use `Pick`/`Omit`/aliases, or a shared
   named type, instead of restating a shape or a function signature in a second file.
9. **Every resource has an owner.** Each timer, socket, stream or thread belongs to one
   object that starts it, retries it and closes it, with idempotent `start()`/`stop()`.
   No timer handle that nobody can cancel; no context object captured as a hidden
   long-lived channel.
10. **Reusable policies are modules.** Backoff, retry, rate limiting and similar
    policies are small pure modules used by every caller, not inlined into the first
    state machine that needed them.
11. **Configuration has one definition.** One module resolves each setting with a
    documented precedence (env > file > default), and the same names are used on both
    sides of a boundary.

## Testability

12. **Inject time and I/O.** Clocks, timers and request functions are passed in, so
    state machines run under fake time in unit tests. Real implementations are the
    default.
13. **Classify, then branch.** Turn raw responses into a small enum with a pure function
    (`classifyResponse(status, body) → ok | unknown_session | rejected | …`); state
    machines switch on the enum and never compare literals from the wire.
14. **Executable contracts.** A contract between two components (especially across
    languages) has golden fixtures — ordered request/response cases in JSON — that both
    sides' test suites run. The prose spec references the fixtures as its executable form.

## Protocols

15. **Specify enough to implement without reading the other side's code:** a field
    table per message (name, type, nullable, units), status codes with bodies, the order
    of validation checks, unknown paths, and timeouts.
16. **Additive by default.** Every message carries a version; receivers ignore unknown
    fields; a version bump ships on both sides together.
17. **Identity and liveness are explicit.** Define the key of every tracked entity (e.g.
    session + process instance), what a second registration under the same key does, and
    how long silence means "gone".
18. **No tracking markers in user content.** Identify messages by ids and metadata kept
    alongside them, never by text injected into what a model or user will read.

## Design docs and spikes

19. **One place per fact in a design doc.** Behaviour is described in one section and
    contracts in another; other sections point instead of copying field lists.
20. **Decisions in the plan, evidence beside it.** Measurements, logs and citations go
    in a separate evidence file linked from each decision, so the plan stays readable.
21. **Spikes are throwaway.** A spike's code is not reworked to production standard;
    its review records which pieces may seed production code and which lessons go into
    the design doc. Production code starts fresh from those lessons.
