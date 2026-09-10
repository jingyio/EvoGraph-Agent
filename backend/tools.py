from copy import deepcopy
from dataclasses import dataclass, field
import inspect
import json
from typing import Callable, Any
from jsonschema import Draft7Validator


@dataclass
class ToolContext:
    run: dict
    evidence: set = field(default_factory=set)


@dataclass
class Tool:
    name: str
    description: str
    effect: str
    parameters: dict
    handler: Callable
    origin: Any = None
    outputs: Any = None

    def __post_init__(self):
        Draft7Validator.check_schema(self.parameters)
        self.validator = Draft7Validator(self.parameters)

    def card(self):
        value = {'name': self.name, 'description': self.description, 'effect': self.effect, 'parameters': self.parameters}
        if self.origin:
            value['origin'] = self.origin
        if self.outputs:
            value['outputs'] = list(self.outputs)
        return deepcopy(value)

    async def execute(self, args, context):
        errors = sorted(self.validator.iter_errors(args), key=lambda error: str(list(error.path)))
        if errors:
            # Do not echo attacker-controlled record values or server secrets.
            raise ValueError('; '.join(f"{'.'.join(map(str, e.path)) or 'arguments'}: schema {e.validator} validation failed" for e in errors[:5]))
        result = self.handler(args, context)
        if inspect.isawaitable(result):
            result = await result
        return deepcopy(result)


def object_schema(properties=None, required=None):
    return {'type': 'object', 'properties': properties or {}, 'required': list(properties or {}) if required is None else required, 'additionalProperties': False}
