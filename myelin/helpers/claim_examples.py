from datetime import datetime

from myelin.input.claim import (
    Claim,
    DiagnosisCode,
    LineItem,
    PoaType,
    Provider,
    ValueCode,
)


def claim_example():
    claim = Claim()
    claim.principal_dx = DiagnosisCode(code="A021", poa=PoaType.Y)
    claim.admit_dx = DiagnosisCode(code="A021", poa=PoaType.Y)
    claim.patient_status = "01"
    claim.patient.age = 65
    claim.patient.sex = "M"
    claim.admit_date = datetime(2025, 7, 1)
    claim.from_date = datetime(2025, 7, 1)
    claim.thru_date = datetime(2025, 7, 10)
    claim.los = 9
    claim.secondary_dxs.append(DiagnosisCode(code="I82411", poa=PoaType.N))
    claim.billing_provider = Provider()
    claim.billing_provider.other_id = "010001"
    return claim


def opps_claim_example():
    claim = Claim()
    claim.claimid = "OPPS_EXAMPLE_001"
    claim.principal_dx = DiagnosisCode(code="S3215XK", poa=PoaType.U)
    claim.patient_status = "01"
    claim.patient.age = 65
    claim.patient.sex = "M"
    claim.from_date = datetime(2026, 1, 1)
    claim.thru_date = datetime(2026, 1, 2)
    claim.bill_type = "131"
    claim.billing_provider = Provider()
    claim.billing_provider.other_id = "010001"

    claim.secondary_dxs.append(DiagnosisCode(code="S72044D", poa=PoaType.N))
    claim.secondary_dxs.append(DiagnosisCode(code="17210", poa=PoaType.Y))
    claim.cond_codes = ["15", "25"]
    claim.value_codes = [ValueCode(code="59", amount=43.02)]

    claim.lines.append(
        LineItem(
            service_date=datetime(2026, 1, 1),
            revenue_code="9999",
            hcpcs="27279",
            units=1,
            charges=435.00,
        )
    )

    claim.lines.append(
        LineItem(
            service_date=datetime(2026, 1, 1),
            revenue_code="0360",
            hcpcs="29305",
            modifiers=["22", "ZZ"],
            units=1,
            charges=191.78,
        )
    )

    claim.lines.append(
        LineItem(
            service_date=datetime(2026, 1, 1),
            revenue_code="0610",
            hcpcs="72196",
            units=1,
            charges=140.67,
        )
    )

    claim.lines.append(
        LineItem(
            service_date=datetime(2026, 1, 1),
            revenue_code="0610",
            hcpcs="72197",
            units=1,
            charges=600.25,
        )
    )

    claim.lines.append(
        LineItem(
            service_date=datetime(2026, 1, 1),
            revenue_code="0610",
            hcpcs="2010F",
            units=2,
            charges=45.98,
        )
    )

    return claim


def json_claim_example():
    claim_json = {
        "from_date": "2025-07-01",
        "thru_date": "2025-07-10",
        "los": 9,
        "patient_status": "01",
        "admit_date": "2025-07-01",
        "principal_dx": {"code": "A021", "poa": "Y", "dx_type": 1},
        "admit_dx": {"code": "A021", "poa": "Y", "dx_type": 1},
        "secondary_dxs": [{"code": "I82411", "poa": "N", "dx_type": "SECONDARY"}],
        "patient": {"age": 65, "sex": "M"},
    }

    return Claim.model_validate(claim_json)
