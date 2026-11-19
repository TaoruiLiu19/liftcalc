"""Case 契约模型（设计 §7）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Units(BaseModel):
    model_config = ConfigDict(extra="forbid")

    length: Literal["mm", "cm", "m"] = "mm"
    force: Literal["N", "kN", "t"] = "kN"
    stress: Literal["MPa", "Pa"] = "MPa"
    mass: Literal["kg", "t"] = "kg"
    angle: Literal["deg", "rad"] = "deg"


class CaseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str = ""
    part: str = ""
    author: str = ""
    date: str = ""
    notes: str = ""


class CaseEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    units: Units = Field(default_factory=Units)
    meta: CaseMeta = Field(default_factory=CaseMeta)


class SectionSpec(BaseModel):
    """截面定义；按 type 取用相应字段。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["steel", "rect", "box", "round", "pipe", "ishape", "channel", "t", "angle"]
    family: str | None = None
    designation: str | None = None
    b: float | None = None
    h: float | None = None
    t: float | None = None
    tw: float | None = None
    tf: float | None = None
    d_outer: float | None = None
    d_inner: float | None = None
    b_long: float | None = None
    b_short: float | None = None


class SectionCase(CaseEnvelope):
    kind: Literal["section.props"]
    section: SectionSpec


class SolidSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "box", "cylinder", "hollow_cylinder", "sphere",
        "spherical_cap", "ellipsoid_head", "cone_frustum", "elbow", "torus",
    ]
    dims: dict[str, float]
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    density: float | None = None


class CentroidCase(CaseEnvelope):
    kind: Literal["geometry.centroid"]
    solids: list[SolidSpec]


class EyeGeometryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plate_t: float
    plate_b: float
    plate_h: float
    hole_d: float
    hole_edge: float


class EyeLoadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design: float
    dynamic_factor: float = 1.0
    angle_deg: float = 0.0


class MaterialModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: str = "Q355B"
    fy: float | None = None


class WeldModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leg: float
    length: float
    electrode: str = "E43"


class PinModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diameter: float


class EyeCase(CaseEnvelope):
    kind: Literal["lifting_eye.check"]
    geometry: EyeGeometryModel
    material: MaterialModel = Field(default_factory=MaterialModel)
    load: EyeLoadModel
    weld: WeldModel | None = None
    pin: PinModel | None = None


class BeamProperties(BaseModel):
    """显式给出截面特性时的单位：I 为 mm⁴、W 为 mm³、腹板面积为 mm²。"""

    model_config = ConfigDict(extra="forbid")

    inertia: float
    section_modulus: float
    web_area: float | None = None


class BeamLoadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    support: Literal["simply_supported", "cantilever"]
    load_type: Literal["udl", "point_mid", "point_tip"]
    span: float
    total: float
    deflection_ratio: float = 400.0


class BeamCase(CaseEnvelope):
    kind: Literal["lifting_beam.check"]
    beam: BeamLoadModel
    section: SectionSpec | None = None
    properties: BeamProperties | None = None
    material: MaterialModel = Field(default_factory=MaterialModel)


class RiggingLoadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: float


class SlingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branches: int = 4
    angle_deg: float = 0.0


class RopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diameter: float
    rated_strength: float = 1770.0
    k_prime: float = 0.356
    safety_factor: float = 6.0


class SelectionOptionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    capacity: float


class RiggingCase(CaseEnvelope):
    kind: Literal["lifting_rigging.check"]
    load: RiggingLoadModel
    sling: SlingModel = Field(default_factory=SlingModel)
    rope: RopeModel | None = None
    shackles: list[SelectionOptionModel] | None = None
    hooks: list[SelectionOptionModel] | None = None


class CapacityPointModel(BaseModel):
    """性能表一行：臂长 / 幅度 / 额定起重量（t）。"""

    model_config = ConfigDict(extra="forbid")

    boom_len: float
    radius: float
    rated_load: float


class CraneModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: str | None = None
    model: str | None = None
    config: str | None = None
    boom_len: float | None = None


class OutriggerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lx: float
    ly: float
    ex: float = 0.0
    ey: float = 0.0
    plate_area: float | None = None


class CraneCase(CaseEnvelope):
    kind: Literal["crane.select"]
    boom_len: float
    radius: float
    payload: float
    machine_mass: float = 0.0
    hook_mass: float = 0.0
    rigging: float = 0.0
    dynamic_factor: float = 1.1
    ratio_limit: float = 0.9
    jib_installed: bool = False
    region: Literal["360", "侧方", "后方", "前方"] = "360"
    fifth_outrigger: bool = True
    capacity_table: list[CapacityPointModel] | None = None
    crane: CraneModelSpec | None = None
    outrigger: OutriggerModel | None = None


class CraneRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: str = "徐工"
    model: str


class CapabilityCase(CaseEnvelope):
    """能力反查：给定吊重，问能不能吊、最远多少米、多高。

    单机负荷率上限默认 90%，双机每台默认 80%。
    """

    kind: Literal["crane.capability"]
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    target_radius: float | None = Field(default=None, gt=0)
    config: str | None = None
    mode: Literal["single", "dual"] = "single"
    payload: float
    hook_mass: float = 0.0
    rigging: float = 0.0
    dynamic_factor: float = 1.1
    limit: float | None = Field(default=None, gt=0, le=1)
    crane: CraneRef
    second: CraneRef | None = None
    left_share: float = 0.6
    asynchronism: float = 1.0
    required_lift_height: float | None = Field(default=None, ge=0)
    # 以下三项只影响立面图的示意尺寸，不参与能力反查
    load_width_m: float = Field(default=3.2, gt=0)
    load_height_m: float = Field(default=3.8, gt=0)
    clearance_m: float = Field(default=1.0, ge=0)


class FrameNodeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class FrameElementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    i: int
    j: int
    e_modulus: float = 206000.0
    area: float
    inertia: float
    udl: float = 0.0


class FrameSupportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: int
    fix_ux: bool = False
    fix_uy: bool = True
    fix_rz: bool = False


class FrameNodalLoadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: int
    fy: float = 0.0
    mz: float = 0.0


class FrameCase(CaseEnvelope):
    """单位约定：x/y 为 mm，E 为 MPa，A 为 mm²，I 为 mm⁴，udl 为 N/mm，fy 为 N，mz 为 N·mm。"""

    kind: Literal["fea.frame2d"]
    nodes: list[FrameNodeModel]
    elements: list[FrameElementModel]
    supports: list[FrameSupportModel]
    loads: list[FrameNodalLoadModel] = Field(default_factory=list)


CASE_MODELS: dict[str, type[CaseEnvelope]] = {
    "section.props": SectionCase,
    "geometry.centroid": CentroidCase,
    "lifting_eye.check": EyeCase,
    "lifting_beam.check": BeamCase,
    "lifting_rigging.check": RiggingCase,
    "crane.select": CraneCase,
    "crane.capability": CapabilityCase,
    "fea.frame2d": FrameCase,
}
