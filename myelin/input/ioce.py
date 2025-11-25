from pydantic import BaseModel, Field


class IoceOverride(BaseModel):
    edit_bypass_list: list[str] = Field(default_factory=list)
    apc: str = ""
    status_indicator: str = ""
    payment_indicator: str = ""
    discounting_formula: str = ""
    rejection_denial_flag: str = ""
    packaging_flag: str = ""
    payment_adjustment_flag_01: str = ""
    payment_method_flag: str = ""
    payment_adjustment_flag_02: str = ""
