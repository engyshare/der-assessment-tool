from typing import Any

from pydantic import BaseModel, Field


class DERConfig(BaseModel):
    tag: str
    params: dict[str, Any] = Field(default_factory=dict)


class LoadConfig(BaseModel):
    annual_kwh: float | None = None
    profile: list[float] | None = None


class ContractConfig(BaseModel):
    structure: str


class RegulationConfig(BaseModel):
    pass


class ModelConfig(BaseModel):
    name: str
    resources: list[DERConfig]
    common_load: LoadConfig | None = None
    contract: ContractConfig | None = None
    regulation: RegulationConfig | None = None
