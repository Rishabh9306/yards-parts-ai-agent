"""
services/hollander_service.py
-----------------------------
Hollander Interchange & Automotive Parts Compatibility Engine.
Implements strict fitment verification, evidence tracking, 
multi-source compatibility resolution, and confidence scoring.
"""

from typing import Dict, Any, List, Optional

# Verified Hollander Interchange Master Catalog
HOLLANDER_MASTER_RULES: List[Dict[str, Any]] = [
    # 2018 Honda Civic 2.0L Engine
    {
        'hollanderNumber': '300-08921',
        'partNumber': 'ENG-HND-18-20L',
        'partName': '2016-2021 Honda Civic 2.0L I4 Engine Assembly (K20C2)',
        'category': 'Engine',
        'oemPartNumber': '10002-5BA-A00',
        'make': 'HONDA',
        'model': 'CIVIC',
        'yearStart': 2016,
        'yearEnd': 2021,
        'engineSpecs': '2.0L',
        'transmissionSpecs': None,
        'driveType': 'FWD',
        'weightLbs': 275.0,
        'unitCost': 650.00,
        'listPrice': 975.00,
        'coreCharge': 150.00,
        'fitmentNotes': 'Fits 2016-2021 Honda Civic with 2.0L K20C2 non-turbo engine. Will NOT fit 1.5L Turbo.',
    },
    # 2018 Honda Civic 1.5L Turbo Engine
    {
        'hollanderNumber': '300-08922',
        'partNumber': 'ENG-HND-18-15T',
        'partName': '2016-2021 Honda Civic 1.5L Turbocharged Engine Assembly (L15B7)',
        'category': 'Engine',
        'oemPartNumber': '10002-5AA-A00',
        'make': 'HONDA',
        'model': 'CIVIC',
        'yearStart': 2016,
        'yearEnd': 2021,
        'engineSpecs': '1.5L',
        'transmissionSpecs': None,
        'driveType': 'FWD',
        'weightLbs': 260.0,
        'unitCost': 850.00,
        'listPrice': 1250.00,
        'coreCharge': 200.00,
        'fitmentNotes': 'Fits 1.5L Turbo models only (EX-T, Touring, Si). Incompatible with 2.0L naturally aspirated.',
    },
    # Honda Civic CVT Transmission
    {
        'hollanderNumber': '400-06120',
        'partNumber': 'TRN-HND-18-CVT',
        'partName': '2016-2020 Honda Civic CVT Automatic Transmission',
        'category': 'Transmission',
        'oemPartNumber': '20021-5BA-A01',
        'make': 'HONDA',
        'model': 'CIVIC',
        'yearStart': 2016,
        'yearEnd': 2020,
        'engineSpecs': '2.0L',
        'transmissionSpecs': 'CVT',
        'driveType': 'FWD',
        'weightLbs': 185.0,
        'unitCost': 520.00,
        'listPrice': 780.00,
        'coreCharge': 125.00,
        'fitmentNotes': 'Fits 2.0L engine equipped Civic models with CVT automatic.',
    },
    # Honda Civic Alternator
    {
        'hollanderNumber': '601-58912',
        'partNumber': 'ALT-HND-18-135A',
        'partName': '2016-2021 Honda Civic 135A Denso Alternator',
        'category': 'Alternator',
        'oemPartNumber': '31100-5BA-A01',
        'make': 'HONDA',
        'model': 'CIVIC',
        'yearStart': 2016,
        'yearEnd': 2021,
        'engineSpecs': '2.0L',
        'transmissionSpecs': None,
        'driveType': None,
        'weightLbs': 14.5,
        'unitCost': 95.00,
        'listPrice': 155.00,
        'coreCharge': 35.00,
        'fitmentNotes': 'Fits all 2.0L Civic models 2016-2021.',
    },
    # Ford F-150 3.5L EcoBoost Engine
    {
        'hollanderNumber': '300-10452',
        'partNumber': 'ENG-FRD-19-35T',
        'partName': '2018-2020 Ford F-150 3.5L EcoBoost Twin-Turbo V6 Engine',
        'category': 'Engine',
        'oemPartNumber': 'JL3Z-6006-D',
        'make': 'FORD',
        'model': 'F-150',
        'yearStart': 2018,
        'yearEnd': 2020,
        'engineSpecs': '3.5L',
        'transmissionSpecs': 'Automatic',
        'driveType': '4WD',
        'weightLbs': 480.0,
        'unitCost': 1950.00,
        'listPrice': 2850.00,
        'coreCharge': 350.00,
        'fitmentNotes': 'Fits 2018-2020 Ford F-150 with 3.5L EcoBoost. Does not fit 2.7L or 3.3L.',
    },
    # Toyota Camry 2.5L Engine
    {
        'hollanderNumber': '300-09871',
        'partNumber': 'ENG-TOY-20-25L',
        'partName': '2018-2022 Toyota Camry 2.5L 4-Cylinder A25A-FKS Engine',
        'category': 'Engine',
        'oemPartNumber': '19000-25010',
        'make': 'TOYOTA',
        'model': 'CAMRY',
        'yearStart': 2018,
        'yearEnd': 2022,
        'engineSpecs': '2.5L',
        'transmissionSpecs': 'Automatic',
        'driveType': 'FWD',
        'weightLbs': 290.0,
        'unitCost': 950.00,
        'listPrice': 1420.00,
        'coreCharge': 200.00,
        'fitmentNotes': 'Fits gas-only 2.5L Camry (LE, SE, XLE). Does not fit Hybrid (A25A-FXS).',
    },
    # Toyota Fortuner 2.8L Diesel Turbo Engine
    {
        'hollanderNumber': '300-07718',
        'partNumber': 'ENG-TOY-FTN-28D',
        'partName': 'Toyota Fortuner 2.8L 1GD-FTV D-4D Diesel Engine Assembly',
        'category': 'Engine',
        'oemPartNumber': '19000-0E020',
        'make': 'TOYOTA',
        'model': 'FORTUNER',
        'yearStart': 2016,
        'yearEnd': 2024,
        'engineSpecs': '2.8L',
        'transmissionSpecs': 'Automatic',
        'driveType': '4WD',
        'weightLbs': 495.0,
        'unitCost': 2200.00,
        'listPrice': 3150.00,
        'coreCharge': 400.00,
        'fitmentNotes': 'Fits Toyota Fortuner & Hilux 2.8L 1GD-FTV Turbo Diesel.',
    },
    # Toyota Innova 2.4L Diesel Engine
    {
        'hollanderNumber': '300-06642',
        'partNumber': 'ENG-TOY-INV-24D',
        'partName': 'Toyota Innova Crysta 2.4L 2GD-FTV Diesel Engine Assembly',
        'category': 'Engine',
        'oemPartNumber': '19000-0E010',
        'make': 'TOYOTA',
        'model': 'INNOVA',
        'yearStart': 2016,
        'yearEnd': 2024,
        'engineSpecs': '2.4L',
        'transmissionSpecs': 'Manual',
        'driveType': 'RWD',
        'weightLbs': 470.0,
        'unitCost': 1850.00,
        'listPrice': 2650.00,
        'coreCharge': 350.00,
        'fitmentNotes': 'Fits Toyota Innova Crysta 2.4L 2GD-FTV diesel.',
    },
]


def evaluate_compatibility(
    vehicle: Dict[str, Any],
    requested_category: Optional[str] = None,
    hollander_number: Optional[str] = None,
    part_query: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Evaluates candidate parts against decoded vehicle specifications using
    Hollander Interchange rules, year ranges, powertrain matching, and confidence metrics.
    """
    results: List[Dict[str, Any]] = []

    v_year = vehicle.get('year') or 0
    v_make = (vehicle.get('make') or '').strip().upper()
    v_model = (vehicle.get('model') or '').strip().upper()
    v_disp = vehicle.get('engineDisplacementL')
    v_trans = (vehicle.get('transmissionStyle') or '').strip().upper()
    v_drive = (vehicle.get('driveType') or '').strip().upper()

    for item in HOLLANDER_MASTER_RULES:
        # Category filter if supplied
        if requested_category and requested_category.lower() != 'all':
            if requested_category.lower() not in item['category'].lower():
                continue

        # Hollander filter if supplied
        if hollander_number:
            if item['hollanderNumber'] != hollander_number:
                continue

        # Part query if supplied
        if part_query:
            pq = part_query.lower()
            match_name = pq in item['partName'].lower()
            match_no = pq in item['partNumber'].lower()
            match_oem = pq in (item.get('oemPartNumber') or '').lower()
            match_hol = pq in (item.get('hollanderNumber') or '').lower()
            if not (match_name or match_no or match_oem or match_hol):
                continue

        evidence: List[str] = []
        missing_info: List[str] = []
        rule_requires_review = False
        engine_match_found = False
        trans_match_found = False

        # If vehicle specs are unavailable
        if not v_year or not v_make or not v_model:
            results.append({
                'hollanderNumber': item['hollanderNumber'],
                'partNumber': item['partNumber'],
                'partName': item['partName'],
                'category': item['category'],
                'oemPartNumber': item['oemPartNumber'],
                'weightLbs': item['weightLbs'],
                'unitCost': item['unitCost'],
                'listPrice': item['listPrice'],
                'coreCharge': item['coreCharge'],
                'status': 'INSUFFICIENT_DATA',
                'confidenceScore': 20,
                'evidence': ['Part identity is verified in Hollander catalog.'],
                'missingInformation': ['Decoded vehicle specs unavailable. Make, Model, and Year required.'],
                'decisionReason': 'Cannot verify compatibility without confirmed vehicle Year, Make, and Model.',
                'fitmentNotes': item['fitmentNotes'],
            })
            continue

        # Check Make match
        make_match = (item['make'].upper() in v_make or v_make in item['make'].upper())
        # Check Model match
        model_match = (item['model'].upper() in v_model or v_model in item['model'].upper())
        # Check Year match
        year_match = (v_year >= item['yearStart'] and v_year <= item['yearEnd'])

        if not (make_match and model_match):
            continue

        if year_match:
            evidence.append(f"Vehicle matches application range: {item['yearStart']}-{item['yearEnd']} {item['make']} {item['model']}")
        else:
            evidence.append(f"Year mismatch: Vehicle is {v_year}, application range is {item['yearStart']}-{item['yearEnd']}")
            rule_requires_review = True

        evidence.append(f"Hollander Interchange code: {item['hollanderNumber']}")

        # Engine displacement check
        if item.get('engineSpecs'):
            rule_disp = item['engineSpecs']
            if v_disp:
                v_disp_str = f"{v_disp:.1f}L"
                if v_disp_str in rule_disp:
                    evidence.append(f"Engine displacement confirmed: {v_disp_str} matches rule spec ({rule_disp})")
                    engine_match_found = True
                else:
                    evidence.append(f"Engine displacement mismatch: Vehicle has {v_disp_str}, part rule specifies {rule_disp}")
                    rule_requires_review = True
            else:
                missing_info.append("Vehicle engine displacement unconfirmed from VIN decode.")

        # Transmission check
        if item.get('transmissionSpecs'):
            rule_trans = item['transmissionSpecs'].upper()
            if v_trans:
                if 'CVT' in rule_trans and 'CVT' in v_trans:
                    evidence.append("Transmission match: CVT automatic transmission confirmed.")
                    trans_match_found = True
                elif 'AUTO' in rule_trans and 'AUTO' in v_trans:
                    evidence.append("Transmission match: Automatic transmission confirmed.")
                    trans_match_found = True
                elif 'MANUAL' in rule_trans and 'MANUAL' in v_trans:
                    evidence.append("Transmission match: Manual transmission confirmed.")
                    trans_match_found = True
                else:
                    evidence.append(f"Transmission discrepancy: Decoded ({v_trans}) vs rule ({rule_trans})")
                    rule_requires_review = True
            else:
                missing_info.append("Vehicle transmission style unconfirmed from VIN decode.")

        # Drive type check
        if item.get('driveType') and v_drive:
            if item['driveType'].upper() in v_drive:
                evidence.append(f"Drivetrain confirmed: {item['driveType']}")
            else:
                evidence.append(f"Drivetrain check: Vehicle is {v_drive}, part rule notes {item['driveType']}")

        # Status and Confidence computation
        if rule_requires_review:
            status = 'REQUIRES_REVIEW'
            confidence = 55
            decision = 'Fitment variance detected (e.g. engine displacement or year range variance). Manual specialist review required.'
        elif missing_info:
            status = 'POTENTIAL_MATCH'
            confidence = 75
            decision = f"Potential fitment found for {item['make']} {item['model']}. Missing vehicle build options ({', '.join(missing_info)}) require verification."
        elif engine_match_found or item['category'] in ('Alternator', 'Headlight', 'Starter', 'Body'):
            status = 'VERIFIED_COMPATIBLE'
            confidence = 95
            decision = f"Fully verified fitment based on confirmed Hollander Interchange ({item['hollanderNumber']}) and matching powertrain build specifications."
        else:
            status = 'POTENTIAL_MATCH'
            confidence = 80
            decision = 'Vehicle chassis matches Hollander Interchange catalog. Ready for parts specialist approval.'

        results.append({
            'hollanderNumber': item['hollanderNumber'],
            'partNumber': item['partNumber'],
            'partName': item['partName'],
            'category': item['category'],
            'oemPartNumber': item['oemPartNumber'],
            'weightLbs': item['weightLbs'],
            'unitCost': item['unitCost'],
            'listPrice': item['listPrice'],
            'coreCharge': item['coreCharge'],
            'status': status,
            'confidenceScore': confidence,
            'evidence': evidence,
            'missingInformation': missing_info,
            'decisionReason': decision,
            'fitmentNotes': item['fitmentNotes'],
        })

    # Sort descending by confidence score
    results.sort(key=lambda x: x['confidenceScore'], reverse=True)
    return results
