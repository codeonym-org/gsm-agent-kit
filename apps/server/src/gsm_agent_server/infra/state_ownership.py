"""Local state ownership for cooperating server processes, not a device lease."""

import os
from collections.abc import Iterable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from filelock import FileLock, SoftFileLock, Timeout


class StateOwnershipError(RuntimeError):
    """The backend cannot establish exclusive ownership of its local state."""


class StateAlreadyOwnedError(StateOwnershipError):
    """A cooperating backend already owns one of the enabled state files."""


@contextmanager
def own_state(paths: Iterable[Path]) -> Iterator[None]:
    """Acquire native nonblocking locks; retain each lock until the context ends.

    Canonical paths handle relative paths and symbolic links. Hard links and
    independent volumes are outside this local, cooperative ownership boundary.
    Lock files intentionally remain in place: their existence is not ownership.
    """
    with ExitStack() as locks:
        try:
            canonical = sorted({os.path.normcase(str(path.resolve())) for path in paths})
            if canonical and FileLock is SoftFileLock:
                raise StateOwnershipError("Native filesystem locking is unavailable on this platform.")
            for value in canonical:
                database = Path(value)
                database.parent.mkdir(parents=True, exist_ok=True)
                lock = FileLock(
                    database.with_name(database.name + ".owner.lock"),
                    timeout=0,
                    blocking=False,
                    mode=0o600,
                    fallback_to_soft=False,
                    preserve_lock_file=True,
                )
                locks.enter_context(lock.acquire())
        except Timeout:
            raise StateAlreadyOwnedError(
                "Persistent state is already owned by another backend; stop it before starting this one."
            ) from None
        except OSError:
            raise StateOwnershipError(
                "Cannot lock persistent state; check directory permissions and native filesystem locking."
            ) from None
        yield
