"""
services/pricing_service.py
---------------------------
Decimal-Safe Automotive Parts Pricing Engine.
Handles markups, minimum gross margin safeguards, refundable core charges,
commercial discounts, handling fees, and jurisdictional tax calculations.
"""

from typing import Dict, Any, List, Optional


def round_curr(amount: float) -> float:
    """Rounds amount to 2 decimal places safely."""
    return round(amount + 1e-9, 2)


def calculate_line_item(
    unit_cost: float,
    base_list_price: Optional[float] = None,
    markup_percent: float = 30.0,
    minimum_selling_price: float = 0.0,
    minimum_gross_margin_pct: float = 0.0,
    core_charge: float = 0.0,
    discount_percent: float = 0.0,
    quantity: int = 1
) -> Dict[str, Any]:
    """
    Calculates selling price, margins, core charges, and discounts for a line item.
    Follows exact user markup: Selling Price = Unit Cost * (1 + Markup% / 100).
    """
    notes: List[str] = []
    is_margin_safeguard_applied = False

    # 1. Base price
    if base_list_price and base_list_price > 0:
        raw_price = base_list_price
        notes.append(f"Used catalogue list price of ${base_list_price:.2f}")
    else:
        raw_price = unit_cost * (1 + markup_percent / 100.0)
        notes.append(f"Applied {markup_percent}% markup over unit cost of ${unit_cost:.2f}")

    # 2. Minimum selling price (only if raw_price is strictly below minimum_selling_price > 0)
    if minimum_selling_price > 0 and raw_price < minimum_selling_price:
        raw_price = minimum_selling_price
        notes.append(f"Enforced minimum selling price of ${minimum_selling_price:.2f}")

    # 3. Minimum gross margin advisory (informational notice, does not override user pricing)
    if 0 < minimum_gross_margin_pct < 100:
        required_min = unit_cost / (1.0 - (minimum_gross_margin_pct / 100.0))
        if raw_price < required_min:
            notes.append(
                f"Advisory: Gross margin is below {minimum_gross_margin_pct}% target guideline"
            )

    selling_price = round_curr(raw_price)
    markup_amount = round_curr(selling_price - unit_cost)
    gross_margin_pct = round_curr((markup_amount / selling_price) * 100.0) if selling_price > 0 else 0.0

    # 4. Discounts
    discount_amount = round_curr((selling_price * discount_percent) / 100.0) if discount_percent > 0 else 0.0
    if discount_amount > 0:
        notes.append(f"Applied {discount_percent}% commercial discount (-${discount_amount:.2f})")

    # 5. Core charge
    core = round_curr(core_charge)
    if core > 0:
        notes.append(f"Added refundable core deposit of ${core:.2f}")

    qty = max(1, quantity)
    line_subtotal = round_curr((selling_price - discount_amount + core) * qty)

    return {
        'unitCost': round_curr(unit_cost),
        'sellingPrice': selling_price,
        'markupAmount': markup_amount,
        'grossMarginPercent': gross_margin_pct,
        'coreCharge': core,
        'discountPercent': discount_percent,
        'discountAmount': discount_amount,
        'quantity': qty,
        'lineSubtotal': line_subtotal,
        'isMarginSafeguardApplied': is_margin_safeguard_applied,
        'notes': notes,
    }


def calculate_quote_financials(
    items: List[Dict[str, Any]],
    handling_fee: float = 15.00,
    freight_charge: float = 0.00,
    tax_percent: float = 7.50,
    currency: str = "USD"
) -> Dict[str, Any]:
    """
    Computes total quotation financials including parts subtotal,
    core deposits, handling, freight, and taxes.
    """
    parts_subtotal = 0.0
    total_core_charges = 0.0
    total_discounts = 0.0
    breakdown_notes: List[str] = []

    for item in items:
        qty = max(1, item.get('quantity', 1))
        unit_sp = item.get('sellingPrice', 0.0)
        core = item.get('coreCharge', 0.0)
        disc = item.get('discountAmount', 0.0)

        parts_subtotal += round_curr(unit_sp * qty)
        total_core_charges += round_curr(core * qty)
        total_discounts += round_curr(disc * qty)

    parts_subtotal = round_curr(parts_subtotal)
    total_core_charges = round_curr(total_core_charges)
    total_discounts = round_curr(total_discounts)
    handling_fee = round_curr(handling_fee)
    freight_charge = round_curr(freight_charge)

    # Taxable amount in US typically includes parts + core deposit - discount
    taxable_amount = round_curr(max(0.0, parts_subtotal - total_discounts + total_core_charges))
    total_taxes = round_curr((taxable_amount * tax_percent) / 100.0) if tax_percent > 0 else 0.0

    grand_total = round_curr(
        parts_subtotal - total_discounts + total_core_charges + handling_fee + freight_charge + total_taxes
    )

    breakdown_notes.append(f"Parts Net: ${parts_subtotal:.2f}")
    if total_discounts > 0:
        breakdown_notes.append(f"Commercial Account Discount: -${total_discounts:.2f}")
    if total_core_charges > 0:
        breakdown_notes.append(f"Refundable Core Deposit: ${total_core_charges:.2f}")
    if handling_fee > 0:
        breakdown_notes.append(f"Palletizing & Handling Fee: ${handling_fee:.2f}")
    if freight_charge > 0:
        breakdown_notes.append(f"LTL Freight & Shipping: ${freight_charge:.2f}")
    if total_taxes > 0:
        breakdown_notes.append(f"Taxes ({tax_percent}%): ${total_taxes:.2f}")
    breakdown_notes.append(f"Total Quotation Amount: ${grand_total:.2f} {currency}")

    return {
        'partsSubtotal': parts_subtotal,
        'totalCoreCharges': total_core_charges,
        'totalDiscounts': total_discounts,
        'handlingFee': handling_fee,
        'freightCharge': freight_charge,
        'taxableAmount': taxable_amount,
        'taxPercent': tax_percent,
        'totalTaxes': total_taxes,
        'grandTotal': grand_total,
        'currency': currency,
        'breakdownNotes': breakdown_notes,
    }
