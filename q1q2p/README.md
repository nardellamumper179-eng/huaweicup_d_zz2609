# 第一、二问论文图件

本目录仅保留第一、二问最终采用的图件、完整生图脚本及复现所需的最小输入数据。旧版流程图、试绘图片、搜索日志和其他中间产物均未收录。

## 目录结构

```text
q1q2p/
├─ generate_all_figures.py       # 一键生成图1至图10
├─ requirements.txt              # 绘图依赖
├─ 图表说明.md                    # 逐图内容及论文放置建议
├─ figures/                       # 最终PNG、PDF和SVG
├─ inputs/                        # 绘图所需的4个最小输入文件
└─ scripts/
   ├─ terrain_figure.py           # 图1
   ├─ flowchart_figures.py        # 图2、图3、图7
   └─ result_figures.py           # 图4至图6、图8至图10
```

## 一键重新生成

在当前目录运行：

```powershell
python -m pip install -r requirements.txt
python generate_all_figures.py
```

脚本会覆盖 `figures/` 中同名的最终图件。图1至图10按论文数据出现的先后顺序编号；图9甘特图只画到最后返航完成时刻。

## 输入说明

- `调度中心与服务区.xlsx`：O01与S001至S015的坐标。
- `镇龙乡及周边30米DEM.mat`：图1使用的30 m DEM。
- `问题一计算结果.xlsx`：图4至图6使用的第一问最终计算结果。
- `问题二ALNS_CP_SAT零延误方案.xlsx`：图8至图10使用的第二问最终方案。

这些文件是最终图表的直接数据来源，不包含试验过程文件或废弃方案。

## 输出格式

- PNG：正文插图和快速预览，320 dpi。
- PDF：论文排版和打印。
- SVG：需要后期微调时使用。

Windows环境会优先使用黑体或微软雅黑，以保证中文显示。所有流程图均为代码绘制，文字、框线和箭头可重复生成。
