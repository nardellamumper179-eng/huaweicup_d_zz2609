# Huawei Cup D 题：山区洪涝灾害下无人机运输与通信协同优化

本仓库整理问题一至问题四的模型代码、计算说明和结果文件。

## 当前结果

### 问题一

问题一研究单服务区直接往返条件下的货箱组批，综合考虑载重、体积、返航安全余量、架次、能耗和累计作业时间。

### 问题二

问题二最终采用 **ALNS + CP-SAT** 混合方法：

- ALNS 调整货箱组批、拆分和合并结构；
- CP-SAT 在给定组批和路线下精确安排机型、实体无人机、共享电池和开始时刻；
- 最终方案为 21 架次，80 个货箱全部按期送达，加权延误为 0，最后返航时刻为 7718.4 s，总能耗为 64.2234 kWh。

### 问题三

问题三在问题二方案上加入连续通信约束，并联合调整运输时刻与中继任务：

- 使用 30 m DEM 判断链路视线遮挡，按 1 秒间隔检查运输全过程通信状态；
- 采用候选点搜索确定中央、东部、西部和北部 4 个中继悬停点；
- 2 架中继无人机轮换执行 4 个中继架次，分别使用 4 组能源组件；
- 最终保持 80 个货箱零延误，38936 个通信状态采样点中无通信中断；
- 运输与中继总能耗为 68.9654 kWh，联合任务完成时间为 8277.90 s；另对通信切换边界加密检查 1558 个样本，未发现中断。
- 北部中继最小链路裕量仅 0.069 dB；对现有直连缺口额外增加 0.1 dB 中继链路损耗时，北部有 372 个逐秒样本失去覆盖。

### 问题四

问题四固定问题三的架次、时刻和通信关系，将服务区划分为独立执行的 2 组或 3 组。完整枚举 63 种和 301 种合法分区，并分别核算“保留原执行编号”与“仅组内重派同机型资源”的配置。若每组货箱数和联合架次数均控制在组均值的 25% 范围内，两种口径下 2 组缺口分别为 8 件和 4 件，3 组分别为 14 件和 13 件；25% 为额外比较条件。详细结果见 `results/问题四计算说明.md`。

## 目录

```text
src/       问题一至问题四的求解与实验脚本
results/   计算说明、规则整理和 JSON 结果
outputs/   问题一至问题三最终 Excel 结果
```

## 数据说明

原始赛题数据没有上传到仓库。运行代码前，请将官方数据放在本机：

```text
C:\Users\<用户名>\Desktop\华为杯2026\数据\
```

可通过环境变量 `HUAWEICUP_DATA_ROOT` 指向本机的官方数据目录。例如在 PowerShell 中运行 `$env:HUAWEICUP_DATA_ROOT = 'D:\比赛数据\数据'`；未设置时使用 `src/solve_problem1.py` 中的默认路径。发布版脚本在 `src` 内运行时，会读写同级的 `results` 目录。

## 环境

主要依赖：Python 3.9+、pandas、numpy、scipy、openpyxl、rasterio、ortools、deap。

问题一：

```powershell
cd src
python solve_problem1.py
```

问题二基础方案：

```powershell
cd src
python solve_problem2_baseline.py
python solve_problem2_multistop.py
```

问题二 ALNS 与 CP-SAT 实验：

```powershell
cd src
python experiment_problem2_methods.py
python experiment_problem2_pareto.py
python prepare_problem2_final.py
```

问题三运输与中继联合调度：

```powershell
cd src
python prepare_problem3_transport.py
python solve_problem3_coverage.py
python analyze_problem3_relay_candidates.py
python refine_problem3_relay_points.py
python plan_problem3_relay.py
python solve_problem3_joint.py
python analyze_problem3_link_sensitivity.py
```

问题三的最终结果见：

```text
results/问题三运输与中继联合调度最终结果.json
results/问题三计算说明.md
outputs/问题三运输与中继联合调度方案.xlsx
```

问题四任务分区：

```powershell
cd src
python solve_problem4_partition.py
```

## 结果边界

问题二中 CP-SAT 的最优性结论针对 ALNS 给定的组批和路线集合。问题三的悬停点与中继轮换顺序采用启发式候选搜索，最终方案通过逐秒链路和资源约束验证。两问均不宣称完整混合离散与连续优化问题的严格全局最优。问题四的枚举最优性仅针对问题三固定任务、时刻及所选资源口径下的分区选择。
