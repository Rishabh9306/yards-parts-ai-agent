"""
services/freight_service.py
---------------------------
Freight and Shipping Estimation Engine.
Implements US zone-based distance calculation, dimensional weight,
LTL freight classifications, and carrier surcharge rules.
"""

from typing import Dict, Any, List, Optional
from app.services.pricing_service import round_curr


def calculate_shipping_zone(origin_zip: str, dest_zip: str) -> int:
    """
    Calculates US shipping zone (2 to 8) based on 3-digit ZIP prefixes.
    """
    try:
        o3 = int(origin_zip[:3])
        d3 = int(dest_zip[:3])
        diff = abs(o3 - d3)
        if diff < 50:
            return 2
        elif diff < 150:
            return 3
        elif diff < 300:
            return 4
        elif diff < 500:
            return 5
        elif diff < 700:
            return 6
        elif diff < 850:
            return 7
        else:
            return 8
    except Exception:
        return 5  # Default intermediate zone


def estimate_freight(
    origin_zip: str = "43215",
    destination_zip: str = "77001",
    weight_lbs: float = 150.0,
    service_type: str = "LTL_FREIGHT",
    is_residential: bool = False,
    requires_liftgate: bool = False,
    length_in: Optional[float] = None,
    width_in: Optional[float] = None,
    height_in: Optional[float] = None
) -> Dict[str, Any]:
    """
    Estimates freight charge based on weight, dimensions, distance zone, and accessorial services.
    """
    missing_info: List[str] = []
    breakdown: List[str] = []

    origin_clean = "".join([c for c in (origin_zip or "") if c.isdigit()])
    dest_clean = "".join([c for c in (destination_zip or "") if c.isdigit()])

    if len(origin_clean) < 5:
        missing_info.append("Valid 5-digit origin ZIP code required.")
    if len(dest_clean) < 5:
        missing_info.append("Valid 5-digit destination ZIP code required.")
    if weight_lbs <= 0:
        missing_info.append("Part weight must be greater than zero.")

    if missing_info:
        return {
            'isEstimated': False,
            'provider': 'REGIONAL_ZONE_ESTIMATOR',
            'serviceType': service_type,
            'originZip': origin_clean or '43215',
            'destinationZip': dest_clean or 'UNKNOWN',
            'billedWeightLbs': weight_lbs,
            'actualWeightLbs': weight_lbs,
            'zone': 0,
            'baseCharge': 0.0,
            'fuelSurcharge': 0.0,
            'liftgateSurcharge': 0.0,
            'residentialSurcharge': 0.0,
            'oversizeSurcharge': 0.0,
            'totalFreightCharge': 0.0,
            'estimatedTransitDays': 0,
            'missingInformation': missing_info,
            'isPending': True,
            'breakdown': ['Freight calculation pending: ' + '; '.join(missing_info)],
            'disclaimer': 'Freight cannot be calculated without origin/destination ZIP codes and shipment weight.',
        }

    # Dimensional weight check
    dim_weight = 0.0
    is_oversized = False
    if length_in and width_in and height_in:
        divisor = 166.0 if service_type == 'LTL_FREIGHT' else 139.0
        dim_weight = round_curr((length_in * width_in * height_in) / divisor)
        if length_in > 60 or width_in > 48 or height_in > 48:
            is_oversized = True

    billed_weight = max(weight_lbs, dim_weight)
    zone = calculate_shipping_zone(origin_clean, dest_clean)

    transit_days = 2 + (zone // 2)

    if service_type == 'LTL_FREIGHT':
        # Heavy pallet freight (Engines, Transmissions, Rear Axles)
        min_charge = 120.0 + (zone * 15.0)
        rate_per_lb = 0.35 + (zone * 0.08)
        base_rate = max(min_charge, billed_weight * rate_per_lb)
        breakdown.append(f"LTL Freight base (Zone {zone}, {billed_weight:.1f} lbs @ ${rate_per_lb:.2f}/lb): ${base_rate:.2f}")
    elif service_type == 'EXPEDITED':
        min_charge = 45.0 + (zone * 12.0)
        rate_per_lb = 0.85 + (zone * 0.15)
        base_rate = max(min_charge, billed_weight * rate_per_lb)
        transit_days = max(1, transit_days - 2)
        breakdown.append(f"Expedited Air/Express base (Zone {zone}, {billed_weight:.1f} lbs): ${base_rate:.2f}")
    else:
        # PARCEL_GROUND (Alternators, Starters, Small Components)
        min_charge = 14.0 + (zone * 2.0)
        rate_per_lb = 0.40 + (zone * 0.06)
        base_rate = max(min_charge, billed_weight * rate_per_lb)
        breakdown.append(f"Ground Parcel base (Zone {zone}, {billed_weight:.1f} lbs): ${base_rate:.2f}")

    base_rate = round_curr(base_rate)

    # 1. Fuel surcharge (12.5% of base)
    fuel_surcharge = round_curr(base_rate * 0.125)
    breakdown.append(f"Carrier Fuel Surcharge (12.5%): ${fuel_surcharge:.2f}")

    # 2. Residential delivery surcharge
    residential_surcharge = 0.0
    if is_residential:
        residential_surcharge = 45.0 if service_type == 'LTL_FREIGHT' else 5.50
        breakdown.append(f"Residential Delivery Accessorial: ${residential_surcharge:.2f}")

    # 3. Hydraulic Liftgate surcharge (critical for heavy engines/transmissions)
    liftgate_surcharge = 0.0
    if requires_liftgate or (service_type == 'LTL_FREIGHT' and weight_lbs > 120):
        liftgate_surcharge = 65.0
        breakdown.append(f"Hydraulic Liftgate Service: ${liftgate_surcharge:.2f}")

    # 4. Oversize surcharge
    oversize_surcharge = 0.0
    if is_oversized:
        oversize_surcharge = 35.0
        breakdown.append(f"Oversize Dimension Fee: ${oversize_surcharge:.2f}")

    total_freight = round_curr(
        base_rate + fuel_surcharge + residential_surcharge + liftgate_surcharge + oversize_surcharge
    )

    return {
        'isEstimated': True,
        'provider': 'REGIONAL_ZONE_ESTIMATOR',
        'serviceType': service_type,
        'originZip': origin_clean,
        'destinationZip': dest_clean,
        'billedWeightLbs': billed_weight,
        'actualWeightLbs': weight_lbs,
        'dimensionalWeightLbs': dim_weight if dim_weight > 0 else None,
        'zone': zone,
        'baseCharge': base_rate,
        'fuelSurcharge': fuel_surcharge,
        'liftgateSurcharge': liftgate_surcharge,
        'residentialSurcharge': residential_surcharge,
        'oversizeSurcharge': oversize_surcharge,
        'totalFreightCharge': total_freight,
        'estimatedTransitDays': transit_days,
        'missingInformation': [],
        'isPending': False,
        'breakdown': breakdown,
        'disclaimer': (
            'Freight rate estimated via regional LTL density matrix. '
            'Final billing based on certified freight scale weight and dock access at destination.'
        ),
    }
