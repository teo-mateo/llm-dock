"""Persistence policy seam for the chat runtime (Phase 8 of #58).

The runtime (ChatRunner) drives the model/tool stream and publishes events; how
— or whether — a turn is durably stored is delegated to a PersistencePolicy.
This is the architectural hook Ghost Chat (#57) needs: the same model/tool
stream can run DB-backed or fully ephemeral by swapping the policy, with no
change to the runtime or the SSE-encoding layer.

Two policies ship here:

  - DbPersistencePolicy wraps a ChatDB and reproduces the previous inline
    behavior exactly (claim → complete/fail/cancel against chat_runs, message +
    artifacts written atomically).
  - NullPersistencePolicy performs no durable writes. It keeps the transcript in
    memory so a multi-turn ephemeral session stays coherent, and returns
    synthetic run/message objects whose shape matches the DB path so the
    runtime's control flow is identical either way.

The policy intentionally covers only the per-turn runtime writes. Run-manager
orchestration (recovery, the cancel registry, list/active lookups) stays on the
DB directly — those are durable-coordination concerns, not part of running a
single stream, and an ephemeral mode wires up its own (or no) manager.
"""
from .models import ChatRun, Message
from .runs import ChatRunStatus


class PersistencePolicy:
    """Interface the runtime uses to read prior turns and record this one.

    Implementations must be safe to call from the runner's worker thread.
    """

    def load_messages(self, conv):
        """Return the ordered message history used to build the prompt."""
        raise NotImplementedError

    def claim_running(self, run_id):
        """Transition the run to RUNNING and return it (with a `.status`), or
        return a non-running run / None to signal the claim was lost (e.g. the
        run was cancelled before the worker picked it up)."""
        raise NotImplementedError

    def complete(self, run_id, assistant_msg, artifacts):
        """Persist the assistant message + artifacts and mark the run completed,
        atomically. Return the saved message (with `.id` and `.seq`), or None if
        the run was already terminal (cancelled mid-stream)."""
        raise NotImplementedError

    def fail(self, run_id, error, partial_msg=None):
        """Mark the run failed with the given error text.

        If partial_msg is given, persist it as an error message with the
        accumulated content/reasoning before the failure.
        """
        raise NotImplementedError

    def cancel(self, run_id):
        """Mark the run cancelled (idempotent)."""
        raise NotImplementedError


class DbPersistencePolicy(PersistencePolicy):
    """The durable policy: every operation goes to ChatDB exactly as the runtime
    did inline before this seam existed."""

    def __init__(self, db):
        self.db = db

    def load_messages(self, conv):
        return self.db.get_messages(conv.id)

    def claim_running(self, run_id):
        return self.db.update_chat_run_status(
            run_id, ChatRunStatus.RUNNING, active_step="generating")

    def complete(self, run_id, assistant_msg, artifacts):
        return self.db.complete_run_with_message(run_id, assistant_msg, artifacts)

    def fail(self, run_id, error, partial_msg=None):
        if partial_msg is not None:
            self.db.fail_chat_run_with_message(run_id, error, partial_msg)
        else:
            self.db.fail_chat_run(run_id, error)

    def cancel(self, run_id):
        self.db.cancel_chat_run(run_id)


class NullPersistencePolicy(PersistencePolicy):
    """The ephemeral policy: no durable writes (Ghost Chat, #57).

    Holds the transcript in memory so prompts build correctly across turns and a
    completed assistant turn is visible to the next one. Lifecycle transitions
    are no-ops that return synthetic objects shaped like the DB path's, so the
    runtime takes the same branches.
    """

    def __init__(self, messages=None):
        # The in-memory transcript. Seed it with the prior turns (including the
        # current user message) the way the DB path would have persisted them.
        self.messages = list(messages) if messages else []

    def load_messages(self, conv):
        return self.messages

    def claim_running(self, run_id):
        # No row to transition; synthesize a RUNNING run so the runner proceeds.
        return ChatRun(id=run_id, conversation_id="", status=ChatRunStatus.RUNNING)

    def complete(self, run_id, assistant_msg, artifacts):
        # Assign a seq from the in-memory transcript (the DB path assigns it
        # inside the atomic write) and append so the next turn sees this reply.
        assistant_msg.seq = (self.messages[-1].seq + 1) if self.messages else 1
        self.messages.append(assistant_msg)
        return assistant_msg

    def fail(self, run_id, error, partial_msg=None):
        pass

    def cancel(self, run_id):
        pass
