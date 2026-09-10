from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    scenario: Literal['finance', 'support']
    mode: Literal['live'] = 'live'
    source: Literal['erpnext', 'zammad']
    task: str = Field(min_length=1, max_length=6000)
    strategy: Literal['react', 'graph'] = 'react'
    @model_validator(mode='after')
    def validate_scope(self):
        if (self.scenario == 'finance' and self.source != 'erpnext') or (self.scenario == 'support' and self.source != 'zammad'):
            raise ValueError('数据源与业务场景不匹配')
        return self
