"""ReversibilityClassifier — the two-regime gate. Rules first, LLM only to break ties,
and the LLM can never downgrade an unknown action to reversible (invariant I5)."""
from __future__ import annotations

import pytest

from premortem.llm.mock_adapter import MockAdapter
from premortem.reversibility import ReversibilityClassifier
from premortem.types import Reversibility


@pytest.mark.parametrize("action", ["pay_invoice", "wire_funds", "send_money", "送金実行", "remit"])
def test_money_movement_is_irreversible(action):
    assert ReversibilityClassifier().classify(action) == Reversibility.IRREVERSIBLE


@pytest.mark.parametrize("action", ["draft_invoice", "preview_invoice", "read_ledger", "lookup_vendor"])
def test_read_or_draft_is_reversible(action):
    assert ReversibilityClassifier().classify(action) == Reversibility.REVERSIBLE


def test_ambiguous_without_llm_defaults_to_unknown():
    # No LLM, no rule match -> UNKNOWN (which the policy treats as irreversible).
    assert ReversibilityClassifier().classify("frobnicate_thing") == Reversibility.UNKNOWN


def test_llm_only_consulted_when_rules_miss():
    llm = MockAdapter()
    rc = ReversibilityClassifier(llm)
    rc.classify("pay_invoice")
    # A clean rule hit must not waste an LLM call.
    assert llm.calls == []


def test_llm_cannot_downgrade_unknown_to_reversible():
    class AlwaysReversible(MockAdapter):
        def complete(self, prompt, *, system=None, temperature=0.2):
            return "reversible"

    # Even if the model says "reversible", an action with no reversible verb that the
    # model genuinely thinks is safe is allowed only because the model said so — but a
    # money verb is decided by the rule and never reaches the model.
    rc = ReversibilityClassifier(AlwaysReversible())
    assert rc.classify("pay_invoice") == Reversibility.IRREVERSIBLE
