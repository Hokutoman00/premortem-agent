"""FailureMemory — append-only learning store (invariant I4). Seeds future pre-mortems by
exact fingerprint OR vendor prefix, so a fraud against a vendor at one amount still seeds a
different-amount payment to the same vendor."""
from __future__ import annotations

from premortem.memory.failure_memory import FailureMemory
from premortem.types import FailureOutcome


def _outcome(fp="V-1007:pay_invoice:5000", mode="goods_not_received", label="human_override"):
    return FailureOutcome(action_fp=fp, failure_mode=mode, evidence="納品実績なし",
                          label=label, source="human_override")


def test_append_increments_count():
    m = FailureMemory(":memory:")
    assert m.count() == 0
    m.append(_outcome())
    assert m.count() == 1


def test_seed_matches_exact_fingerprint():
    m = FailureMemory(":memory:")
    m.append(_outcome(fp="V-1007:pay_invoice:5000"))
    seeds = m.seed_modes_for("V-1007:pay_invoice:5000", "V-1007")
    assert [s.id for s in seeds] == ["goods_not_received"]
    assert seeds[0].seed_source == "memory"


def test_seed_matches_vendor_prefix_across_amounts():
    m = FailureMemory(":memory:")
    # Fraud recorded at $48,000; a later $5,000 payment to the same vendor must still seed.
    m.append(_outcome(fp="V-1007:pay_invoice:48000", mode="bank_changed"))
    seeds = m.seed_modes_for("V-1007:pay_invoice:5000", "V-1007")
    assert "bank_changed" in [s.id for s in seeds]


def test_seed_isolated_by_vendor():
    m = FailureMemory(":memory:")
    m.append(_outcome(fp="V-1007:pay_invoice:5000"))
    assert m.seed_modes_for("V-2210:pay_invoice:5000", "V-2210") == []


def test_seed_dedups_repeated_mode():
    m = FailureMemory(":memory:")
    m.append(_outcome())
    m.append(_outcome())  # same mode appended twice
    seeds = m.seed_modes_for("V-1007:pay_invoice:5000", "V-1007")
    assert len(seeds) == 1  # DISTINCT failure_mode


def test_all_returns_every_row_in_order():
    m = FailureMemory(":memory:")
    m.append(_outcome(mode="a"))
    m.append(_outcome(mode="b"))
    rows = list(m.all())
    assert [r["failure_mode"] for r in rows] == ["a", "b"]
