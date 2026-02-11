import os
from datetime import datetime, timedelta

from myelin import Myelin, MyelinOutput
from myelin.helpers.claim_examples import (
    claim_example,
    json_claim_example,
    opps_claim_example,
)
from myelin.input import (
    DiagnosisCode,
    ICDConvertOption,
    ICDConvertOptions,
    IrfPai,
    LineItem,
    Modules,
    OasisAssessment,
    OccurrenceCode,
    PoaType,
    ProcedureCode,
    Provider,
    ValueCode,
)


def run_groupers(myelin: Myelin):
    """Runs all grouper examples."""
    print("""
    ====================
    Running Grouper Examples
    ====================
    """)

    # MCE Grouper
    print("--- MCE Claim Example ---")
    mce_claim = claim_example()
    mce_claim.claimid = "MCE_CLAIM_001"
    mce_output = myelin.mce_client.process(mce_claim)
    print(mce_output.model_dump_json(indent=2))

    # MS-DRG Grouper
    print("--- MS-DRG Claim Example ---")
    drg_claim = json_claim_example()
    drg_claim.claimid = "DRG_CLAIM_001"
    drg_output = myelin.drg_client.process(drg_claim)
    print(drg_output.model_dump_json(indent=2))

    # IOCE Grouper
    print("--- IOCE Claim Example ---")
    ioce_claim = opps_claim_example()
    ioce_claim.claimid = "IOCE_CLAIM_001"
    ioce_output = myelin.ioce_client.process(ioce_claim)
    print(ioce_output.model_dump_json(indent=2))

    # IRF Grouper
    print("--- IRF Grouper Example ---")
    irf_claim = claim_example()
    irf_claim.claimid = "IRF_CLAIM_001"
    irf_claim.oasis_assessment = None
    irf_claim.billing_provider.other_id = "013025"
    irf_claim.irf_pai = IrfPai()
    irf_claim.principal_dx.code = "D61.03"
    irf_claim.admit_date = datetime(2025, 1, 1)
    irf_claim.thru_date = datetime(2025, 1, 30)
    irf_claim.patient.date_of_birth = datetime(1970, 1, 1)
    irf_claim.secondary_dxs.clear()
    irf_claim.irf_pai.assessment_system = "IRF-PAI"
    irf_claim.irf_pai.transaction_type = 1
    irf_claim.irf_pai.impairment_admit_group_code = "0012.9   "
    irf_claim.irf_pai.eating_self_admsn_cd = "06"
    irf_claim.irf_pai.oral_hygne_admsn_cd = "06"
    irf_claim.irf_pai.toileting_hygne_admsn_cd = "06"
    irf_claim.irf_pai.bathing_hygne_admsn_cd = "06"
    irf_claim.irf_pai.footwear_dressing_cd = "06"
    irf_claim.irf_pai.chair_bed_transfer_cd = "06"
    irf_claim.irf_pai.toilet_transfer_cd = "06"
    irf_claim.irf_pai.walk_10_feet_cd = "06"
    irf_claim.irf_pai.walk_50_feet_cd = "06"
    irf_claim.irf_pai.walk_150_feet_cd = "06"
    irf_claim.irf_pai.step_1_cd = "06"
    irf_claim.irf_pai.urinary_continence_cd = "0"
    irf_claim.irf_pai.bowel_continence_cd = "0"
    irf_output = myelin.irfg_client.process(irf_claim)
    print(irf_output.model_dump_json(indent=2))


def run_pricers(myelin: Myelin):
    """Runs all pricer examples."""
    print("""
    ====================
    Running Pricer Examples
    ====================
    """)

    # IPPS Pricer
    if myelin.ipps_client:
        print("--- IPPS Pricer Example ---")
        ipps_claim = claim_example()
        ipps_claim.claimid = "IPPS_CLAIM_001"
        drg_output = myelin.drg_client.process(ipps_claim)
        ipps_output, _ = myelin.ipps_client.process(ipps_claim, drg_output)
        print(ipps_output.model_dump_json(indent=2))

    # IPF Pricer
    if myelin.ipf_client:
        print("--- IPF Pricer Example ---")
        ipf_claim = claim_example()
        ipf_claim.claimid = "IPF_CLAIM_001"
        drg_output = myelin.drg_client.process(ipf_claim)
        ipf_output, _ = myelin.ipf_client.process(ipf_claim, drg_output)
        print(ipf_output.model_dump_json(indent=2))

    # LTCH Pricer
    if myelin.ltch_client:
        print("--- LTCH Pricer Example ---")
        ltch_claim = claim_example()
        if ltch_claim.billing_provider is None:
            ltch_claim.billing_provider = Provider()
        ltch_claim.claimid = "LTCH_CLAIM_001"
        ltch_claim.billing_provider.other_id = "012006"
        ltch_claim.inpatient_pxs.append(ProcedureCode(code="XW033H4"))
        ltch_claim.from_date = datetime(2023, 10, 1)
        ltch_claim.thru_date = datetime(2023, 10, 10)
        ltch_claim.admit_date = datetime(2023, 10, 1)
        ltch_claim.icd_convert = ICDConvertOptions(option=ICDConvertOption.AUTO)
        drg_output = myelin.drg_client.process(
            ltch_claim,
            drg_version="430",
            icd_converter=myelin.icd10_converter,
            poa_exempt=True,
        )
        ltch_output, _ = myelin.ltch_client.process(ltch_claim, drg_output)
        print(ltch_output.model_dump_json(indent=2))

    # Hospice Pricer
    if myelin.hospice_client:
        print("--- Hospice Pricer Example ---")
        hospice_claim = claim_example()
        hospice_claim.claimid = "HOSPICE_CLAIM_001"
        hospice_claim.bill_type = "812"
        hospice_claim.patient_status = "40"
        hospice_claim.value_codes.append(ValueCode(code="61", amount=35300.00))
        hospice_claim.value_codes.append(ValueCode(code="G8", amount=35300.00))
        hospice_claim.thru_date = datetime(2025, 7, 10)
        hospice_claim.los = 10
        hospice_claim.lines.append(
            LineItem(
                hcpcs="Q5001",
                revenue_code="0651",
                service_date=datetime(2025, 7, 1),
                units=9,
                charges=10_000.00,
            )
        )
        hospice_claim.lines.append(
            LineItem(
                hcpcs="G0299",
                revenue_code="0551",
                service_date=datetime(2025, 7, 1),
                units=3,
                charges=10_000.00,
            )
        )
        hospice_output = myelin.hospice_client.process(hospice_claim)
        print(hospice_output.model_dump_json(indent=2))

    # HHA Pricer
    if myelin.hha_client:
        print("--- HHA Pricer Example ---")
        hha_claim = claim_example()
        hha_claim.claimid = "HHA_CLAIM_001"
        hha_claim.patient.age = 65
        hha_claim.patient.address.zip = "35300"
        hha_claim.from_date = datetime(2025, 1, 1)
        hha_claim.admit_date = datetime(2025, 1, 1)
        hha_claim.thru_date = datetime(2025, 1, 30)
        hha_claim.bill_type = "329"
        hha_claim.los = 30
        hha_claim.principal_dx.code = "I10"
        hha_claim.principal_dx.poa = PoaType.Y
        hha_claim.secondary_dxs.append(DiagnosisCode(code="C50911", poa=PoaType.Y))
        hha_claim.billing_provider.other_id = "047127"
        hha_claim.lines.clear()
        hha_claim.lines.append(
            LineItem(service_date=datetime(2025, 1, 30), revenue_code="0420", units=20)
        )
        hha_claim.lines.append(
            LineItem(service_date=datetime(2025, 1, 29), revenue_code="0430", units=20)
        )
        hha_claim.lines.append(
            LineItem(service_date=datetime(2025, 1, 28), revenue_code="0440", units=20)
        )
        hha_claim.lines.append(
            LineItem(service_date=datetime(2025, 1, 27), revenue_code="0550", units=20)
        )
        hha_claim.occurrence_codes.append(
            OccurrenceCode(code="61", date=datetime(2024, 12, 15))
        )
        hha_claim.oasis_assessment = OasisAssessment()
        hha_claim.oasis_assessment.fall_risk = 1
        hha_claim.oasis_assessment.multiple_hospital_stays = 1
        hha_claim.oasis_assessment.grooming = "1"
        hhag_output = myelin.hhag_client.process(hha_claim)
        hha_pricer, _ = myelin.hha_client.process(hha_claim, hhag_output)
        myout = MyelinOutput()
        myout.hhag = hhag_output
        myout.hha = hha_pricer
        myout.to_excel("hha_pricer_output.xlsx", hha_claim)
        print(hha_pricer.model_dump_json(indent=2))

    # IRF Pricer
    if myelin.irf_client:
        print("--- IRF Pricer Example ---")
        irf_claim = claim_example()
        irf_claim.claimid = "IRF_CLAIM_001"
        irf_claim.oasis_assessment = None
        irf_claim.billing_provider.other_id = "013025"
        irf_claim.irf_pai = IrfPai()
        irf_claim.principal_dx.code = "D61.03"
        irf_claim.admit_date = datetime(2025, 1, 1)
        irf_claim.thru_date = datetime(2025, 1, 30)
        irf_claim.patient.date_of_birth = datetime(1970, 1, 1)
        irf_claim.secondary_dxs.clear()
        irf_claim.irf_pai.assessment_system = "IRF-PAI"
        irf_claim.irf_pai.transaction_type = 1
        irf_claim.irf_pai.impairment_admit_group_code = "0012.9   "
        irf_claim.irf_pai.eating_self_admsn_cd = "06"
        irf_claim.irf_pai.oral_hygne_admsn_cd = "06"
        irf_claim.irf_pai.toileting_hygne_admsn_cd = "06"
        irf_claim.irf_pai.bathing_hygne_admsn_cd = "06"
        irf_claim.irf_pai.footwear_dressing_cd = "06"
        irf_claim.irf_pai.chair_bed_transfer_cd = "06"
        irf_claim.irf_pai.toilet_transfer_cd = "06"
        irf_claim.irf_pai.walk_10_feet_cd = "06"
        irf_claim.irf_pai.walk_50_feet_cd = "06"
        irf_claim.irf_pai.walk_150_feet_cd = "06"
        irf_claim.irf_pai.step_1_cd = "06"
        irf_claim.irf_pai.urinary_continence_cd = "0"
        irf_claim.irf_pai.bowel_continence_cd = "0"
        irf_output = myelin.irfg_client.process(irf_claim)
        irf_pricer, _ = myelin.irf_client.process(irf_claim, irf_output)
        print(irf_pricer.model_dump_json(indent=2))

    # ESRD Pricer
    if myelin.esrd_client:
        print("--- ESRD Pricer Example ---")
        esrd_claim = claim_example()
        esrd_claim.claimid = "ESRD_CLAIM_001"
        esrd_claim.billing_provider.other_id = "012525"
        esrd_claim.patient.date_of_birth = datetime(1960, 1, 1)
        esrd_claim.irf_pai = None
        esrd_claim.cond_codes.clear()
        esrd_claim.cond_codes.append("74")
        esrd_claim.value_codes.clear()
        esrd_claim.value_codes.append(ValueCode(code="QH", amount=5000.00))
        start_date = datetime(2025, 1, 1)
        esrd_claim.esrd_initial_date = datetime(2025, 1, 1)
        while start_date < datetime(2025, 1, 26):
            line = LineItem()
            line.revenue_code = "0821"
            line.service_date = start_date
            esrd_claim.lines.append(line)
            start_date += timedelta(days=1)
        esrd_claim.value_codes.append(ValueCode(code="A8", amount=70.0))
        esrd_claim.value_codes.append(ValueCode(code="A9", amount=180.0))
        esrd_output, _ = myelin.esrd_client.process(esrd_claim)
        print(esrd_output.model_dump_json(indent=2))

    # FQHC Pricer
    if myelin.fqhc_client:
        print("--- FQHC Pricer Example ---")
        fqhc_claim = opps_claim_example()
        fqhc_claim.claimid = "FQHC_CLAIM_001"
        fqhc_claim.lines.clear()
        fqhc_claim.lines.append(
            LineItem(
                hcpcs="G0466",
                revenue_code="0521",
                service_date=datetime(2025, 7, 1),
                units=1,
                charges=300.00,
            )
        )
        fqhc_claim.lines.append(
            LineItem(
                hcpcs="36415",
                revenue_code="0300",
                service_date=datetime(2025, 7, 1),
                units=1,
                charges=250.00,
            )
        )
        fqhc_claim.lines.append(
            LineItem(
                hcpcs="99203",
                revenue_code="0521",
                service_date=datetime(2025, 7, 1),
                units=1,
                charges=350.00,
                modifiers=["25"],
            )
        )
        fqhc_claim.from_date = datetime(2025, 7, 1)
        fqhc_claim.thru_date = datetime(2025, 7, 1)
        fqhc_claim.bill_type = "771"
        fqhc_claim.billing_provider = Provider()
        fqhc_claim.billing_provider.address.zip = "06040"
        ioce_output = myelin.ioce_client.process(fqhc_claim)
        fqhc_output = myelin.fqhc_client.process(fqhc_claim, ioce_output)
        res = MyelinOutput()
        res.ioce = ioce_output
        res.fqhc = fqhc_output
        res.to_excel("./fqhc_pricer_output.xlsx", fqhc_claim)
        print(fqhc_output.model_dump_json(indent=2))

        # OPPS Pricer
    if myelin.opps_client:
        print("--- OPPS Pricer Example ---")
        opps_claim = opps_claim_example()
        opps_claim.claimid = "OPPS_CLAIM_001"
        ioce_output = myelin.ioce_client.process(opps_claim)
        opps_output, _ = myelin.opps_client.process(opps_claim, ioce_output)
        print(opps_output.model_dump_json(indent=2))


def run_myelin_process(myelin: Myelin):
    claim = claim_example()
    claim.modules = [Modules.MCE, Modules.MSDRG, Modules.IPPS, Modules.PSYCH]
    claim.claimid = "MYELIN_CLAIM_001"
    results = myelin.process(claim)
    results.to_excel("./myelin_process_output.xlsx")
    print(results.model_dump_json(indent=2, exclude_none=True))


def main():
    """Main function to run all examples."""
    jar_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "jars"))
    db_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "data", "myelin.db")
    )
    # Set build_db=True to create the database if it does not exist
    with Myelin(
        build_jar_dirs=True, jar_path=jar_path, db_path=db_path, build_db=False
    ) as myelin:
        run_groupers(myelin)
        run_pricers(myelin)
        # run_myelin_process(myelin)


if __name__ == "__main__":
    main()
