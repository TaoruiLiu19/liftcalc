"""错误类型与错误码（见设计 §14.2）。

约定：
- 2xxx 输入错误：字段缺失、类型错、单位错
- 3xxx 数据错误：库表缺项、数据不一致
- 4xxx 定义域错误：输入合法但物理/几何上不成立
- 5xxx 内部错误：不该发生的分支
"""

from __future__ import annotations

from typing import Any


class LiftcalcError(Exception):
    code = "LC-0000"

    def __init__(self, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.message = message
        self.detail: dict[str, Any] = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class InputError(LiftcalcError):
    code = "LC-2000"


class UnknownKindError(InputError):
    code = "LC-2001"


class UnitInputError(InputError):
    code = "LC-2002"


class DataError(LiftcalcError):
    code = "LC-3000"


class NotFoundError(DataError):
    code = "LC-3001"


class DomainError(LiftcalcError):
    code = "LC-4000"


class DegenerateGeometryError(DomainError):
    code = "LC-4001"


class NonPositiveAreaError(DomainError):
    code = "LC-4002"


class NonPositiveDimensionError(DomainError):
    code = "LC-4003"


class InfeasibleSectionError(DomainError):
    code = "LC-4010"


class OutOfTableError(DomainError):
    code = "LC-4030"


class SingularSystemError(DomainError):
    code = "LC-4040"


class InternalError(LiftcalcError):
    code = "LC-5000"
