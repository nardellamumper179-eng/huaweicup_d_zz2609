# Huawei Cup D 题：山区洪涝灾害下无人机运输与通信协同优化

本仓库整理问题一、问题二、问题三的模型代码、计算说明和最终结果文件。

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
- 运输与中继总能耗为 68.9307 kWh，联合任务完成时间为 8277.90 s。

## 目录

```text
src/       问题一至问题三的求解与实验脚本
results/   计算说明、规则整理和 JSON 结果
outputs/   问题一至问题三最终 Excel 结果
```

## 数据说明

原始赛题数据没有上传到仓库。运行代码前，请将官方数据放在本机：

```text
C:\Users\<用户名>\Desktop\华为杯2026\数据\
```

当前脚本中的数据路径定义在 `src/solve_problem1.py` 的 `DATA_ROOT`。如需在其他电脑运行，请修改为本机数据目录。

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
```

问题三的最终结果见：

```text
results/问题三运输与中继联合调度最终结果.json
results/问题三计算说明.md
outputs/问题三运输与中继联合调度方案.xlsx
```

## 结果边界

问题二中 CP-SAT 的最优性结论针对 ALNS 给定的组批和路线集合。问题三的悬停点与中继轮换顺序采用启发式候选搜索，最终方案通过逐秒链路和资源约束验证。两问均不宣称完整混合离散与连续优化问题的严格全局最优。
