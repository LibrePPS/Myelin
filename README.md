# Myelin

Myelin is a comprehensive Python toolkit for interacting with key components of the US healthcare reimbursement system. It provides a unified, developer-friendly interface to official CMS (Centers for Medicare & Medicaid Services) software, enabling programmatic access to:

- **MS-DRG Grouper:** Assigns inpatient claims to Diagnosis-Related Groups (DRGs) for payment determination.
- **HHA Grouper (HHAG):** Groups home health claims based on clinical and functional status, using OASIS data.
- **IRF Grouper (IRFG):** Groups inpatient rehabilitation facility claims.
- **MCE Editor:** Validates inpatient claims against the Medicare Code Editor (MCE) to ensure clinical coherence.
- **IOCE Editor:** Processes outpatient claims through the Integrated Outpatient Code Editor (IOCE) to assign Ambulatory Payment Classifications (APCs).
- **IPPS Pricer:** Calculates reimbursement for inpatient claims under the Inpatient Prospective Payment System (IPPS).
- **OPPS Pricer:** Calculates reimbursement for outpatient claims under the Outpatient Prospective Payment System (OPPS).
- **IPF Pricer:** Calculates reimbursement for inpatient claims under the Inpatient Psychiatric Facility Prospective Payment System (IPF PPS).
- **IRF Pricer:** Calculates reimbursement for inpatient rehabilitation facility claims.
- **LTCH Pricer:** Calculates reimbursement for long-term care hospital claims.
- **SNF Pricer:** Calculates reimbursement for skilled nursing facility claims.
- **HHA Pricer:** Calculates reimbursement for home health claims.
- **Hospice Pricer:** Calculates reimbursement for hospice claims.
- **ESRD Pricer:** Calculates reimbursement for End-Stage Renal Disease claims.
- **FQHC Pricer:** Calculates reimbursement for Federally Qualified Health Center claims.

Built on top of the official Java-based CMS tools, Myelin uses `jpype` to create a seamless bridge to Python, allowing developers, analysts, and researchers to integrate these critical healthcare components into their workflows for automation, analytics, and research.

## What is Myelin?

In the complex world of healthcare reimbursement, claims are processed through a series of steps to determine how much a provider should be paid. Myelin simplifies this process by providing a single, easy-to-use Python library that handles the most important of these steps:

- **Grouping:** Assigning a standardized code (like a DRG or APC) that categorizes the patient's episode of care.
- **Editing:** Checking the claim for errors or inconsistencies based on clinical and coding rules.
- **Pricing:** Calculating the final payment amount based on the assigned group and other factors.

By wrapping the official CMS software, Myelin ensures that you are using the same logic as Medicare and other major payers, providing a high degree of accuracy and reliability.

## Features

- **Unified Interface:** A single, consistent API for interacting with multiple CMS tools.
- **Flexible Claim Construction:** Easily create and modify claims using Pydantic data models.
- **Support for Multiple Editors and Groupers:** Includes interfaces for the MCE (inpatient), IOCE (outpatient), HHA (home health), and IRF (inpatient rehabilitation) grouper/editors.
- **Comprehensive Pricer Suite:** Full-featured pricers for IPPS, OPPS, IPF, IRF, LTCH, SNF, HHA, Hospice, ESRD, and FQHC.
- **Extensible:** The underlying architecture makes it easy to add new components or customize existing ones.
- **Example Scripts:** Get up and running quickly with a comprehensive set of examples in the `example.py` file.

## Requirements

- Python 3.10+
- Java (JRE/JDK, Java 17+ is recommended)
- JPype1 (Python-Java bridge)
- DRG, MCE, IOCE, and Pricer Java JAR files (provided in the `jars/` directory or downloadable)

## Installation

1.  **Clone this repository:**
    ```bash
    git clone https://github.com/LibrePPS/myelin.git
    cd Myelin
    ```
2.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    or, if you use [uv](https://github.com/astral-sh/uv):
    ```bash
    uv sync
    ```
    dev dependencies:
    ```bash
    uv sync --group dev
    ```
3.  **Ensure Java is installed and available in your PATH.**
    - Check with: `java -version`

## Dev Env Setup
To get proper type checking in your IDE you will need to generate stubs for all the java classes.
```bash
cd myelin
uv run create_stubs.py
```
**Note:** This process relies on the presence of the JAR files that are downloaded at runtime. Run the [example](#usage)
first then generate the stubs.

## Testing
```bash
pytest tests/
```

# Linting & Formatting
Before commiting run [ruff](https://docs.astral.sh/ruff/) tooling.

Linter:
```bash
ruff check .
```
Autofix what you can, manually fix the remaining errors.

Import Sorting and Formatter:
```bash
ruff check --select I --fix
ruff format
```


## Setup

Myelin is designed to handle the setup and configuration of the environment for you. By default, it will:
- Create the `jars/` and `data/` directories if they don't exist.
- Download the latest CMS grouper and editor JARs.
- Download the latest CMS pricer JARs.
- Create and populate the necessary SQLite databases for the pricers.

To get started, simply instantiate the `Myelin` class:
```python
from myelin import Myelin

myelin = Myelin(build_jar_dirs=True, build_db=True)
```

## Usage

The `example.py` script provides a comprehensive set of examples for using all the features of myelin. Here's a brief overview of how to use each component through the `Myelin` class:

```bash
uv run example.py
```

### MS-DRG Grouper

The `DrgClient` is used to process inpatient claims and assign a DRG.

```python
from myelin import Myelin
from myelin.helpers.test_examples import claim_example

myelin = Myelin(build_jar_dirs=True, build_db=True)

claim = claim_example()
drg_output = myelin.drg_client.process(claim)
print(drg_output.model_dump_json(indent=2))
```

### HHA Grouper (HHAG)

The `HhagClient` is used to process home health claims. This grouper has a special requirement for OASIS assessment data, which can be provided in `oasis` object class on the `Claim` object.

The following variables are supported within the `oasis` class:
- **Risk flags (boolean/int):** `fall_risk`, `weight_loss`, `multiple_hospital_stays`, `multiple_ed_visits`, `mental_behavior_risk`, `compliance_risk`, `five_or_more_meds`, `exhaustion`, `other_risk`, `none_of_above`.
- **Functional status (string codes):** `grooming`, `dress_upper`, `dress_lower`, `bathing`, `toileting`, `transferring`, `ambulation`.

If the `"oasis"` key is not provided, a set of defaults will be used.

```python
from myelin import Myelin
from myelin.helpers.test_examples import claim_example
from datetime import datetime

myelin = Myelin(build_jar_dirs=True, build_db=True)

claim = claim_example()
claim.from_date = datetime(2025, 1, 1)
claim.thru_date = datetime(2025, 1, 31)

# Add OASIS data
claim.oasis_assessment = OasisAssessment()
claim.oasis_assessment.fall_risk = 1
claim.oasis_assessment.multiple_hospital_stays = 1
claim.oasis_assessment.grooming = "1"

hhag_output = myelin.hhag_client.process(claim)
print(hhag_output.model_dump_json(indent=2))
```

### IRF Grouper (IRFG)

The `IrfgClient` is used to process inpatient rehabilitation facility claims.

```python
from myelin import Myelin
from myelin.helpers.test_examples import claim_example

myelin = Myelin(build_jar_dirs=True, build_db=True)

claim = claim_example()
irfg_output = myelin.irfg_client.process(claim)
print(irfg_output.model_dump_json(indent=2))
```

### MCE Editor

The `MceClient` is used to validate inpatient claims against the MCE edits.

```python
from myelin import Myelin
from myelin.helpers.test_examples import claim_example

myelin = Myelin(build_jar_dirs=True, build_db=True)

claim = claim_example()
mce_output = myelin.mce_client.process(claim)
print(mce_output.model_dump_json(indent=2))
```

### IOCE Editor

The `IoceClient` is used to process outpatient claims through the IOCE editor.

```python
from myelin import Myelin
from myelin.helpers.test_examples import opps_claim_example

myelin = Myelin(build_jar_dirs=True, build_db=True)

opps_claim = opps_claim_example()
ioce_output = myelin.ioce_client.process(opps_claim)
print(ioce_output.model_dump_json(indent=2))
```

### Inpatient & Long-Term Care Pricers

This suite of pricers calculates reimbursement for various inpatient and long-term care settings. The IPPS, IPF, and LTCH pricers require the output from the `DrgClient`, while the SNF pricer operates directly on the claim.

- **`IppsClient`:** For standard inpatient claims (IPPS).
- **`IpfClient`:** For inpatient psychiatric facility (IPF) claims.
- **`LtchClient`:** For long-term care hospital (LTCH) claims.
- **`SnfClient`:** For skilled nursing facility (SNF) claims.
- **`IrfClient`:** For inpatient rehabilitation facility (IRF) claims.

```python
from myelin import Myelin
from myelin.helpers.test_examples import claim_example
from datetime import datetime

myelin = Myelin(build_jar_dirs=True, build_db=True)

claim = claim_example()
drg_output = myelin.drg_client.process(claim)
irfg_output = myelin.irfg_client.process(claim)

# IPPS Pricer
ipps_output = myelin.ipps_client.process(claim, drg_output)
print("IPPS Output:", ipps_output.model_dump_json(indent=2))

# IPF Pricer
ipf_output = myelin.ipf_client.process(claim, drg_output)
print("IPF Output:", ipf_output.model_dump_json(indent=2))

# LTCH Pricer
# LTCH may require specific provider IDs or other claim modifications
ltch_claim = claim_example()
ltch_claim.billing_provider.other_id = "012006"
ltch_drg_output = myelin.drg_client.process(ltch_claim)
ltch_output = myelin.ltch_client.process(ltch_claim, ltch_drg_output)
print("LTCH Output:", ltch_output.model_dump_json(indent=2))

# SNF Pricer
# SNF claims have specific requirements for bill type, DX, etc.
snf_claim = claim_example()
snf_claim.admit_date = datetime(2025, 1, 1)
snf_claim.from_date = datetime(2025, 1, 1)
snf_claim.thru_date = datetime(2025, 1, 20)
snf_claim.bill_type = "327"
snf_claim.principal_dx.code = "B20"
snf_output = myelin.snf_client.process(snf_claim)
print("SNF Output:", snf_output.model_dump_json(indent=2))

# IRF Pricer
irf_output = myelin.irf_client.process(claim, irfg_output)
print("IRF Output:", irf_output.model_dump_json(indent=2))
```

### Outpatient Pricers

- **`OppsClient`:** For standard outpatient claims (OPPS).
- **`HhaClient`:** For home health agency (HHA) claims.
- **`EsrdClient`:** For end-stage renal disease (ESRD) claims.
- **`FqhcClient`:** For federally qualified health center (FQHC) claims.

### OPPS Pricer

The `OppsClient` is used to calculate the reimbursement for an outpatient claim. It requires the output from the `IoceClient`.

```python
from myelin import Myelin
from myelin.helpers.test_examples import opps_claim_example

myelin = Myelin(build_jar_dirs=True, build_db=True)

opps_claim = opps_claim_example()
ioce_output = myelin.ioce_client.process(opps_claim)
opps_output = myelin.opps_client.process(opps_claim, ioce_output)
print(opps_output.model_dump_json(indent=2))
```

### Hospice Pricer

The `HospiceClient` calculates reimbursement for hospice claims. It operates directly on the claim object.

```python
from myelin import Myelin
from myelin.helpers.test_examples import claim_example
from myelin.input import LineItem, ValueCode
from datetime import datetime

myelin = Myelin(build_jar_dirs=True, build_db=True)

claim = claim_example()
claim.bill_type = "812"
claim.patient_status = "40"
claim.value_codes.append(ValueCode(code="61", amount=35300.00))
claim.thru_date = datetime(2025, 7, 10)
claim.lines.append(
    LineItem(
        hcpcs="Q5001",
        revenue_code="0651",
        service_date=datetime(2025, 7, 1),
        units=9
    )
)

hospice_output = myelin.hospice_client.process(claim)
print(hospice_output.model_dump_json(indent=2))
```

## Project Structure

- `myelin/client.py` – Main class for interacting with the CMS tools and example usage.
- `msdrg/` – MS-DRG Grouper client and output models
- `hhag/` – HHA Grouper client and output models
- `irfg/` – IRF Grouper client and output models
- `mce/` – MCE Editor client and output models
- `ioce/` – IOCE Editor client and output models
- `pricers/` – Clients for all pricers (IPPS, OPPS, IPF, IRF, LTCH, SNF, HHA, Hospice, ESRD, FQHC)
- `input/` – Pydantic models for claims and related data
- `helpers/` – Utility scripts, including the CMS downloader
- `jars/` – Directory for Java JAR files (not tracked in git)
- `data/` – Directory for SQLite databases (not tracked in git)

## Troubleshooting

- **JVM Not Started:** Ensure Java is installed and the JAR path is correct.
- **Missing JARs:** The `Myelin` class should handle this automatically. If not, ensure the `jars/` directory is writable.
- **JPype Errors:** Make sure JPype1 is installed and matches your Python version.
- **Pricer Errors:** Ensure you have created the databases by running `Myelin(build_db=True)`.

## License

MIT License. See [LICENSE](LICENSE).
