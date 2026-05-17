"""Shared lock serializing every services.json read-modify-write + compose
rebuild, across *all* blueprints (services routes and benchmarking routes).

Flask's dev server runs threaded (``app.run`` defaults ``threaded=True``), so
handlers in different blueprints that each do
``load services.json -> mutate -> save -> rebuild_compose_file`` can interleave
and clobber each other (e.g. benchmark "apply" writing a stale full service
config back over a concurrent key rotation). The lock must live below every
blueprint so they all contend on the *same* object.

``RLock`` (not ``Lock``) so a handler that nests guarded helpers on the same
thread can't self-deadlock.
"""

import threading
from functools import wraps

SERVICES_DB_LOCK = threading.RLock()


def serialize_db(fn):
    """Run the wrapped Flask view under :data:`SERVICES_DB_LOCK`.

    Place it *below* ``@require_auth`` so unauthenticated requests are
    rejected without contending for the lock.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        with SERVICES_DB_LOCK:
            return fn(*args, **kwargs)

    return wrapper
