# liftcalc · 汽车吊单机校核与双机上轨

liftcalc 是 Windows 吊装计算工作台。单机模式按车型、臂长和工作幅度查原厂主臂性能表，核对负荷率与钩高。双机模式面向列车上轨，按吊点和重心计算两端分载，搜索两台固定吊机的站位与吊物转向路径，标出沿途的超限和待核区间。

[启动工作台](#启动工作台) · [单机吊装](#单机吊装) · [双机上轨](#双机上轨) · [算例验证](#算例验证) · [机型与数据](#机型与数据) · [命令行](#命令行)

![工作台首页，可选择单机吊装或双机上轨](docs/handover/assets/mode-home.png)

## 启动工作台

在装有 **Python 3.12 或更高版本**的 Windows 电脑上，下载并解压完整仓库。在仓库根目录打开 PowerShell，首次使用执行以下命令，安装项目及桌面依赖。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[desktop]"
.\启动单机工作台.cmd
```

以后双击 `启动单机工作台.cmd` 即可进入首页，选择单机或双机。首次安装依赖需要联网；之后界面、车型数据和 DXF 查看器均可离线使用。桌面端每次从随仓库提供的数据包建立临时数据库。

窗口默认最大化，右上角可切换浅色或深色。默认使用 pywebview 和 WebView2；原生宿主启动失败时，程序会尝试 Edge 或 Chrome 独立窗口。启动异常可查看 `%TEMP%\liftcalc-error.log`。

## 单机吊装

1. **吊物与重心**　输入吊件质量、长宽高、重心偏移及吊点内缩。固定轴测图显示四个吊点，修改重心的水平位置后，吊钩随之移到重心正上方。
2. **车型与工况**　选择实车型号、配置和主钩，录入索具重量。可指定幅度，也可反查满足输入条件的最远表档。结果页显示采用的表档、额载、负荷率及钩高资料。

**索具捆扎后高度**取拉紧后吊点平面至钩中心的竖直距离。若现场从吊物底面量起，请在界面选底面基准，再填包含吊物的总高。例如，吊物高 3 m、顶面至钩中心 2 m、底面离地 1 m，所需钩高为 **6 m**。单机也支持按吊点几何估算索高。

**怎样读结果**　单机计算荷载为吊件质量 + 钩重 + 索具质量 × 动载系数。工作幅度介于两档时，按同一配置和臂长中较大的幅度档核载。若要求核对指定位置的钩高，缺少该位置的高度数据会列为资料不足。换算四索张力时，工作台同时给出名义值和每根索的静力范围；各根索的上限可能出现在不同的受力状态。

点击 A3 立面图可放大，按住左键拖动，滚轮缩放。单机支持导出 DXF、SVG、PNG 和 Word 计算书。只读 CAD 查看器可打开本次导出的 DXF 或 32 MB 以内的本地 DXF。[单机结果截图](docs/handover/assets/refract-result.png) · [CAD 查看器截图](docs/handover/assets/refract-cad.png)

## 双机上轨

| 步骤 | 操作与结果 |
|---|---|
| 1 · 吊物与吊点 | 在车体局部 XY 图上放置吊点 A、B 和重心 G，输入两侧索具捆扎后高度。调整任一吊点、重心或质量，即可查看两机各自分担的吨数和百分比。水平悬吊要求 G 的水平投影落在 AB 线段内部，位于中点时两侧各分担 50%。 |
| 2–3 · A 机、B 机工况 | 分别选择车型、固定臂长、配置与主钩。填写含支腿的矩形占地；选车时可查看两台车的预排位置。 |
| 4 · 转向与场地 | 指定起吊与落位姿态、障碍和要求的平面净距。默认自动搜索站位及中间转向路径；已有实测站位时可锁定机位，继续搜索吊物路径。 |
| 5 · 图纸与校核 | 同窗查看静力分析图和俯视轨迹图，可分别放大或导出 DXF。静力图用于读两端分载、力臂、索高和钩高；轨迹回放用于定位限制区间及对应障碍或机位。 |

每台吊机的查表总吊重为 **（该端分载质量 + 本侧索具质量）× 输入放大系数 + 本侧钩重**。软件逐段检查工作幅度所跨表档、可用钩高和二维扫掠净距。默认负荷率限值为单机 90%、双机每台 80%，属于项目判定参数。

出现已知超载或相交时，结果标为超限。缺少全段钩高资料或保守净距下界不足以证明满足要求时，该项标为待核。搜索得到的轨迹需结合实车允许回转区域、地基、三维干涉及动作时序另行复核。转向模型采用水平刚体和竖向吊力，适用于悬空转运阶段。

[吊点与重心编辑页](docs/handover/assets/transfer-points.png) · [静力图 DXF](docs/handover/assets/01-static.dxf) · [轨迹图 DXF](docs/handover/assets/02-trajectory.dxf) · [12 m 列车演示输入](cases/rail-transfer-demo.json)

在 A、B 机工况页可分别填写允许最大工作幅度。规划器同时比较预设路径与平面位姿格网上自由平移、转动的路径。同等校核状态和问题数下，先压低两机较大的峰值幅度上界，再比较另一台的上界。结果页显示两侧峰值上界及其所在区间。对于窄通道，程序会尝试更小的转角和平移步长，并在接近要求净距的区间加密校核。对已通过的自动路线，程序还会调整转向时机，在保持每台车峰值幅度和最高负荷率上界的条件下增加净距。可复算 [6 t 列车、机位锁定、净距至少 1 m 的工况](cases/rail-transfer-1m-clearance.json)。模型与实算数据见[双机幅度优化对照](cases/README.md#双机幅度优化对照)。

自动站位会比较对齐和错位布局，也会按圆形障碍与支腿矩形分别移动两台车的候选机位；起吊后两机固定。[自动避障站位算例](cases/rail-transfer-auto-stagger.json)

列车可以斜着穿过两机空隙。轨迹图在形心首次穿过两回转中心连线的位置叠画车体，分别标注车体纵轴和形心行进方向相对连线法向的角度。[斜穿算例](cases/rail-transfer-oblique.json)

## 算例验证

| 验证对象 | 输入与可复算的结果 |
|---|---|
| 单机跨幅度档 | 三一 STC1100T7，38.5 t 全配重，侧后方作业，总吊重 34 t。10.00 m 时可选 36.7 m 臂、额载 39 t，负荷率 **87.18%**。10.01 m 向外取 12 m 档，适用臂长中最大额载降至 32.3 t，触发超限。 |
| 双机转向中段超载 | 构造两机对称吊 50 t 的转向路径，B 机总吊重 28.565 t、臂长 36.7 m。起止幅度均为 9.883 m，负荷率 **73.24%**；中途幅度增至 10.100 m，负荷率升至 **89.27%**，工作台检出中段超过 80% 限值。 |
| 偏心四吊点 | ITI 图 3 给出总重 8,000 lbf、吊点纵距 10 ft、重心距 A/B 端 3 ft。复算的竖向反力范围为 A、B 各 **1,600–4,000 lbf**，C、D 各 **0–2,400 lbf**，与原题逐点一致。 |

武汉体育中心钢桁架的双机设计负荷率复算为 **85.798%**，论文为 85.8%。另有盾构双机翻身设计荷载、四组工业模块起落点回转角，以及机身从两台汽车吊之间穿过的现场分载对照。[论文与现场工程复算](cases/README.md#论文与现场工程复算)

算例文档列出原厂表页、教材答案、解析几何题、误差和适用条件。双机中段超载例使用厂家额载与自设站位，检验的是转动中的跨档判定。[算例与原始资料](cases/README.md) · [可执行回归用例](tests/test_reference_lifts.py)

## 机型与数据

随库有主臂性能数据的车型共 **16 款、245 组配置、4,063 个格点**，含徐工及三一的 15 款汽车吊，以及徐工 QAY200 全地面起重机。车型吨级从 25 t 到 300 t。查表时须匹配实车配重、支腿状态、伸缩组合、允许作业方位及所装主钩。

<details>
<summary>展开车型清单、格点数及原厂表页</summary>

| 机型 | 吨位 | 类型 | 配置 | 格点 |
|---|---|---|---|---|
| QY70K-1 | 70 t | 汽车吊 | 7 | 77 |
| QY100H-3 | 100 t | 汽车吊 | 9 | 152 |
| QY130H-1 | 130 t | 汽车吊 | 18（配重 30/20 t 两套） | 273 |
| QAY200 | 200 t | 全地面 | 12 | 214 |
| XCT25L5_Y | 25 t | 汽车吊 | 15（固定全配重 5.8 t） | 192 |
| XCT60_Y | 60 t | 汽车吊 | 15（固定 5.5 t + 活动 1 t） | 204 |
| XCT100_1 | 100 t | 汽车吊 | 29（全配重 45 t，按伸缩码分列） | 432 |
| 三一 STC500 | 50 t | 汽车吊 | 11（固定全配重 3.5 t） | 183 |
| 三一 STC550C5 | 55 t | 汽车吊 | 15（固定 5.2 t + 活动 2.3 t） | 216 |
| 三一 STC750 | 75 t | 汽车吊 | 9（固定 4.5 t + 活动 2 t） | 154 |
| 三一 STC1100T7 | 110 t | 汽车吊 | 14（全配重 38.5 t，侧后方） | 242 |
| 三一 STC1200T7 | 120 t | 汽车吊 | 14（巴西缓速器版，全配重 36.2 t） | 234 |
| 三一 STC1600T7 | 160 t | 汽车吊 | 28（全配重 52 t，常规位和全后移各 14 组） | 463 |
| 三一 STC2000C8-8 | 200 t | 汽车吊 | 14（2024 款，全配重 61 t） | 281 |
| 三一 STC2400C8PHEV | 240 t | 汽车吊 | 18（全配重 71 t，后移 R 位） | 394 |
| 三一 STC3000C8-8 | 300 t | 汽车吊 | 17（全配重 73.5 t，普通主臂） | 352 |
| **合计** | | | **245** | **4063** |

下列六款采用全配重、主臂、支腿全伸、360° 工况。页码从 PDF 封面起算，每个入库格点带有对应页的链接。

| 机型 | 支腿跨距（纵 × 横）及条件 | 格点幅度 | 原厂性能表 |
|---|---|---|---|
| XCT25L5_Y | 5.23 × 6.4 m，第五支腿支好 | 3–32 m | [规格书 PDF 第 14–15 页](https://www.wme.cn/xcmg-xct25l5y/xcmg-xct25l5y.pdf#page=14) |
| XCT60_Y | 6.1 × 7.1 m，第五支腿支好 | 3–34 m | [规格书 PDF 第 9–10 页](https://cdn2.antbuildz.com/images/801140e237a2c5fee8df6b44b.pdf#page=9) |
| XCT100_1 | 8.45 × 7.9 m，按表底五位伸缩码选择 | 3–54 m | [徐工欧洲规格书 PDF 第 15–16 页](https://xcmg-eu.com/wp-content/uploads/2021/12/XCT100.pdf#page=15) |
| STC500 | 6 × 7.2 m，11.5–43 m 主臂，按第 2 节至顶节伸出率选择 | 3–34 m | [三一规格书 PDF 第 7 页左表](https://sanyglobal-img.sany.com.cn/product/picture_album/20200929/STC500-13%20Broch-224154.pdf#page=7) |
| STC550C5 | 6.05 × 7.4 m，第五支腿支好，11.6–45 m 主臂 | 3–34 m | [三一规格书 PDF 第 10 页](https://sanyglobal-img.sany.com.cn/sanyglobal-com-prd/prod/20251226/Sany-brochure-STC550C5-20240329-EN-CN_200143.pdf#page=10) |
| STC750 | 6.1 × 7.6 m，11.8–45 m 主臂，按伸缩组合选择 | 3–32 m | [三一规格书 PDF 第 7 页右表](https://www.sanyglobal.com/all/d/file/p/2017-03-02/af0f448e4762f6053306cb254e378409.pdf#page=7) |

这六款主臂表的空格、逐格钩高和仰角均留空。表中的幅度范围汇总了该机型所有伸缩组合，每个组合只能查到原表列出的幅度。

计算时按实车核对吊钩自重、额定能力及倍率。XCT100_1 标配 75 t 主钩自重 0.530 t，选配 130 t 主钩自重 1.017 t。STC500 的主钩有 0.610 t 和 0.555 t 两种，STC750 的两种主钩分别为 0.800 t（75 t 钩）和 0.320 t（30 t 钩）。STC550C5 规格书的吊钩参数表与性能表备注所列自重有出入，库中主副钩自重均留空，按实车填写。

**110–300 t 三一汽车吊的查表条件**

下表六款均采用支腿全伸的主臂表。工作台列有对应车型的原厂主钩，可按实车选择。各格点均可回到对应的 PDF 页。带星号的特殊额定值和原表空格均未录入。

| 车型 | 适用范围和转录说明 | 厂家原表 |
|---|---|---|
| STC1100T7 | 页脚限定侧方及后方作业。13.9 m 主臂的 3 m 和 3.5 m 两格有星号。 | [第 10 页](https://sanyglobal-img.sany.com.cn/product/picture_album/20211027/Sany_crane-brochure_STC1100T7-150757.pdf#page=10) |
| STC1200T7 | 巴西缓速器版，360°。2.5 m 幅度的 120 t 格点需辅助装置。第 8 页尺寸图与第 9 页规格表对支腿纵横顺序的标注相反，数据库的纵横跨距留空。 | [第 16 页](https://sanyglobal-img.sany.com.cn/sanyglobal-com-prd/prod/20251226/Sany-brochure-STC1200T7-Brazil-Retarder-20231018-EN-CN_195416.pdf#page=16) |
| STC1600T7 | 360°，按实际配重位置选表。带星号的格点需提高倍率并使用指定吊钩。 | [全后移第 23 页](https://sanyglobal-img.sany.com.cn/sanyglobal-com-prd/prod/20251230/Sany-brochure-STC1600T7-20230606-EN-CN_220415.pdf#page=23)、[常规位第 25 页](https://sanyglobal-img.sany.com.cn/sanyglobal-com-prd/prod/20251230/Sany-brochure-STC1600T7-20230606-EN-CN_220415.pdf#page=25) |
| STC2000C8-8 | 2024 款，360°。第 7 页左表的 21.0 m、39.8 m 与第 6 页曲线标注不一致，另有两列同标 59.4 m。四列均暂缺。 | [第 7 页左表](https://cos-www.sanygroup.com/2024/03/26/STC2000C8-8%2824%E6%AC%BE%29%E5%8D%95%E8%A1%8C%E6%9C%AC%E4%B8%AD%E6%96%87%E7%89%8820240129.pdf#page=7) |
| STC2400C8PHEV | 360°，配重后移，按 2024 年 5 月手册封面的型号入库。产品页写作 STC2400C8-8PHEV。 | [第 11 页](https://cos-www.sanygroup.com/2024/07/03/STC2400C8PHEV%E5%8D%95%E8%A1%8C%E6%9C%AC%E4%B8%AD%E6%96%87%E7%89%8820240528%281%29.pdf#page=11) |
| STC3000C8-8 | 360°。双星号表示能力等级，单星号要求辅助装置。40 m 主臂在 6 m、6.5 m 幅度的表值依次为 83.9 t 和 87.0 t，该列暂缺。普通主臂已收录的最大表值为 124.8 t。 | [第 11 页](https://cos-www.sanygroup.com/2024/07/19/STC3000C8-8%E5%8D%95%E8%A1%8C%E6%9C%AC%E4%B8%AD%E6%96%87%E7%89%8820240711.pdf#page=11) |

</details>

QAY300、QAY500 尚缺可用的主臂性能数据。遇到“缺吊钩自重”时，请先选择已安装的主钩；库中缺少该钩时，按实车铭牌填写自重，并复核吊钩额载和穿绳倍率。例如 800 kg 对应 0.8 t。[车型数据源](src/liftcalc/data/pack/crane)

## 命令行

在仓库根目录运行。CLI 默认读取随仓库提供的 `data/liftcalc.sqlite`。下面的例子用徐工 QY70K-1 的 25.98 m 主臂，在 10 m 幅度核吊件 10 t，要求钩高 6 m。

```powershell
.\liftcalc.ps1 capability --model QY70K-1 --config "主臂25.98m" --target-radius 10 --required-height 6 --payload 10 --hook 0.616 --rigging 0.3 --out out\cap.json
.\liftcalc.ps1 report --in out\cap.json --out out\吊装计算书.docx
.\liftcalc.ps1 draw --in out\cap.json --out out\cap.dxf --format dxf
```

按默认索具动载系数 1.1，总吊重为 **10.946 t**。该表格点额载 **15.5 t**、钩高 **24.43 m**，负荷率 **70.62%**。本例的 `draw` 命令生成三份 DXF，`out\cap-2.dxf` 是吊装立面图。省略 `--target-radius` 可反查最远可用幅度。更多参数见 `.\liftcalc.ps1 capability --help`。

CLI 的 `capability --mode dual` 用于一个给定工况的双机分载；连续转向轨迹使用桌面首页的“双机上轨”。批处理可读取 `$LASTEXITCODE`。对于 `capability`，**0 表示满足，1 表示不满足，6 表示资料不足**。这三种结果在传入 `--out` 时均写入 JSON。其余错误码为 2（输入或参数）、3（数据库或基础数据）、4（超出定义域）和 5（内部或启动错误）。

## 开发与复验

计算内核使用 Python，工作台使用 Vue 3、TypeScript 和 Vite，只读 CAD 预览使用 MLightCAD。前端构建产物已随仓库提供。

```powershell
# 安装测试依赖并复跑对照算例
.\.venv\Scripts\python.exe -m pip install -e ".[desktop,dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_reference_lifts.py

# 变更前端后，在 frontend 目录构建
cd frontend
pnpm install --frozen-lockfile
pnpm run build
```

修改机型数据时，在 `src/liftcalc/data/pack/crane` 维护车型及性能表 CSV，同臂长的不同伸缩组合用 `config` 区分。在仓库根目录重建并校验 CLI 数据库。

```powershell
.\liftcalc.ps1 data build --pack src/liftcalc/data/pack --out data/liftcalc.sqlite
.\liftcalc.ps1 data validate --db data/liftcalc.sqlite
```

<details>
<summary>工程案例与研究资料</summary>

- 铁路设备抬吊实例记录了机位布置、配重干涉与回转时序。[Synergy Lifting 工程案例](https://synergy-lifting.co.uk/project/loading-60000kg-rail-machines-onto-transport-for-export/)
- 双机协同路径研究讨论吊物平衡和沿途避碰。[Cai 等，双机路径规划](https://archive.ymsc.tsinghua.edu.cn/pacm_download/53/9490-dual-crane.pdf)
- Duerr 研究了四点吊装中索长误差、吊索刚度和吊物刚度对分载的影响。实测捆扎高度可以确定钩高，实际四索张力还受各根索长偏差影响。[Engineering Journal，1989](https://ej.aisc.org/index.php/engj/article/view/524)
- 张育诚将起重能力和场地障碍纳入可行位姿，再用概率路线图搜索单机及双机的吊装路径。[台湾大学硕士论文，2010](https://tdr.lib.ntu.edu.tw/bitstream/123456789/10692/1/ntu-99-1.pdf)
- 双机吊运细长梁的缩比试验研究了两根悬挂绳长度不同时的摆动响应，可作为后续动态模型的参考。文中的悬挂绳长度与本软件输入的钩下索具净高是两种测量量。[Mechanical Systems and Signal Processing，2019](https://www.sciencedirect.com/science/article/abs/pii/S0888327019301165)
- 钱森等建立多机协作动力学模型，并比较改进蚁群算法在栅格场地中的路径长度和搜索效率，可用于设计路径规划对照试验。[机械工程学报，2022](https://qikan.cmes.org/jxgcxb/CN/10.3901/JME.2022.07.020)

</details>

[交接文档](docs/handover/交接文档.md) · [计算内核](src/liftcalc) · [工作台前端](frontend/src) · [前端构建产物](src/liftcalc/dusk_static)
