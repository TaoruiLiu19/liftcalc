"""组合体形心。

设计 §8.2：组合体按 x̄ = Σ(Vᵢ·xᵢ)/ΣVᵢ 合成；密度可选，缺省只出几何形心。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from liftcalc.core.errors import NonPositiveDimensionError
from liftcalc.core.units import Q
from liftcalc.geometry.solids import Solid


@dataclass(frozen=True)
class AssemblyItem:
    solid: Solid
    offset: tuple[Q, Q, Q] = (Q(0, "m"), Q(0, "m"), Q(0, "m"))
    density: Q | None = None  # kg/m³


@dataclass(frozen=True)
class AssemblyResult:
    volume: Q
    mass: Q | None
    centroid: tuple[Q, Q, Q]
    geometric_centroid: tuple[Q, Q, Q] = (Q(0, "m"), Q(0, "m"), Q(0, "m"))


def assembly_centroid(items: Sequence[AssemblyItem]) -> AssemblyResult:
    if not items:
        raise NonPositiveDimensionError("组合体至少需要一个构件")

    total_volume = 0.0
    moments = [0.0, 0.0, 0.0]
    total_mass = 0.0
    mass_moments = [0.0, 0.0, 0.0]
    for item in items:
        volume = float(item.solid.volume.to("m**3").magnitude)
        if volume <= 0:
            raise NonPositiveDimensionError(f"构件 {item.solid.name} 体积不为正")
        cx, cy, cz = (float(coordinate.to("m").magnitude) for coordinate in item.solid.centroid)
        ox, oy, oz = (float(offset.to("m").magnitude) for offset in item.offset)
        total_volume += volume
        moments[0] += volume * (cx + ox)
        moments[1] += volume * (cy + oy)
        moments[2] += volume * (cz + oz)

        if item.density is not None:
            density = float(item.density.to("kg/m**3").magnitude)
            mass = volume * density
            total_mass += mass
            mass_moments[0] += mass * (cx + ox)
            mass_moments[1] += mass * (cy + oy)
            mass_moments[2] += mass * (cz + oz)

    geometric = tuple(Q(moment / total_volume, "m") for moment in moments)
    mass: Q | None = None
    # 给了密度就按质量求重心，否则退回几何形心
    centroid = geometric
    if total_mass > 0:
        mass = Q(total_mass, "kg")
        centroid = tuple(Q(moment / total_mass, "m") for moment in mass_moments)

    return AssemblyResult(
        volume=Q(total_volume, "m**3"),
        mass=mass,
        centroid=centroid,  # type: ignore[arg-type]
        geometric_centroid=geometric,  # type: ignore[arg-type]
    )


def mass_centroid(items: Sequence[AssemblyItem]) -> AssemblyResult:
    """按质量求重心；所有构件必须给出密度。"""
    if any(item.density is None for item in items):
        raise NonPositiveDimensionError("按质量求重心时，每个构件都必须给出密度")
    return assembly_centroid(items)
