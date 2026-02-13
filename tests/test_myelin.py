from myelin import OPSFProvider
from myelin import IPSFProvider
import os
import tempfile
from datetime import datetime

import pytest

from myelin import Myelin
from myelin.helpers.claim_examples import (
    claim_example,
    json_claim_example,
    opps_claim_example,
)
from myelin.input import (
    DiagnosisCode,
    IoceOverride,
    IrfPai,
    LineItem,
    Modules,
    OasisAssessment,
    PoaType,
    ValueCode,
)


def project_root_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def jars_dir():
    return os.path.join(project_root_dir(), "jars")


def pricers_dir():
    return os.path.join(jars_dir(), "pricers")


def _file_exists(dir_path, name_substring):
    if not os.path.exists(dir_path):
        return False
    try:
        for f in os.listdir(dir_path):
            if f.endswith(".jar") and name_substring in f:
                return True
    except Exception:
        return False
    return False


def base_jars_present():
    d = jars_dir()
    # Require core runtime deps and at least one of the main components
    required_substrings = [
        "gfc-base-api",
        "protobuf-java",
        "slf4j-",
    ]
    return all(_file_exists(d, s) for s in required_substrings)


def pricer_available(name_substring):
    return _file_exists(pricers_dir(), name_substring)


@pytest.fixture(scope="module")
def myelin_or_skip():
    if not base_jars_present():
        pytest.skip(
            "Required runtime JARs not found in ./jars. Populate real CMS jars to run integration tests."
        )

    jar_path = jars_dir()
    db_path = os.path.join(project_root_dir(), "data", "myelin.db")

    myelin = Myelin(
        build_jar_dirs=False, jar_path=jar_path, db_path=db_path, build_db=False
    )
    myelin.setup_clients()
    try:
        yield myelin
    finally:
        myelin.cleanup()


def test_mce_process_example_claim(myelin_or_skip):
    claim = claim_example()
    output = myelin_or_skip.mce_client.process(claim)
    assert hasattr(output, "model_dump"), "MCE output should be a pydantic model"


def test_msdrg_process_json_claim(myelin_or_skip):
    claim = json_claim_example()
    output = myelin_or_skip.drg_client.process(claim)
    # Basic invariants
    assert hasattr(output, "model_dump"), "MS-DRG output should be a pydantic model"


def test_ioce_process_opps_claim(myelin_or_skip):
    claim = opps_claim_example()
    output = myelin_or_skip.ioce_client.process(claim)
    assert hasattr(output, "model_dump"), "IOCE output should be a pydantic model"


def test_ioce_with_override(myelin_or_skip: Myelin):
    claim = opps_claim_example()
    claim.lines[1].override = IoceOverride()
    claim.lines[1].override.status_indicator = "C"
    output = myelin_or_skip.ioce_client.process(claim)
    assert output.line_item_list[1].status_indicator == "C", (
        "IOCE should apply override to status indicator"
    )


def test_ipps_pricer_if_available(myelin_or_skip):
    if not pricer_available("ipps-pricer"):
        pytest.skip("IPPS pricer jar not present in ./jars/pricers")
    if myelin_or_skip.ipps_client is None:
        pytest.skip("IPPS client not initialized")

    claim = claim_example()
    assert myelin_or_skip.ipps_client.db is not None
    ipsf_provider = IPSFProvider()
    ipsf_provider.from_claim(claim, myelin_or_skip.ipps_client.db)
    drg_output = myelin_or_skip.drg_client.process(claim)
    output, _ = myelin_or_skip.ipps_client.process(claim, ipsf_provider, drg_output)
    assert hasattr(output, "model_dump")


def test_myelin_process(myelin_or_skip):
    claim = claim_example()
    claim.modules = [Modules.MCE, Modules.MSDRG, Modules.IPPS]
    output = myelin_or_skip.process(claim)
    assert hasattr(output, "model_dump"), "Myelin output should be a pydantic model"


def test_opps_pricer_if_available(myelin_or_skip):
    if not pricer_available("opps-pricer"):
        pytest.skip("OPPS pricer jar not present in ./jars/pricers")
    if myelin_or_skip.opps_client is None:
        pytest.skip("OPPS client not initialized")

    claim = opps_claim_example()
    assert myelin_or_skip.opps_client.db is not None
    ipsf_provider = OPSFProvider()
    ipsf_provider.from_claim(claim, myelin_or_skip.opps_client.db)
    ioce_output = myelin_or_skip.ioce_client.process(claim)
    output, _ = myelin_or_skip.opps_client.process(claim, ipsf_provider, ioce_output)
    assert hasattr(output, "model_dump")


def test_ipf_pricer_if_available(myelin_or_skip):
    if not pricer_available("ipf-pricer"):
        pytest.skip("IPF pricer jar not present in ./jars/pricers")
    if myelin_or_skip.ipf_client is None:
        pytest.skip("IPF client not initialized")

    claim = claim_example()
    assert myelin_or_skip.ipf_client.db is not None
    ipsf_provider = IPSFProvider()
    ipsf_provider.from_claim(claim, myelin_or_skip.ipf_client.db)
    drg_output = myelin_or_skip.drg_client.process(claim)
    output, _ = myelin_or_skip.ipf_client.process(claim, ipsf_provider, drg_output)
    assert hasattr(output, "model_dump")


def test_ltch_pricer_if_available(myelin_or_skip):
    if not pricer_available("ltch-pricer"):
        pytest.skip("LTCH pricer jar not present in ./jars/pricers")
    if myelin_or_skip.ltch_client is None:
        pytest.skip("LTCH client not initialized")

    claim = claim_example()
    # Example parity: LTCH requires special provider id in example
    claim.billing_provider.other_id = "012006"
    assert myelin_or_skip.ltch_client.db is not None
    ipsf_provider = IPSFProvider()
    ipsf_provider.from_claim(claim, myelin_or_skip.ltch_client.db)
    drg_output = myelin_or_skip.drg_client.process(claim)
    output, _ = myelin_or_skip.ltch_client.process(claim, ipsf_provider, drg_output)
    assert hasattr(output, "model_dump")


def test_hospice_pricer_if_available(myelin_or_skip):
    if not pricer_available("hospice-pricer"):
        pytest.skip("Hospice pricer jar not present in ./jars/pricers")
    if myelin_or_skip.hospice_client is None:
        pytest.skip("Hospice client not initialized")

    claim = claim_example()
    claim.bill_type = "812"
    claim.patient_status = "40"
    claim.value_codes.append(ValueCode(code="61", amount=35300.00))
    claim.value_codes.append(ValueCode(code="G8", amount=35300.00))
    claim.thru_date = datetime(2025, 7, 10)
    claim.los = 10
    claim.lines.append(
        LineItem(
            hcpcs="Q5001",
            revenue_code="0651",
            service_date=datetime(2025, 7, 1),
            units=9,
            charges=10_000.00,
        )
    )
    claim.lines.append(
        LineItem(
            hcpcs="G0299",
            revenue_code="0551",
            service_date=datetime(2025, 7, 1),
            units=3,
            charges=10_000.00,
        )
    )

    output = myelin_or_skip.hospice_client.process(claim)
    assert hasattr(output, "model_dump")


def test_snf_pricer_if_available(myelin_or_skip):
    if not pricer_available("snf-pricer"):
        pytest.skip("SNF pricer jar not present in ./jars/pricers")
    if myelin_or_skip.snf_client is None:
        pytest.skip("SNF client not initialized")

    claim = claim_example()
    claim.admit_date = datetime(2025, 1, 1)
    claim.from_date = datetime(2025, 1, 1)
    claim.thru_date = datetime(2025, 1, 20)
    claim.los = 20
    claim.bill_type = "327"
    claim.patient_status = "01"
    claim.principal_dx.code = "B20"
    claim.secondary_dxs[0].code = "C50911"
    claim.lines.clear()
    claim.lines.append(LineItem())
    claim.lines[0].revenue_code = "0022"
    claim.lines[0].hcpcs = "ABAC1"
    claim.lines[0].service_date = datetime(2025, 1, 1)
    claim.lines[0].units = 20
    assert myelin_or_skip.snf_client.db is not None
    ipsf_provider = IPSFProvider()
    ipsf_provider.from_claim(claim, myelin_or_skip.snf_client.db)
    output, _ = myelin_or_skip.snf_client.process(claim, ipsf_provider)
    assert hasattr(output, "model_dump")


def test_irf_pricer_if_availabler(myelin_or_skip):
    if not pricer_available("irf-pricer"):
        pytest.skip("IRF pricer jar not present in ./jars/pricers")
    if myelin_or_skip.irf_client is None:
        pytest.skip("IRF client not initialized")

    claim = claim_example()
    claim.billing_provider.other_id = "013025"
    claim.los = 20
    claim.non_covered_days = 0
    claim.irf_pai = IrfPai()
    claim.principal_dx.code = "D61.03"
    claim.admit_date = datetime(2025, 1, 1)
    claim.thru_date = datetime(2025, 1, 30)
    claim.patient.date_of_birth = datetime(1970, 1, 1)
    claim.secondary_dxs.clear()
    claim.irf_pai.assessment_system = "IRF-PAI"
    claim.irf_pai.transaction_type = 1
    claim.irf_pai.impairment_admit_group_code = "0012.9   "
    claim.irf_pai.eating_self_admsn_cd = "06"
    claim.irf_pai.oral_hygne_admsn_cd = "06"
    claim.irf_pai.toileting_hygne_admsn_cd = "06"
    claim.irf_pai.bathing_hygne_admsn_cd = "06"
    claim.irf_pai.footwear_dressing_cd = "06"
    claim.irf_pai.chair_bed_transfer_cd = "06"
    claim.irf_pai.toilet_transfer_cd = "06"
    claim.irf_pai.walk_10_feet_cd = "06"
    claim.irf_pai.walk_50_feet_cd = "06"
    claim.irf_pai.walk_150_feet_cd = "06"
    claim.irf_pai.step_1_cd = "06"
    claim.irf_pai.urinary_continence_cd = "0"
    claim.irf_pai.bowel_continence_cd = "0"
    cmg_output = myelin_or_skip.irfg_client.process(claim)
    assert myelin_or_skip.irf_client.db is not None
    ipsf_provider = IPSFProvider()
    ipsf_provider.from_claim(claim, myelin_or_skip.irf_client.db)
    irf_output, _ = myelin_or_skip.irf_client.process(claim, ipsf_provider, cmg_output)
    assert hasattr(irf_output, "model_dump")


def test_hha_pricer_if_available(myelin_or_skip):
    if not pricer_available("hha-pricer"):
        pytest.skip("HHA pricer jar not present in ./jars/pricers")
    if myelin_or_skip.hha_client is None:
        pytest.skip("HHA client not initialized")
    claim = claim_example()
    claim.patient.age = 65
    claim.from_date = datetime(2025, 1, 1)
    claim.thru_date = datetime(2025, 1, 31)
    claim.los = 30
    claim.principal_dx.code = "I10"
    claim.principal_dx.poa = PoaType.Y
    claim.secondary_dxs.append(DiagnosisCode(code="C50911", poa=PoaType.Y))
    claim.lines.append(
        LineItem(service_date=datetime(2025, 1, 1), revenue_code="0420", units=20)
    )
    claim.lines.append(
        LineItem(service_date=datetime(2025, 1, 1), revenue_code="0430", units=20)
    )
    claim.lines.append(
        LineItem(service_date=datetime(2025, 1, 1), revenue_code="0440", units=20)
    )
    claim.lines.append(
        LineItem(service_date=datetime(2025, 1, 1), revenue_code="0550", units=20)
    )
    claim.oasis_assessment = OasisAssessment()
    claim.oasis_assessment.fall_risk = True
    claim.oasis_assessment.multiple_hospital_stays = True
    claim.oasis_assessment.multiple_ed_visits = True
    claim.oasis_assessment.mental_behavior_risk = False
    claim.oasis_assessment.compliance_risk = True
    claim.oasis_assessment.five_or_more_meds = True
    claim.oasis_assessment.exhaustion = False
    claim.oasis_assessment.other_risk = False
    claim.oasis_assessment.none_of_above = False
    claim.oasis_assessment.weight_loss = False
    claim.oasis_assessment.grooming = "1"
    claim.oasis_assessment.dress_upper = "2"
    claim.oasis_assessment.dress_lower = "2"
    claim.oasis_assessment.bathing = "0"
    claim.oasis_assessment.toileting = "1"
    claim.oasis_assessment.transferring = "2"
    claim.oasis_assessment.ambulation = "3"
    assert myelin_or_skip.hha_client.db is not None 
    ipsf_provider = IPSFProvider()
    ipsf_provider.from_claim(claim, myelin_or_skip.hha_client.db)
    hhag_output = myelin_or_skip.hhag_client.process(claim)
    hha_pricer, _ = myelin_or_skip.hha_client.process(claim, ipsf_provider, hhag_output)
    assert hasattr(hha_pricer, "model_dump")


def test_hhag_grouper(myelin_or_skip):
    claim = claim_example()
    claim.patient.age = 65
    claim.from_date = datetime(2025, 1, 1)
    claim.thru_date = datetime(2025, 1, 31)
    claim.los = 30
    claim.principal_dx.code = "I10"
    claim.principal_dx.poa = PoaType.Y
    claim.secondary_dxs.append(DiagnosisCode(code="C50911", poa=PoaType.Y))
    claim.oasis_assessment = OasisAssessment()
    claim.oasis_assessment.fall_risk = True
    claim.oasis_assessment.multiple_hospital_stays = True
    claim.oasis_assessment.multiple_ed_visits = True
    claim.oasis_assessment.mental_behavior_risk = False
    claim.oasis_assessment.compliance_risk = True
    claim.oasis_assessment.five_or_more_meds = True
    claim.oasis_assessment.exhaustion = False
    claim.oasis_assessment.other_risk = False
    claim.oasis_assessment.none_of_above = False
    claim.oasis_assessment.weight_loss = False
    claim.oasis_assessment.grooming = "1"
    claim.oasis_assessment.dress_upper = "2"
    claim.oasis_assessment.dress_lower = "2"
    claim.oasis_assessment.bathing = "0"
    claim.oasis_assessment.toileting = "1"
    claim.oasis_assessment.transferring = "2"
    claim.oasis_assessment.ambulation = "3"
    output = myelin_or_skip.hhag_client.process(claim)
    assert hasattr(output, "model_dump")


def test_ipps_extract_resource_file(myelin_or_skip):
    """Test extracting resource files from IPPS pricer JAR across multiple years."""
    if not pricer_available("ipps-pricer"):
        pytest.skip("IPPS pricer jar not present in ./jars/pricers")
    if myelin_or_skip.ipps_client is None:
        pytest.skip("IPPS client not initialized")

    # Create a temporary directory for extractions
    with tempfile.TemporaryDirectory() as extract_dir:
        extracted_files = []
        attempted_files = []
        start = 2020

        # Try to extract drgstable files from 2020 to current year
        while start < datetime.now().year:
            year = start + 1
            filename = f"drgstable-{year}.csv"
            attempted_files.append(filename)

            try:
                myelin_or_skip.ipps_client.extract_resource_file(filename, extract_dir)

                # Verify the file was extracted to the correct location
                extracted_path = os.path.join(extract_dir, filename)
                assert os.path.exists(extracted_path), (
                    f"{filename} should exist in {extract_dir}"
                )
                assert os.path.getsize(extracted_path) > 0, (
                    f"{filename} should not be empty"
                )

                extracted_files.append(filename)
                start = year
            except FileNotFoundError:
                # Expected for years where the resource doesn't exist
                start += 1
            except Exception as e:
                pytest.fail(f"Unexpected error extracting resource file: {e}")

        # Ensure we attempted to extract at least one file and all attempts succeeded
        assert len(attempted_files) > 0, (
            "Should have attempted to extract at least one file"
        )
        assert len(extracted_files) == len(attempted_files), (
            f"Should have extracted {len(attempted_files)} files but got {len(extracted_files)}"
        )

    # Test error handling for non-existent resource
    with pytest.raises(FileNotFoundError, match="not found in that JAR"):
        myelin_or_skip.ipps_client.extract_resource_file("nonexistent-file.csv")


def test_ipf_extract_resource_file(myelin_or_skip):
    """Test extracting resource files from IPF pricer JAR across multiple years."""
    if not pricer_available("ipf-pricer"):
        pytest.skip("IPF pricer jar not present in ./jars/pricers")
    if myelin_or_skip.ipf_client is None:
        pytest.skip("IPF client not initialized")

    # Create a temporary directory for extractions
    with tempfile.TemporaryDirectory() as extract_dir:
        extracted_files = []
        attempted_files = []
        start = 2020

        # Try to extract drg files from 2020 to current year
        while start < datetime.now().year:
            year = start + 1
            filename = f"drg-{year}.csv"
            attempted_files.append(filename)

            try:
                myelin_or_skip.ipf_client.extract_resource_file(filename, extract_dir)

                # Verify the file was extracted to the correct location
                extracted_path = os.path.join(extract_dir, filename)
                assert os.path.exists(extracted_path), (
                    f"{filename} should exist in {extract_dir}"
                )
                assert os.path.getsize(extracted_path) > 0, (
                    f"{filename} should not be empty"
                )

                extracted_files.append(filename)
                start = year
            except FileNotFoundError:
                # Expected for years where the resource doesn't exist
                start += 1
            except Exception as e:
                pytest.fail(f"Unexpected error extracting resource file: {e}")

        # Ensure we attempted to extract at least one file and all attempts succeeded
        assert len(attempted_files) > 0, (
            "Should have attempted to extract at least one file"
        )
        assert len(extracted_files) == len(attempted_files), (
            f"Should have extracted {len(attempted_files)} files but got {len(extracted_files)}"
        )

    # Test error handling for non-existent resource
    with pytest.raises(FileNotFoundError, match="not found in that JAR"):
        myelin_or_skip.ipf_client.extract_resource_file("nonexistent-file.csv")


def test_ltch_extract_resource_file(myelin_or_skip):
    """Test extracting resource files from LTCH pricer JAR across multiple years."""
    if not pricer_available("ltch-pricer"):
        pytest.skip("LTCH pricer jar not present in ./jars/pricers")
    if myelin_or_skip.ltch_client is None:
        pytest.skip("LTCH client not initialized")

    # Create a temporary directory for extractions
    with tempfile.TemporaryDirectory() as extract_dir:
        extracted_files = []
        attempted_files = []
        start = 2020

        # Try to extract ltdrgstable files from 2020 to current year
        while start < datetime.now().year:
            year = start + 1
            filename = f"ltdrgstable-{year}.csv"
            attempted_files.append(filename)

            try:
                myelin_or_skip.ltch_client.extract_resource_file(filename, extract_dir)

                # Verify the file was extracted to the correct location
                extracted_path = os.path.join(extract_dir, filename)
                assert os.path.exists(extracted_path), (
                    f"{filename} should exist in {extract_dir}"
                )
                assert os.path.getsize(extracted_path) > 0, (
                    f"{filename} should not be empty"
                )

                extracted_files.append(filename)
                start = year
            except FileNotFoundError:
                # Expected for years where the resource doesn't exist
                start += 1
            except Exception as e:
                pytest.fail(f"Unexpected error extracting resource file: {e}")

        # Ensure we attempted to extract at least one file and all attempts succeeded
        assert len(attempted_files) > 0, (
            "Should have attempted to extract at least one file"
        )
        assert len(extracted_files) == len(attempted_files), (
            f"Should have extracted {len(attempted_files)} files but got {len(extracted_files)}"
        )

    # Test error handling for non-existent resource
    with pytest.raises(FileNotFoundError, match="not found in that JAR"):
        myelin_or_skip.ltch_client.extract_resource_file("nonexistent-file.csv")
