> **接手本项目的请先看**：[docs/handover/交接文档.md](docs/handover/交接文档.md)（含程序结构、数据规范、绘图层设计与待办清单，附原版参照图）

# liftcalc · 本地离线吊装计算后端

> 自用学习项目。**纯本地、无网络、无 GUI、无 AI、无商务。**
> 设计依据：`../研究/详细设计-v1.0-吊装计算后端.md`

## 它是什么

一个"工况 JSON → 计算内核 → 结果 JSON → 计算书/简图"的后端：

```
case.json ──calc──▶ result.json ──report──▶ 计算书.docx
                          └────draw────▶ 简图.svg / .dxf
```

三条铁律：

1. **单位在边界转换一次**，内核只接受 `pint.Quantity`；
2. **计算书由 `checks[]` 渲染**，渲染器不做任何计算；
3. **规范是公式来源，原程序只是对拍基准**。

## 它不是什么

不复刻原软件界面；不做在线吊车库、登录、会员、开票、支付、自动更新、云盘、地图；
不做三维渲染与 CAD 级制图；不含任何 AI 功能。

## 当前范围（只做汽车吊）

本项目**只面向汽车吊（truck crane）**。其余模块代码仍在、测试仍跑，但**当前版本不使用**，仅在需要时恢复：

| 模块 | 状态 |
|---|---|
| 汽车吊选型、负荷率、支腿反力、接地比压 | ✅ 使用中 |
| QY70K-1 原厂性能表（77 格，含起升高度） | ✅ 使用中 |
| 吊梁 `lifting.beam` | ⏸ 暂不使用 |
| 索具/卸扣 `lifting.rigging` | ⏸ 暂不使用 |
| 吊耳 `lifting.eye` | ⏸ 暂不使用 |
| 截面 `sections`、重心 `geometry` | ⏸ 暂不使用（吊梁/吊耳的依赖） |
| 平面框架 `fea`、规范校核 `codecheck` | ⏸ 暂不使用 |

> "暂不使用" = 保留实现与测试，命令行仍可调用，但不在当前产品范围内，也不进计算书模板。
> 恢复只需在文档与流程里重新纳入，不必重写。

## 当前状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| P0 | 骨架、core 三件套（units/tolerance/result）、CLI、离线测试 | ✅ 完成 |
| P1 | 数据结构与导入校验（SQLite + CSV） | ✅ 完成（示例数据） |
| P2 | 截面特性、重心/形心 | ✅ 完成 |
| P3 | 吊耳校核 + 计算书 | ✅ 完成（**限值为占位系数**） |
| P4 | 吊梁、索具 | ✅ 完成（吊梁限 4 种有闭式解的工况） |
| P5 | 吊车选型、支腿反力、接地比压 | ✅ 完成（已录入 QY70K-1 全表 77 格） |
| P6 | 简图 | ✅ 基础版（SVG + DXF） |
| P7 | 2D 框架 FEA、GB 规范校核 | ✅ 基础版（FEA 仅水平杆；未做整体稳定） |
| P8 | 接口固化（JSON Schema 导出） | ✅ 已可导出（7 种 case） |

## 环境

已在本机建好 `.venv`（继承系统 site-packages），依赖：pint、numpy、pydantic、python-docx、ezdxf、typer、pyyaml、pytest、hypothesis。

```powershell
# 项目根目录：D:\学习日志\吊装\liftcalc
$py = ".\.venv\Scripts\python.exe"
$env:PYTHONPATH = "src"
& $py -m liftcalc.cli.main --version
```

或直接用包装脚本：

```powershell
.\liftcalc.ps1 --version
.\liftcalc.ps1 selftest
```

## 快速开始

```powershell
# 1) 建库并校验
.\liftcalc.ps1 data build --pack src/liftcalc/data/pack --out data/liftcalc.sqlite
.\liftcalc.ps1 data validate --db data/liftcalc.sqlite

# 2) 算一个吊耳
.\liftcalc.ps1 calc --in cases/eye/eye-001/case.json --out out/eye-001.result.json

# 3) 出计算书（带 case 快照与附录）
.\liftcalc.ps1 report --in out/eye-001.result.json --out out/吊耳计算书.docx --case cases/eye/eye-001/case.json

# 4) 出简图
.\liftcalc.ps1 draw --in out/eye-001.result.json --out out/eye-001.svg --format svg
.\liftcalc.ps1 draw --in out/eye-001.result.json --out out/eye-001.dxf --format dxf

# 5) 与原程序对拍（把原件结果填进 oracle.json 后）
.\liftcalc.ps1 compare --case cases/eye/eye-001/case.json --oracle cases/eye/eye-001/oracle.json --out cases/eye/eye-001/diff.md

# 6) 导出 JSON Schema（给前端）
.\liftcalc.ps1 schema --out schemas
```

## 已录入的机型（数据覆盖范围）

| 机型 | 吨位 | 类型 | 配置数 | 格点 | 来源页 |
|---|---|---|---|---|---|
| QY70K-1 | 70 t | 汽车吊 | 7 | 77 | p1 |
| QY100H-3 | 100 t | 汽车吊 | 9 | 152 | p2（表）、p3（参数） |
| QY130H-1 | 130 t | 汽车吊 | 18 | 273 | p4（两张表）、p5（参数） |
| QAY200 | 200 t | 全地面 | 12 | 214 | p6（参数）、p7（表） |

**未录入**：

- **QAY300（p8 参数表 / p9 主臂性能表）**：该表 23 列，同一臂长重复 2~3 次
  （15.4\*、15.4、20.5×2、25.7×3、30.8×3、35.9×3、41.1×3、46.2×3、51.3×2、56.4、61），
  每列对应一种伸缩组合，表底用 II/III/IV/V 各节伸出百分比区分。已录入 16 列的上部数据，
  **因表没录完，脚本拒绝写 CSV，故未入库**——查询该机型会明确报"无性能数据"，不会给出半截答案。
- **QAY500（p10 主臂性能表 / p11 超起工况图）**：5 个臂长 × 4 种组合
  （X=135 t 配重、Y=185 t 配重；A=轻型杆头、B=重型杆头）≈ 940 格，另需 5 组伸缩百分比行。

> 原则：**宁可查不到，也不给错的数**。未完成的表一律不写入数据库。

## 能力反查（核心用法）

给定吊重，直接回答"能不能吊、最远多少米、多高"，代替人工查表：

```powershell
# 单机：10 t 货，QY70K-1（默认 90% 上限）
.\liftcalc.ps1 capability --model QY70K-1 --payload 10 --hook 0.616 --rigging 0.3 --out out/cap.json

# 双机：每台 80% 上限、60/40 分配、不同步系数 1.1
.\liftcalc.ps1 capability --mode dual --model QY70K-1 --second-model QY70K-1 `
    --payload 10 --hook 0.616 --rigging 0.3 --asynchronism 1.1 --out out/cap.json

# 出计算书与图（两张：能力曲线 + 吊装立面）
.\liftcalc.ps1 report --in out/cap.json --out out/反查计算书.docx
.\liftcalc.ps1 draw   --in out/cap.json --out out/图.svg --format svg
.\liftcalc.ps1 draw   --in out/cap.json --out out/图.dxf --format dxf
```

判定规则：**查表取下一档，不插值**；单机 ≤90%，双机每台 ≤80%。

## 支持的 case 类型

| kind | 用途 | 关键参数 |
|---|---|---|
| `section.props` | 截面特性 | `section.type`：`steel` / `rect` / `box` / `round` / `pipe` / `ishape` / `channel` / `t` / `angle` |
| `geometry.centroid` | 组合体形心/重心 | `solids[]`：box/cylinder/hollow_cylinder/sphere/spherical_cap/ellipsoid_head/cone_frustum/elbow/torus |
| `lifting_eye.check` | 吊耳校核 | `geometry`、`material`、`load`，可选 `weld`、`pin` |
| `lifting_beam.check` | 吊梁校核 | `beam`（支承/荷载/跨度/总荷载）、`section` 或 `properties` |
| `lifting_rigging.check` | 索具 | `load`、`sling`、可选 `rope`、`shackles`、`hooks` |
| `crane.select` | 正算负荷率 | `boom_len`、`radius`、`payload`、`capacity_table` 或数据库 |
| `crane.capability` | **能力反查**（核心） | `mode`(single/dual)、`payload`、`crane`、可选 `second`/`asynchronism`/`required_lift_height` |
| `fea.frame2d` | 水平梁有限元 | `nodes`、`elements`、`supports`、`loads` |

示例见 `cases/`。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功且结论通过 |
| 1 | 成功但结论为 FAIL（业务结果，不是错误） |
| 2 | 输入错误 |
| 3 | 数据错误 |
| 4 | 定义域错误（物理上不成立） |
| 5 | 内部错误 |

## 与设计 v1.0 的偏差

| 设计 | 实际 | 原因 |
|---|---|---|
| `report` 用 docxtpl + 模板文件 | 改为 python-docx 直接构建 | 免去二进制模板维护；渲染规则不变（仍然只填充、不计算） |
| `steel_section` 列 `Wy,Wz,iy,iz` | 改为 `Wx,Wy,rx,ry` | SQLite 列名大小写不敏感，`Iy` 与 `iy` 冲突 |
| `sections.props` 内部用 Quantity 全程 | 内部先归一为 SI 浮点 | 积分过程反复搬单位无收益；公开 API 仍是 Quantity |
| 性能表/型钢表为真实国标数据 | 仅 `DEMO-*` 示例行 | 不伪造国标数值；真实数据须由你导入并逐格核对 |

## 测试

```powershell
.\liftcalc.ps1 -m pytest    # 或
& .\.venv\Scripts\python.exe -m pytest -q
```

覆盖：解析解对照、手算样例、属性测试（hypothesis）、离线保证、依赖方向、数据单调性、端到端 CLI、对拍分级。

## 待办（按设计的分期）

1. **条文核定**：`codecheck/limits.py` 里全部系数是占位值，必须对规范原文替换——这是出正式计算书的前置条件。
2. **真实数据**：型钢库、材质库、机型性能表（每格要带 `source_ref`）。
3. **未实现的校核**：受弯/轴压整体稳定 φ、局部稳定宽厚比、螺栓连接。
4. **其余机型**：目前只录了 QY70K-1 一页（77 格），其余机型用 `data crane-template` 生成模板后转录。
4. **FEA 限制**：只支持水平杆、Euler-Bernoulli（深梁偏小）。
5. 对拍用例填充（`cases/*/oracle.json` 目前是模板）。

**选型铁律**：按原厂说明第 7 条，臂长与幅度一律**取下一档**，不插值、不外推。

详细计算流程（供专家审阅）：`../研究/吊装计算流程说明书（工程审阅版）.md` / `.docx`
程序实现对照（开发用）：`../研究/计算流程说明书-v1.0（开发用·技术对照）.md`

## 免责

本工具为个人学习与复核参考，输出**不得**作为工程实施依据。
计算书中"限值"目前为占位系数，未经规范核定。
