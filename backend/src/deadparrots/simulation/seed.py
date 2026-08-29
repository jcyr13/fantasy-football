from __future__ import annotations

import hashlib

# The head-to-head simulation is seeded, and the spec fixes *where* the seed
# comes from: the weekly snapshot ID (spec user story 64, issue #10 acceptance
# criterion 2). Deriving it here — once, deterministically — means every
# consumer of a snapshot reproduces its win-probability numbers exactly across
# page reloads and re-runs.


def seed_from_snapshot_id(snapshot_id: str | int) -> int:
    """Derive the simulation's RNG seed from a weekly snapshot ID.

    Uses BLAKE2b rather than the built-in :func:`hash` (which is salted
    per-process) so the mapping is stable across processes, machines, and Python
    versions. The result is a 64-bit non-negative int, which ``random.Random``
    and every factor stream in :mod:`deadparrots.simulation.montecarlo` accept
    directly.
    """
    token = str(snapshot_id).encode("utf-8")
    digest = hashlib.blake2b(token, digest_size=8).digest()
    return int.from_bytes(digest, "big")
