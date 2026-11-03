"""
services/vin_service.py
-----------------------
VIN Validation and Normalization Engine & NHTSA vPIC Vehicle Decoder.
Conforms to US 49 CFR Part 565 and ISO 3779 standards.
Queries official NHTSA vPIC API with latency tracking and offline fallback cache.
"""

import time
import httpx
from typing import Dict, Any, List, Optional

# Letter transliteration values for US 49 CFR Part 565 check digit calculation
VIN_LETTER_VALUES = {
    'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
    'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
    'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9,
    '0': 0, '1': 1, '2': 2, '3': 3, '4': 4,
    '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
}

# Position weights (1-indexed positions 1 to 17)
VIN_POSITION_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

# Well-known demo vehicles for guaranteed offline / test execution
DEMO_VEHICLES: Dict[str, Dict[str, Any]] = {
    '19XFC2F5XJE000001': {
        'vin': '19XFC2F5XJE000001',
        'year': 2018,
        'make': 'HONDA',
        'model': 'CIVIC',
        'trim': 'EX',
        'bodyClass': 'Sedan',
        'vehicleType': 'PASSENGER CAR',
        'engineDisplacementL': 2.0,
        'engineCylinders': 4,
        'engineConfiguration': 'In-Line (I4)',
        'fuelType': 'Gasoline',
        'transmissionStyle': 'Continuously Variable Transmission (CVT)',
        'transmissionSpeeds': None,
        'driveType': 'FWD (Front-Wheel Drive)',
        'plantCountry': 'UNITED STATES',
        'plantState': 'INDIANA',
        'plantCity': 'GREENSBURG',
        'source': 'DEMO_SYNTHETIC',
        'status': 'DECODED',
        'missingCriticalFields': [],
    },
    '19XFC1F98JE000002': {
        'vin': '19XFC1F98JE000002',
        'year': 2018,
        'make': 'HONDA',
        'model': 'CIVIC',
        'trim': 'Touring',
        'bodyClass': 'Sedan',
        'vehicleType': 'PASSENGER CAR',
        'engineDisplacementL': 1.5,
        'engineCylinders': 4,
        'engineConfiguration': 'In-Line Turbo (I4)',
        'fuelType': 'Gasoline',
        'transmissionStyle': 'Continuously Variable Transmission (CVT)',
        'transmissionSpeeds': None,
        'driveType': 'FWD (Front-Wheel Drive)',
        'plantCountry': 'UNITED STATES',
        'plantState': 'INDIANA',
        'plantCity': 'GREENSBURG',
        'source': 'DEMO_SYNTHETIC',
        'status': 'DECODED',
        'missingCriticalFields': [],
    },
    '1FTFW1E48KFA00001': {
        'vin': '1FTFW1E48KFA00001',
        'year': 2019,
        'make': 'FORD',
        'model': 'F-150',
        'trim': 'XLT',
        'bodyClass': 'Pickup',
        'vehicleType': 'TRUCK',
        'engineDisplacementL': 3.5,
        'engineCylinders': 6,
        'engineConfiguration': 'V-Engine Twin-Turbo (V6)',
        'fuelType': 'Gasoline',
        'transmissionStyle': 'Automatic',
        'transmissionSpeeds': '10-Speed (10R80)',
        'driveType': '4WD / 4x4',
        'plantCountry': 'UNITED STATES',
        'plantState': 'MICHIGAN',
        'plantCity': 'DEARBORN',
        'source': 'DEMO_SYNTHETIC',
        'status': 'DECODED',
        'missingCriticalFields': [],
    },
    '4T1B11HK5LU000001': {
        'vin': '4T1B11HK5LU000001',
        'year': 2020,
        'make': 'TOYOTA',
        'model': 'CAMRY',
        'trim': 'LE',
        'bodyClass': 'Sedan',
        'vehicleType': 'PASSENGER CAR',
        'engineDisplacementL': 2.5,
        'engineCylinders': 4,
        'engineConfiguration': 'In-Line (I4)',
        'fuelType': 'Gasoline',
        'transmissionStyle': 'Automatic',
        'transmissionSpeeds': '8-Speed (Direct Shift)',
        'driveType': 'FWD (Front-Wheel Drive)',
        'plantCountry': 'UNITED STATES',
        'plantState': 'KENTUCKY',
        'plantCity': 'GEORGETOWN',
        'source': 'DEMO_SYNTHETIC',
        'status': 'DECODED',
        'missingCriticalFields': [],
    },
}


def validate_vin(raw_vin: Any) -> Dict[str, Any]:
    """
    Validates and normalizes a 17-character VIN.
    Conforms to US 49 CFR Part 565 and ISO 3779 standards.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(raw_vin, str):
        return {
            'isValid': False,
            'normalizedVin': '',
            'errors': ['VIN must be a string of text.'],
            'warnings': [],
        }

    trimmed = raw_vin.strip()
    if not trimmed:
        return {
            'isValid': False,
            'normalizedVin': '',
            'errors': ['VIN input is empty. Please enter a 17-character VIN.'],
            'warnings': [],
        }

    normalized = trimmed.upper()

    # 1. Length validation
    if len(normalized) != 17:
        errors.append(
            f"VIN must be exactly 17 characters long. You entered {len(normalized)} character{'s' if len(normalized) != 1 else ''}."
        )

    # 2. Prohibited characters check (I, O, Q are strictly prohibited in standard 17-char VINs)
    prohibited = []
    if 'I' in normalized:
        prohibited.append("'I' (often confused with '1')")
    if 'O' in normalized:
        prohibited.append("'O' (often confused with '0')")
    if 'Q' in normalized:
        prohibited.append("'Q' (often confused with '9')")

    if prohibited:
        errors.append(
            f"Standard VINs do not contain letters I, O, or Q. Found invalid characters: {', '.join(prohibited)}."
        )

    # 3. Alphanumeric check
    legal_chars = set("0123456789ABCDEFGHJKLMNPRSTUVWXYZ")
    illegal = [c for c in normalized if c not in legal_chars]
    if illegal:
        errors.append(f"VIN contains illegal characters: {', '.join(set(illegal))}. Only letters and digits permitted.")

    if errors:
        return {
            'isValid': False,
            'normalizedVin': normalized,
            'errors': errors,
            'warnings': warnings,
        }

    # 4. Section extraction
    wmi = normalized[0:3]
    vds = normalized[3:9]
    vis = normalized[9:17]
    check_digit_actual = normalized[8]

    # 5. Check Digit Calculation (US 49 CFR Part 565 / ISO 3779)
    total_sum = 0
    for i in range(17):
        char = normalized[i]
        val = VIN_LETTER_VALUES.get(char, 0)
        weight = VIN_POSITION_WEIGHTS[i]
        total_sum += val * weight

    rem = total_sum % 11
    check_digit_calc = 'X' if rem == 10 else str(rem)
    is_check_digit_valid = (check_digit_actual == check_digit_calc)

    if not is_check_digit_valid:
        warnings.append(
            f"Check digit mismatch at position 9. Found '{check_digit_actual}', calculated '{check_digit_calc}'. "
            "This may be an international VIN or a transcription error."
        )

    return {
        'isValid': True,
        'normalizedVin': normalized,
        'errors': [],
        'warnings': warnings,
        'wmi': wmi,
        'vds': vds,
        'vis': vis,
        'checkDigitActual': check_digit_actual,
        'checkDigitCalculated': check_digit_calc,
        'isCheckDigitValid': is_check_digit_valid,
    }


def clean_val(val: Any) -> Optional[str]:
    if not val or not isinstance(val, str):
        return None
    trimmed = val.strip()
    if not trimmed or trimmed.lower() in ('not applicable', 'not available', 'none', 'null'):
        return None
    return trimmed


def parse_nhtsa_record(record: Dict[str, Any], vin: str, latency_ms: int) -> Dict[str, Any]:
    raw_year = clean_val(record.get('ModelYear'))
    try:
        year = int(raw_year) if raw_year else 0
    except ValueError:
        year = 0

    make = clean_val(record.get('Make')) or 'Unknown Make'
    model = clean_val(record.get('Model')) or 'Unknown Model'
    trim = clean_val(record.get('Trim')) or clean_val(record.get('Series'))
    body_class = clean_val(record.get('BodyClass'))
    vehicle_type = clean_val(record.get('VehicleType'))

    # Engine
    raw_disp = clean_val(record.get('DisplacementL'))
    try:
        engine_disp_l = round(float(raw_disp), 1) if raw_disp else None
    except ValueError:
        engine_disp_l = None

    raw_cyl = clean_val(record.get('EngineCylinders'))
    try:
        engine_cyl = int(raw_cyl) if raw_cyl else None
    except ValueError:
        engine_cyl = None

    engine_config = clean_val(record.get('EngineConfiguration'))
    fuel_type = clean_val(record.get('FuelTypePrimary'))

    # Transmission
    trans_style = clean_val(record.get('TransmissionStyle'))
    trans_speeds = clean_val(record.get('TransmissionSpeeds'))
    drive_type = clean_val(record.get('DriveType'))

    # Plant
    plant_country = clean_val(record.get('PlantCountry'))
    plant_state = clean_val(record.get('PlantState'))
    plant_city = clean_val(record.get('PlantCity'))

    missing_fields = []
    if not year:
        missing_fields.append('Model Year')
    if make == 'Unknown Make':
        missing_fields.append('Make')
    if model == 'Unknown Model':
        missing_fields.append('Model')
    if not engine_disp_l and not engine_cyl:
        missing_fields.append('Engine Displacement / Cylinders')
    if not trans_style:
        missing_fields.append('Transmission Type')

    status = 'DECODED' if not missing_fields else ('PARTIALLY_DECODED' if year and make != 'Unknown Make' else 'UNAVAILABLE')

    return {
        'vin': vin,
        'year': year,
        'make': make.upper(),
        'model': model.upper(),
        'trim': trim,
        'bodyClass': body_class,
        'vehicleType': vehicle_type,
        'engineDisplacementL': engine_disp_l,
        'engineCylinders': engine_cyl,
        'engineConfiguration': engine_config,
        'fuelType': fuel_type,
        'transmissionStyle': trans_style,
        'transmissionSpeeds': trans_speeds,
        'driveType': drive_type,
        'plantCountry': plant_country,
        'plantState': plant_state,
        'plantCity': plant_city,
        'source': 'NHTSA_VPIC',
        'status': status,
        'missingCriticalFields': missing_fields,
        'responseLatencyMs': latency_ms,
    }


def decode_vin(vin: str) -> Dict[str, Any]:
    """
    Decodes VIN by first validating, then calling NHTSA vPIC live API.
    Falls back gracefully to demo dictionary or partial result if offline.
    """
    val_res = validate_vin(vin)
    if not val_res['isValid']:
        return {
            'vin': vin,
            'year': 0,
            'make': 'Invalid VIN',
            'model': 'Invalid VIN',
            'status': 'UNAVAILABLE',
            'missingCriticalFields': val_res['errors'],
            'errorMessage': ' '.join(val_res['errors']),
            'responseLatencyMs': 0,
            'validation': val_res,
        }

    norm_vin = val_res['normalizedVin']
    start_time = time.time()

    # 1. Check if demo vehicle
    if norm_vin in DEMO_VEHICLES:
        demo = dict(DEMO_VEHICLES[norm_vin])
        demo['responseLatencyMs'] = int((time.time() - start_time) * 1000)
        demo['validation'] = val_res
        return demo

    # 2. Call live NHTSA vPIC API
    api_url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{norm_vin}?format=json"
    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(api_url, headers={'Accept': 'application/json', 'User-Agent': 'YardsParts-AI/2.0'})
            latency_ms = int((time.time() - start_time) * 1000)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('Results', [])
                if results and isinstance(results, list):
                    decoded = parse_nhtsa_record(results[0], norm_vin, latency_ms)
                    decoded['validation'] = val_res
                    return decoded
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[VIN Service] NHTSA API error for {norm_vin}: {e}")

    # Fallback response
    return {
        'vin': norm_vin,
        'year': 0,
        'make': 'Unavailable',
        'model': 'Unavailable',
        'trim': None,
        'bodyClass': None,
        'vehicleType': None,
        'engineDisplacementL': None,
        'engineCylinders': None,
        'engineConfiguration': None,
        'fuelType': None,
        'transmissionStyle': None,
        'transmissionSpeeds': None,
        'driveType': None,
        'plantCountry': None,
        'plantState': None,
        'plantCity': None,
        'source': 'NHTSA_VPIC',
        'status': 'UNAVAILABLE',
        'missingCriticalFields': ['Live external API connection timed out. Manual vehicle entry available.'],
        'errorMessage': 'Live NHTSA API connection could not be completed. You can select vehicle specifications manually.',
        'responseLatencyMs': latency_ms,
        'validation': val_res,
    }
