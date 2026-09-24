# Huawei Cup D 题：山区洪涝灾害下无人机运输与通信协同优化

本仓库整理问题一、问题二的模型代码、计算说明和最终结果文件。

## 当前结果

### 问题一

问题一研究单服务区直接往返条件下的货箱组批，综合考虑载重、体积、返航安全余量、架次、能耗和累计作业时间。

### 问题二

问题二最终采用 **ALNS + CP-SAT** 混合方法：

- ALNS 调整货箱组批、拆分和合并结构；
- CP-SAT 在给定组批和路线下精确安排机型、实体无人机、共享电池和开始时刻；
- 最终方案为 21 架次，80 个货箱全部按期送达，加权延误为 0，最后返航时刻为 7718.4 s，总能耗为 64.2234 kWh。

## 目录

```text
src/       问题一、问题二求解与实验脚本
results/   计算说明、规则整理和 JSON 结果
outputs/   问题一、问题二最终 Excel 结果
```

## 数据说明

原始赛题数据没有上传到仓库。运行代码前，请将官方数据放在本机：

```text
C:\Users\<用户名>\Desktop\华为杯2026\数据\
```

当前脚本中的数据路径定义在 `src/solve_problem1.py` 的 `DATA_ROOT`。如需在其他电脑运行，请修改为本机数据目录。

## 环境

主要依赖：Python 3.9+、pandas、numpy、openpyxl、rasterio、ortools、deap。

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

## 结果边界

CP-SAT 的最优性结论针对 ALNS 给定的组批和路线集合。完整问题的所有组批和多点路线组合没有被穷举，因此最终结果应表述为经过精确资源排程验证的高质量可行方案，不宣称为完整问题的严格全局最优解。
