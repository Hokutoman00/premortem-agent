"""ProbeRegistry — the set of read-only probes, keyed by name.

Probe names match the `probe` field in the catastrophe registry and remembered modes,
so enumerate -> falsify wiring is just a dict lookup. Each probe answers ONE question
about the world; the anchor of the final verdict is these non-LLM checks (invariant I6).

A probe returns confirmed=True when the danger is real. When a probe lacks the data to
judge, it returns probe_ran=False so the engine escalates rather than guessing.
"""
from __future__ import annotations

from ..data.demo_data import DemoDataStore
from ..types import PaymentPlan, ProbeResult
from .base import ProbeFn


def _norm_iban(iban: str | None) -> str:
    return (iban or "").replace(" ", "").upper()


# --- individual probes --------------------------------------------------
def bank_detail_diff(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    last = _norm_iban(store.last_iban(plan.vendor_id))
    now = _norm_iban(plan.bank.get("iban"))
    if not last:
        return ProbeResult("bank_changed", False,
                           "ベンダーに過去支払なし（口座差分は判定不能→他probe/escalateへ）",
                           probe_ran=False)
    if last != now:
        return ProbeResult("bank_changed", True,
                           f"last_paid_iban={last} != plan_iban={now}（口座が変更されている）")
    return ProbeResult("bank_changed", False, f"口座一致 {now}")


def vendor_age(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    v = store.vendor(plan.vendor_id)
    if v is None:
        return ProbeResult("new_payee_first_payment", True,
                           f"vendor {plan.vendor_id} がレジストリに存在しない")
    has_history = bool(store.payments_for(plan.vendor_id))
    if not has_history:
        return ProbeResult("new_payee_first_payment", True,
                           f"vendor {plan.vendor_id} は初回支払（履歴なし）")
    return ProbeResult("new_payee_first_payment", False, "既存ベンダー（支払履歴あり）")


def duplicate_check(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    for p in store.payments_for(plan.vendor_id):
        if p.invoice_id == plan.invoice_id or abs(p.amount - plan.amount) < 0.01:
            return ProbeResult("duplicate_invoice", True,
                               f"既支払と重複: {p.invoice_id} / {p.amount} {p.currency}")
    return ProbeResult("duplicate_invoice", False, "重複なし")


def amount_anomaly(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    stats = store.amount_stats(plan.vendor_id)
    if stats is None:
        return ProbeResult("amount_anomaly", False,
                           "履歴なしで分布判定不能", probe_ran=False)
    mean, mx = stats
    if mean > 0 and plan.amount > max(mean * 3, mx * 2):
        return ProbeResult("amount_anomaly", True,
                           f"金額 {plan.amount} が履歴平均 {mean:.0f}/最大 {mx:.0f} を大きく超過")
    return ProbeResult("amount_anomaly", False,
                       f"金額 {plan.amount} は履歴分布内（平均 {mean:.0f}）")


def approval_list(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    v = store.vendor(plan.vendor_id)
    if v is None or not v.approved:
        return ProbeResult("unapproved_vendor", True,
                           f"vendor {plan.vendor_id} は承認済みリスト外")
    return ProbeResult("unapproved_vendor", False, "承認済みベンダー")


def bank_country_mismatch(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    v = store.vendor(plan.vendor_id)
    iban = _norm_iban(plan.bank.get("iban"))
    if v is None or len(iban) < 2:
        return ProbeResult("bank_country_mismatch", False, "判定不能", probe_ran=False)
    iban_country = iban[:2]
    if iban_country != v.registered_country:
        return ProbeResult("bank_country_mismatch", True,
                           f"口座国 {iban_country} != 登記国 {v.registered_country}")
    return ProbeResult("bank_country_mismatch", False,
                       f"口座国 {iban_country} == 登記国")


def round_number(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    if plan.amount >= 1000 and plan.amount % 1000 == 0:
        return ProbeResult("round_number_anomaly", True,
                           f"丸い金額 {plan.amount}（手入力/水増しの兆候・要確認）")
    return ProbeResult("round_number_anomaly", False, "金額は丸い数でない")


def image_consistency(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    """Cross-check the VL-read invoice facts against the structured payment plan.

    This is the leg a text-only competitor cannot build (AMPLIFY Qwen-irreplaceability):
    the judgment basis is what the vision model SAW on the document image."""
    facts = plan.source_image_facts or {}
    doc_iban = _norm_iban(facts.get("iban_on_doc"))
    plan_iban = _norm_iban(plan.bank.get("iban"))
    if not doc_iban:
        return ProbeResult("invoice_image_mismatch", False,
                           "画像から口座を読めず（VL未実行/不鮮明）", probe_ran=False)
    if doc_iban != plan_iban:
        return ProbeResult("invoice_image_mismatch", True,
                           f"請求書画像の口座 {doc_iban} != 支払指示 {plan_iban}")
    return ProbeResult("invoice_image_mismatch", False,
                       f"画像の口座と支払指示が一致 {plan_iban}")


def currency_check(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    pays = store.payments_for(plan.vendor_id)
    known = {p.currency for p in pays}
    if not known:
        return ProbeResult("currency_mismatch", False,
                           "履歴なしで通貨判定不能", probe_ran=False)
    if plan.currency not in known:
        return ProbeResult("currency_mismatch", True,
                           f"通貨 {plan.currency} は履歴通貨 {sorted(known)} と不一致")
    return ProbeResult("currency_mismatch", False,
                       f"通貨 {plan.currency} は履歴と一致")


def tax_id_check(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    """Cross-check the tax/registration id printed on the invoice against the vendor record.

    A mismatched tax id is a classic vendor-impersonation tell. The id read off the document
    lives in source_image_facts['tax_id_on_doc'] (populated by the qwen-vl-max leg)."""
    facts = plan.source_image_facts or {}
    doc_tax = (facts.get("tax_id_on_doc") or "").replace(" ", "").upper()
    v = store.vendor(plan.vendor_id)
    if not doc_tax or v is None or not v.tax_id:
        return ProbeResult("tax_id_mismatch", False,
                           "税ID未読/ベンダー記録なし（判定不能→他probe/escalateへ）",
                           probe_ran=False)
    if doc_tax != v.tax_id.replace(" ", "").upper():
        return ProbeResult("tax_id_mismatch", True,
                           f"請求書の税ID {doc_tax} != 登録税ID {v.tax_id}（なりすまし兆候）")
    return ProbeResult("tax_id_mismatch", False, f"税ID一致 {v.tax_id}")


def po_match(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
    """Three-way-match guard: the invoice amount must agree with its referenced purchase order.

    The PO number/amount the invoice cites are read off the document
    (source_image_facts['po_amount']). A figure that disagrees with the authorizing PO is the
    canonical over-billing / no-PO fraud, so a confirmed gap blocks."""
    facts = plan.source_image_facts or {}
    raw = facts.get("po_amount")
    if raw in (None, ""):
        return ProbeResult("po_mismatch", False,
                           "発注書(PO)参照なし（3way照合不能→escalateへ）", probe_ran=False)
    try:
        po_amount = float(raw)
    except (TypeError, ValueError):
        return ProbeResult("po_mismatch", False,
                           f"PO金額が数値でない（{raw!r}）→判定不能", probe_ran=False)
    if abs(po_amount - plan.amount) >= 0.01:
        return ProbeResult("po_mismatch", True,
                           f"請求金額 {plan.amount} != 発注書(PO)金額 {po_amount}（3way不一致）")
    return ProbeResult("po_mismatch", False, f"PO金額と一致 {po_amount}")


def _unwired(mode_id: str) -> ProbeFn:
    """Probe names referenced by registry/memory but not yet implemented here resolve to
    an honest 'cannot falsify' so the engine escalates instead of silently passing."""

    def _fn(plan: PaymentPlan, store: DemoDataStore) -> ProbeResult:
        return ProbeResult(mode_id, False,
                           f"probe '{mode_id}' は未実装（反証不能→escalate）",
                           probe_ran=False)

    return _fn


class ProbeRegistry:
    def __init__(self, probes: dict[str, ProbeFn] | None = None):
        self._probes: dict[str, ProbeFn] = probes if probes is not None else {}

    def register(self, name: str, fn: ProbeFn) -> None:
        self._probes[name] = fn

    def get(self, name: str) -> ProbeFn:
        return self._probes.get(name, _unwired(name))

    def has(self, name: str) -> bool:
        return name in self._probes

    def names(self) -> list[str]:
        return sorted(self._probes)


def default_registry() -> ProbeRegistry:
    return ProbeRegistry({
        "bank_detail_diff": bank_detail_diff,
        "vendor_age": vendor_age,
        "duplicate_check": duplicate_check,
        "amount_anomaly": amount_anomaly,
        "approval_list": approval_list,
        "bank_country_mismatch": bank_country_mismatch,
        "round_number": round_number,
        "image_consistency": image_consistency,
        "currency_check": currency_check,
        "tax_id_check": tax_id_check,
        "po_match": po_match,
        # Memory-seeded modes reuse their id as probe name; map the common ones:
        "bank_changed": bank_detail_diff,
        "unapproved_vendor": approval_list,
        "duplicate_invoice": duplicate_check,
        "invoice_image_mismatch": image_consistency,
        "currency_mismatch": currency_check,
        "tax_id_mismatch": tax_id_check,
        "po_mismatch": po_match,
    })
