from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)
    scenario: Literal['finance', 'support']
    mode: Literal['fixture', 'live']
    source: Literal['sandbox', 'erpnext', 'zammad']
    task: str = Field(min_length=1, max_length=6000)
    strategy: Literal['react', 'graph'] = 'react'
    snapshot: Literal['base', 'changed', 'exception'] = 'base'
    evaluationProfile: Literal['auto', 'invariants', 'finance_full', 'support_full'] = 'auto'

    @model_validator(mode='after')
    def validate_scope(self):
        from .domain import PRESETS
        if self.mode == 'fixture' and (self.source != 'sandbox' or self.task != PRESETS[self.scenario]
                                      or self.strategy != 'react' or self.snapshot != 'base'):
            raise ValueError('离线示例仅支持原始沙箱预设任务，不可用作 Graph RSI。')
        if (self.scenario == 'finance' and self.source == 'zammad') or (self.scenario == 'support' and self.source == 'erpnext'):
            raise ValueError('数据源与业务场景不匹配')
        if self.source != 'sandbox' and self.snapshot != 'base':
            raise ValueError('快照变体只用于内置沙箱')
        if self.evaluationProfile not in ['auto', 'invariants', self.scenario + '_full']:
            raise ValueError('校验目标与场景不匹配')
        return self
