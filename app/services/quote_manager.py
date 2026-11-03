"""
services/quote_manager.py
-------------------------
Coordinates VIN decoding, Hollander fitment, pricing calculations,
LTL freight estimates, database persistence, and PDF quote generation.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.db import VehicleRecord, QuoteProposal, QuoteLineItem
from app.services.vin_service import decode_vin
from app.services.hollander_service import evaluate_compatibility
from app.services.pricing_service import calculate_line_item, calculate_quote_financials, round_curr
from app.services.freight_service import estimate_freight
from app.services.pdf_quote_service import generate_formal_quote_pdf


def get_or_create_vehicle_record(db: Session, vin: str) -> VehicleRecord:
    """Finds existing decoded vehicle by VIN or decodes and caches in DB."""
    rec = db.query(VehicleRecord).filter(VehicleRecord.vin == vin.upper()).first()
    if rec:
        return rec

    decoded = decode_vin(vin)
    rec = VehicleRecord(
        vin=decoded.get('vin', vin.upper()),
        year=decoded.get('year') or 2018,
        make=decoded.get('make', 'UNKNOWN'),
        model=decoded.get('model', 'UNKNOWN'),
        trim=decoded.get('trim'),
        body_class=decoded.get('bodyClass'),
        engine_displacement=decoded.get('engineDisplacementL'),
        engine_cylinders=decoded.get('engineCylinders'),
        fuel_type=decoded.get('fuelType'),
        transmission=decoded.get('transmissionStyle'),
        drive_type=decoded.get('driveType'),
        plant_country=decoded.get('plantCountry'),
        status=decoded.get('status', 'DECODED'),
        raw_json=json.dumps(decoded),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def create_new_quote(db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates a new formal QuoteProposal and line items, performs financial calculations,
    estimates freight, generates official PDF, and commits to SQLite.
    """
    vin = (data.get('vin') or '').strip().upper()
    veh_rec = None
    vehicle_summary = data.get('vehicleSummary')

    if vin and len(vin) == 17:
        veh_rec = get_or_create_vehicle_record(db, vin)
        if not vehicle_summary:
            vehicle_summary = f"{veh_rec.year} {veh_rec.make} {veh_rec.model}"
            if veh_rec.trim:
                vehicle_summary += f" {veh_rec.trim}"
            if veh_rec.engine_displacement:
                vehicle_summary += f" {veh_rec.engine_displacement}L"

    # Destination ZIP
    dest_zip = data.get('destinationZip', '43215')
    origin_zip = data.get('originZip', '43215')

    # Line items
    raw_items = data.get('items') or data.get('lineItems') or []
    if not raw_items:
        # Check if single item passed at root of payload
        if data.get('partDescription') or data.get('partName'):
            raw_items = [{
                'partName': data.get('partName') or data.get('partDescription'),
                'hollanderNumber': data.get('hollanderNumber'),
                'oemPartNumber': data.get('oemNumber') or data.get('oemPartNumber'),
                'unitCost': float(data.get('unitCost', 650.0)),
                'sellingPrice': float(data.get('sellingPrice', 845.0)),
                'coreCharge': float(data.get('coreCharge', 150.0)),
                'discountPercent': float(data.get('discountPercent', 0.0)),
                'quantity': int(data.get('quantity', 1)),
                'weightLbs': float(data.get('weightLbs', 275.0)),
            }]
        else:
            raise ValueError("Cannot create a quote with zero line items. Please add at least one part.")
    line_items_data = []
    total_weight = 0.0

    for itm in raw_items:
        unit_cost = float(itm.get('unitCost', 0.0))
        list_price = float(itm.get('listPrice', 0.0)) if itm.get('listPrice') else None
        markup_pct = float(itm.get('markupPercent', 30.0))
        min_margin_pct = float(itm.get('minMarginPercent', 0.0))
        core = float(itm.get('coreCharge', 0.0))
        discount_pct = float(itm.get('discountPercent', 0.0))
        qty = int(itm.get('quantity', 1))
        weight = float(itm.get('weightLbs', 25.0)) * qty
        total_weight += weight

        calc = calculate_line_item(
            unit_cost=unit_cost,
            base_list_price=list_price,
            markup_percent=markup_pct,
            minimum_gross_margin_pct=min_margin_pct,
            core_charge=core,
            discount_percent=discount_pct,
            quantity=qty
        )

        evidence = itm.get('evidence', [])
        if isinstance(evidence, str):
            evidence = [evidence]

        line_items_data.append({
            'partName': itm.get('partName', 'Automotive Component'),
            'partNumber': itm.get('partNumber'),
            'hollanderNumber': itm.get('hollanderNumber'),
            'oemPartNumber': itm.get('oemPartNumber'),
            'category': itm.get('category'),
            'unitCost': calc['unitCost'],
            'sellingPrice': calc['sellingPrice'],
            'coreCharge': calc['coreCharge'],
            'discountAmount': calc['discountAmount'],
            'quantity': qty,
            'lineSubtotal': calc['lineSubtotal'],
            'fitmentStatus': itm.get('fitmentStatus', 'VERIFIED_COMPATIBLE'),
            'fitmentNotes': itm.get('fitmentNotes'),
            'evidenceJson': json.dumps(evidence),
            'notes': calc['notes'],
        })

    # Freight estimation
    service_type = data.get('freightServiceType', 'LTL_FREIGHT' if total_weight > 70 else 'PARCEL_GROUND')
    is_res = bool(data.get('isResidential', False))
    req_lift = bool(data.get('requiresLiftgate', total_weight > 120))

    freight_res = estimate_freight(
        origin_zip=origin_zip,
        destination_zip=dest_zip,
        weight_lbs=max(10.0, total_weight),
        service_type=service_type,
        is_residential=is_res,
        requires_liftgate=req_lift
    )

    # Financials
    handling_fee = float(data.get('handlingFee', 15.00))
    tax_pct = float(data.get('taxPercent', 7.50))
    freight_charge = freight_res['totalFreightCharge']

    fin = calculate_quote_financials(
        items=line_items_data,
        handling_fee=handling_fee,
        freight_charge=freight_charge,
        tax_percent=tax_pct
    )

    # Generate unique quote number: YP-2026-XXXX
    count = db.query(QuoteProposal).count() + 1
    quote_num = f"YP-{datetime.utcnow().year}-{count:04d}"

    # Build PDF
    pdf_filename = f"Quote_{quote_num}_{int(datetime.utcnow().timestamp())}.pdf"
    pdf_path = f"temp_quotes/{pdf_filename}"

    vehicle_dict = {
        'vin': veh_rec.vin if veh_rec else (vin or 'N/A'),
        'year': veh_rec.year if veh_rec else '',
        'make': veh_rec.make if veh_rec else '',
        'model': veh_rec.model if veh_rec else '',
        'trim': veh_rec.trim if veh_rec else '',
        'engineDisplacementL': veh_rec.engine_displacement if veh_rec else None,
        'transmissionStyle': veh_rec.transmission if veh_rec else 'Automatic',
        'driveType': veh_rec.drive_type if veh_rec else '',
    }

    pdf_quote_payload = {
        'quoteNumber': quote_num,
        'createdDate': datetime.utcnow().strftime('%B %d, %Y'),
        'validUntil': (datetime.utcnow() + timedelta(days=14)).strftime('%B %d, %Y'),
        'customerName': data.get('customerName', 'Commercial Account'),
        'customerPhone': data.get('customerPhone', 'On File'),
        'customerEmail': data.get('customerEmail', 'On File'),
        'destinationZip': dest_zip,
        'vehicle': vehicle_dict,
        'items': line_items_data,
        'financials': fin,
        'freightDetails': f"{service_type.replace('_', ' ').title()} &bull; Zone {freight_res['zone']} &bull; {freight_res['estimatedTransitDays']} Days Transit",
    }

    generate_formal_quote_pdf(pdf_quote_payload, pdf_path)

    # Persist Quote
    quote_rec = QuoteProposal(
        quote_number=quote_num,
        customer_name=data.get('customerName', 'Valued Customer'),
        customer_phone=data.get('customerPhone'),
        customer_email=data.get('customerEmail'),
        destination_zip=dest_zip,
        vehicle_id=veh_rec.id if veh_rec else None,
        vehicle_summary=vehicle_summary,
        parts_subtotal=fin['partsSubtotal'],
        total_core_charges=fin['totalCoreCharges'],
        total_discounts=fin['totalDiscounts'],
        handling_fee=fin['handlingFee'],
        freight_charge=fin['freightCharge'],
        freight_zone=freight_res['zone'],
        tax_amount=fin['totalTaxes'],
        grand_total=fin['grandTotal'],
        status="DRAFT",
        pdf_path=pdf_path,
        valid_until=datetime.utcnow() + timedelta(days=14),
    )
    db.add(quote_rec)
    db.commit()
    db.refresh(quote_rec)

    # Persist Line Items
    for itm in line_items_data:
        li = QuoteLineItem(
            quote_id=quote_rec.id,
            part_name=itm['partName'],
            part_number=itm.get('partNumber'),
            hollander_number=itm.get('hollanderNumber'),
            oem_part_number=itm.get('oemPartNumber'),
            category=itm.get('category'),
            unit_cost=itm['unitCost'],
            selling_price=itm['sellingPrice'],
            core_charge=itm['coreCharge'],
            discount_amount=itm['discountAmount'],
            quantity=itm['quantity'],
            line_subtotal=itm['lineSubtotal'],
            fitment_status=itm['fitmentStatus'],
            fitment_notes=itm.get('fitmentNotes'),
            evidence_json=itm['evidenceJson'],
        )
        db.add(li)
    db.commit()

    # Dispatch outbound CRM webhook event to Kiran's CRM
    try:
        from app.crm.webhook_dispatcher import dispatch_crm_event
        dispatch_crm_event("quote.created", {
            "quoteId": quote_rec.id,
            "quoteNumber": quote_num,
            "customerName": quote_rec.customer_name,
            "customerPhone": quote_rec.customer_phone,
            "customerEmail": quote_rec.customer_email,
            "vehicle": vehicle_dict,
            "vehicleSummary": vehicle_summary,
            "destinationZip": dest_zip,
            "partsSubtotal": fin['partsSubtotal'],
            "totalCoreCharges": fin['totalCoreCharges'],
            "freightCharge": fin['freightCharge'],
            "grandTotal": fin['grandTotal'],
            "status": quote_rec.status,
            "pdfUrl": f"/api/quotes/{quote_rec.id}/pdf",
            "itemsCount": len(line_items_data),
        })
    except Exception as e:
        print(f"[CRM Dispatcher] Error notifying CRM of new quote: {e}")

    return {
        'id': quote_rec.id,
        'quoteNumber': quote_num,
        'customerName': quote_rec.customer_name,
        'customerPhone': quote_rec.customer_phone,
        'customerEmail': quote_rec.customer_email,
        'destinationZip': dest_zip,
        'vehicleSummary': vehicle_summary,
        'financials': fin,
        'freight': freight_res,
        'items': line_items_data,
        'pdfUrl': f"/api/quotes/{quote_rec.id}/pdf",
        'status': quote_rec.status,
    }


def get_quote_detail(db: Session, quote_id: int) -> Optional[Dict[str, Any]]:
    quote = db.query(QuoteProposal).filter(QuoteProposal.id == quote_id).first()
    if not quote:
        return None

    items = []
    for itm in quote.items:
        items.append({
            'id': itm.id,
            'partName': itm.part_name,
            'partNumber': itm.part_number,
            'hollanderNumber': itm.hollander_number,
            'oemPartNumber': itm.oem_part_number,
            'category': itm.category,
            'sellingPrice': itm.selling_price,
            'coreCharge': itm.core_charge,
            'discountAmount': itm.discount_amount,
            'quantity': itm.quantity,
            'lineSubtotal': itm.line_subtotal,
            'fitmentStatus': itm.fitment_status,
            'fitmentNotes': itm.fitment_notes,
            'evidence': json.loads(itm.evidence_json or "[]"),
        })

    return {
        'id': quote.id,
        'quoteNumber': quote.quote_number,
        'customerName': quote.customer_name,
        'customerPhone': quote.customer_phone,
        'customerEmail': quote.customer_email,
        'destinationZip': quote.destination_zip,
        'vehicleSummary': quote.vehicle_summary,
        'financials': {
            'partsSubtotal': quote.parts_subtotal,
            'totalCoreCharges': quote.total_core_charges,
            'totalDiscounts': quote.total_discounts,
            'handlingFee': quote.handling_fee,
            'freightCharge': quote.freight_charge,
            'totalTaxes': quote.tax_amount,
            'grandTotal': quote.grand_total,
        },
        'partsSubtotal': quote.parts_subtotal,
        'totalCoreCharges': quote.total_core_charges,
        'totalDiscounts': quote.total_discounts,
        'handlingFee': quote.handling_fee,
        'freightCharge': quote.freight_charge,
        'taxAmount': quote.tax_amount,
        'grandTotal': quote.grand_total,
        'status': quote.status,
        'pdfPath': quote.pdf_path,
        'pdfUrl': f"/api/quotes/{quote.id}/pdf",
        'createdAt': quote.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'items': items,
    }
