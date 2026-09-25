from __future__ import annotations

from pathlib import Path

from scripts import flowchart_figures, result_figures, terrain_figure


ROOT = Path(__file__).resolve().parent
REQUIRED_INPUTS = (
    "调度中心与服务区.xlsx",
    "镇龙乡及周边30米DEM.mat",
    "问题一计算结果.xlsx",
    "问题二ALNS_CP_SAT零延误方案.xlsx",
)


def check_inputs() -> None:
    missing = [name for name in REQUIRED_INPUTS if not (ROOT / "inputs" / name).is_file()]
    if missing:
        names = "\n".join(f"  - {name}" for name in missing)
        raise FileNotFoundError(f"缺少绘图输入文件：\n{names}")


def main() -> None:
    check_inputs()
    (ROOT / "figures").mkdir(exist_ok=True)

    print("[1/3] 生成前置地形图（图1）")
    terrain_figure.main()

    print("[2/3] 生成第一、二问流程图（图2、图3、图7）")
    flowchart_figures.setup()
    flowchart_figures.q1_overview()
    flowchart_figures.q1_algorithm()
    flowchart_figures.q2_flow()

    print("[3/3] 生成结果图（图4至图6、图8至图10）")
    result_figures.main()

    print(f"全部图件已生成：{ROOT / 'figures'}")


if __name__ == "__main__":
    main()
