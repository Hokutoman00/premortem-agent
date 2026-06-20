"""Shared fixtures. Everything runs on the creds-free MockAdapter (PREMORTEM_LLM=mock),
so the whole suite is offline and deterministic.

We force an in-memory failure DB *before* any premortem import so importing the API does
not create a stray premortem_memory.sqlite3 on disk during collection."""
from __future__ import annotations

import os

os.environ.setdefault("PREMORTEM_LLM", "mock")
os.environ["PREMORTEM_MEMORY_DB"] = ":memory:"

import pytest

from premortem.agent import PreMortemAgent
from premortem.catastrophe_registry import CatastropheRegistry
from premortem.data.demo_data import default_store
from premortem.llm.mock_adapter import MockAdapter
from premortem.memory.failure_memory import FailureMemory
from premortem.premortem import PreMortemEngine
from premortem.probes.registry import default_registry
from premortem.types import PaymentPlan


@pytest.fixture
def store():
    return default_store()


@pytest.fixture
def memory():
    m = FailureMemory(":memory:")
    yield m
    m.close()


@pytest.fixture
def llm():
    return MockAdapter()


@pytest.fixture
def probes():
    return default_registry()


@pytest.fixture
def engine(llm, store, probes, memory):
    return PreMortemEngine(llm, store, probes, memory, CatastropheRegistry())


@pytest.fixture
def agent(memory):
    # Fresh agent per test: mock LLM, default demo ledger, in-memory failure store.
    return PreMortemAgent(memory=memory)


@pytest.fixture
def safe_plan():
    return PaymentPlan(
        invoice_id="INV-T-0001", vendor_name="Acme Supplies Ltd", vendor_id="V-1007",
        amount=4750.00, currency="USD",
        bank={"iban": "DE89370400440532013000", "name": "Acme Supplies Ltd"},
        action="pay_invoice",
        source_image_facts={"iban_on_doc": "DE89370400440532013000"},
    )
