from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PACKAGE_ROOT / "inputs"
OUTPUT_DIR = PACKAGE_ROOT / "figures"
Q1_BOOK = INPUT_DIR / "问题一计算结果.xlsx"
Q2_BOOK = INPUT_DIR / "问题二ALNS_CP_SAT零延误方案.xlsx"

INK = "#30343A"
MUTED = "#66727C"
GRID = "#DCE5EA"
PANEL = "#F6F9FA"
BLUE = "#4E79A7"
CYAN = "#62B7B4"
YELLOW = "#E9C75B"
SALMON = "#E88982"
RED = "#D85852"


def setup_style() -> None:
    for candidate in (
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
    ):
        if candidate.exists():
            mpl.font_manager.fontManager.addfont(str(candidate))
            mpl.rcParams["font.family"] = mpl.font_manager.FontProperties(
                fname=str(candidate)
            ).get_name()
            break
    mpl.rcParams.update(
        {
            "axes.unicode_minus": False,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "axes.facecolor": PANEL,
            "axes.edgecolor": "#87939C",
            "axes.labelcolor": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": INK,
            "font.size": 10.5,
        }
    )


def finish(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_title(title, loc="left", fontsize=16, fontweight="bold", pad=18, color=INK)
    if subtitle:
        ax.text(
            0,
            1.015,
            subtitle,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=9.5,
            color=MUTED,
        )
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def save(fig, filename: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = OUTPUT_DIR / filename
    fig.savefig(stem.with_suffix(".png"), dpi=320, bbox_inches="tight", pad_inches=0.14)
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.14)
    fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.14)
    plt.close(fig)
    print(stem.with_suffix(".png"))


def plot_q1_safe_payload() -> None:
    data = pd.read_excel(Q1_BOOK, sheet_name="20%安全载荷")
    pivot = data.pivot(index="服务区编号", columns="机型", values="最大安全载荷_kg")
    pivot = pivot.reindex(sorted(pivot.index))

    fig, ax = plt.subplots(figsize=(11.8, 8.2), dpi=180)
    y = np.arange(len(pivot))
    height = 0.22
    colors = {"A": BLUE, "B": CYAN, "C": YELLOW}
    offsets = {"A": -height, "B": 0, "C": height}
    for model in ["A", "B", "C"]:
        values = pivot[model].to_numpy(float)
        bars = ax.barh(
            y + offsets[model],
            values,
            height=height * 0.88,
            color=colors[model],
            edgecolor="white",
            linewidth=0.8,
            label=f"{model}型",
            zorder=3,
        )
        for bar, value in zip(bars, values):
            ax.text(
                value + 0.65,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.1f}",
                ha="left",
                va="center",
                fontsize=7.6,
                color=INK,
            )

    ax.set_yticks(y)
    ax.set_yticklabels(pivot.index)
    ax.invert_yaxis()
    ax.set_xlim(0, 88)
    ax.set_xlabel("单架次最大安全载荷（kg）")
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    ax.legend(frameon=False, ncol=3, loc="lower right")
    finish(
        ax,
        "各服务区不同机型的最大安全载荷",
        "在20%返航安全余量下，满足载重、体积和往返能耗约束时的单架次最大货物质量。",
    )
    save(fig, "图4_第一问各服务区最大安全载荷")


def plot_q1_service_bubbles() -> None:
    route = pd.read_excel(Q1_BOOK, sheet_name="航段地形参数")
    summary = pd.read_excel(Q1_BOOK, sheet_name="服务区汇总")
    data = route.merge(summary, on="服务区编号").sort_values("服务区编号")
    data["水平距离_km"] = data["水平距离_m"] / 1000

    fig, ax = plt.subplots(figsize=(11.5, 7.6), dpi=180)
    trip_colors = data["最优架次数"].map({1: CYAN, 2: SALMON})
    sizes = 55 + data["总质量_kg"].to_numpy(float) * 3.2
    ax.scatter(
        data["水平距离_km"],
        data["总能耗_kWh"],
        s=sizes,
        c=trip_colors,
        edgecolor="white",
        linewidth=1.4,
        alpha=0.9,
        zorder=3,
    )

    offsets = {
        "S001": (8, 7), "S002": (8, -13), "S003": (-37, 9), "S004": (8, 7),
        "S005": (8, 7), "S006": (8, 7), "S007": (8, 7), "S008": (8, -13),
        "S009": (-35, 8), "S010": (-34, -11), "S011": (-34, 8), "S012": (8, 8),
        "S013": (8, 9), "S014": (8, -12), "S015": (8, 7),
    }
    for row in data.itertuples(index=False):
        dx, dy = offsets[str(row.服务区编号)]
        ax.annotate(
            str(row.服务区编号),
            (float(row.水平距离_km), float(row.总能耗_kWh)),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=8.2,
            ha="left" if dx >= 0 else "right",
            va="center",
            color=INK,
        )

    ax.set_xlim(2.35, 8.65)
    ax.set_ylim(0.45, 9.15)
    ax.set_xlabel("O01至服务区水平距离（km）")
    ax.set_ylabel("最优组批总能耗（kWh）")
    ax.grid(color=GRID, linewidth=0.8, zorder=0)
    legend_items = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=CYAN,
               markeredgecolor="white", markersize=9, label="1架次"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=SALMON,
               markeredgecolor="white", markersize=9, label="2架次"),
    ]
    first_legend = ax.legend(handles=legend_items, title="最优架次数", frameon=False,
                             loc="upper left")
    ax.add_artist(first_legend)
    for mass in [25, 80, 154]:
        ax.scatter([], [], s=55 + mass * 3.2, c="#A9C8D3", alpha=0.55,
                   edgecolor="white", label=f"{mass} kg")
    ax.legend(title="服务区货物总质量", frameon=False, loc="lower right",
              labelspacing=1.2, borderpad=0.8)
    finish(
        ax,
        "服务区最优组批能耗与航程关系",
        "气泡面积表示该服务区货物总质量；颜色表示字典序最优方案的架次数。",
    )
    save(fig, "图5_第一问服务区组批能耗与航程关系")


def plot_q1_sensitivity() -> None:
    data = pd.read_excel(Q1_BOOK, sheet_name="安全余量敏感性汇总")
    reserve = data["返航安全余量"].to_numpy(float) * 100
    baseline = data.loc[np.isclose(data["返航安全余量"], 0.20)].iloc[0]
    series = {
        "总架次": data["总架次数"].to_numpy(float) / float(baseline["总架次数"]) * 100,
        "总能耗": data["总能耗_kWh"].to_numpy(float) / float(baseline["总能耗_kWh"]) * 100,
        "累计作业时间": data["累计作业时间_s"].to_numpy(float)
        / float(baseline["累计作业时间_s"]) * 100,
    }
    colors = {"总架次": BLUE, "总能耗": RED, "累计作业时间": CYAN}

    fig, ax = plt.subplots(figsize=(11.2, 6.8), dpi=180)
    ax.axvspan(10, 20, color="#DCECEF", alpha=0.7, zorder=0)
    ax.text(15, 115.15, "组批结果稳定区间", ha="center", va="top", fontsize=9.0, color=MUTED)
    for label, values in series.items():
        ax.plot(
            reserve,
            values,
            marker="o",
            markersize=6.5,
            linewidth=2.2,
            drawstyle="steps-post",
            color=colors[label],
            label=label,
            zorder=3,
        )
    ax.axhline(100, color="#8B969E", linewidth=1.0, linestyle="--", zorder=1)
    ax.text(9.8, 100.25, "20%基准＝100", ha="left", va="bottom", fontsize=8.6, color=MUTED)
    ax.annotate("67.36 kWh", (30, series["总能耗"][-1]), xytext=(9, 7),
                textcoords="offset points", fontsize=8.8, color=RED)
    ax.annotate("10.17 h", (30, series["累计作业时间"][-1]), xytext=(9, -3),
                textcoords="offset points", fontsize=8.8, color=CYAN)
    ax.annotate("20架次", (30, series["总架次"][-1]), xytext=(9, -17),
                textcoords="offset points", fontsize=8.8, color=BLUE)
    ax.set_xlim(9, 33)
    ax.set_ylim(98, 116)
    ax.set_xticks(reserve)
    ax.set_xticklabels([f"{v:.0f}%" for v in reserve])
    ax.set_xlabel("返航安全余量")
    ax.set_ylabel("相对20%基准的指标（%）")
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.legend(frameon=False, ncol=3, loc="upper left", bbox_to_anchor=(0, 0.93))
    finish(
        ax,
        "返航安全余量对第一问结果的影响",
        "10%—20%时方案保持不变；25%起安全约束使架次、能耗和作业时间同步上升。",
    )
    save(fig, "图6_第一问返航安全余量敏感性")


def read_q2(sheet: str) -> pd.DataFrame:
    return pd.read_excel(Q2_BOOK, sheet_name=sheet, header=4).dropna(how="all")


def plot_q2_gantt() -> None:
    trips = read_q2("运输架次")
    trips = trips.dropna(subset=["架次编号", "无人机编号", "开始时刻_s", "返回O01时刻_s"])
    order = (
        trips[["无人机编号", "机型编号"]]
        .drop_duplicates()
        .sort_values(["机型编号", "无人机编号"])
    )
    uavs = order["无人机编号"].astype(str).tolist()
    y_map = {uav: i for i, uav in enumerate(uavs)}
    colors = {"A": BLUE, "B": CYAN, "C": SALMON}

    fig, ax = plt.subplots(figsize=(12.0, 6.8), dpi=180)
    for row in trips.sort_values("开始时刻_s").itertuples(index=False):
        uav = str(row.无人机编号)
        start = float(row.开始时刻_s) / 3600
        end = float(row.返回O01时刻_s) / 3600
        model = str(row.机型编号)
        ax.barh(
            y_map[uav],
            end - start,
            left=start,
            height=0.60,
            color=colors[model],
            edgecolor="white",
            linewidth=1.0,
            zorder=3,
        )
        service = str(row.访问服务区顺序)
        if end - start > 0.22:
            ax.text(
                (start + end) / 2,
                y_map[uav],
                service,
                ha="center",
                va="center",
                fontsize=7.5,
                color="white" if model != "B" else INK,
                fontweight="bold",
                clip_on=True,
            )

    makespan = float(trips["返回O01时刻_s"].max()) / 3600
    ax.axvline(makespan, color=RED, linestyle="--", linewidth=1.3, zorder=2)
    ax.text(makespan - 0.015, -0.43, "最后返航 2.144 h", ha="right",
            va="bottom", fontsize=8.8, color=RED)
    ax.set_yticks(range(len(uavs)))
    ax.set_yticklabels(uavs)
    ax.invert_yaxis()
    ax.set_xlim(0, 2.28)
    ax.set_xlabel("任务时间（h）")
    ax.set_ylabel("实体无人机")
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    handles = [mpl.patches.Patch(facecolor=colors[m], edgecolor="white", label=f"{m}型")
               for m in ["A", "B", "C"]]
    ax.legend(handles=handles, frameon=False, ncol=3, loc="upper left")
    finish(
        ax,
        "第二问21架次无人机任务时序",
        "条带表示起飞至返回O01的作业区间；同一行任务互不重叠，条内标注访问服务区。",
    )
    save(fig, "图9_第二问无人机任务调度甘特图")


def plot_q2_delivery_progress() -> None:
    delivery = read_q2("逐箱交付")
    delivery = delivery.dropna(subset=["货箱编号", "物资类型", "交付完成时刻_s"])
    delivery["交付_h"] = delivery["交付完成时刻_s"].astype(float) / 3600
    type_order = ["医疗物资", "饮用水", "应急食品", "生活卫生用品"]
    colors = [RED, BLUE, YELLOW, CYAN]
    last_delivery = float(delivery["交付_h"].max())
    times = np.unique(np.r_[0, np.sort(delivery["交付_h"].to_numpy(float)), last_delivery])
    layers = []
    for material in type_order:
        material_times = np.sort(
            delivery.loc[delivery["物资类型"] == material, "交付_h"].to_numpy(float)
        )
        layers.append(np.searchsorted(material_times, times, side="right"))

    fig, ax = plt.subplots(figsize=(11.7, 6.8), dpi=180)
    ax.stackplot(times, layers, labels=type_order, colors=colors, alpha=0.82, step="post")
    for hour in [1, 2]:
        ax.axvline(hour, color="#6F7B83", linestyle=(0, (3, 3)), linewidth=0.9, zorder=4)
        ax.text(
            hour - 0.018,
            2.0,
            f"{hour} h时限",
            ha="right",
            va="bottom",
            rotation=90,
            fontsize=8.2,
            color=MUTED,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.82, pad=0.8),
            zorder=5,
        )
    ax.plot([last_delivery], [80], marker="o", markersize=6, color=INK, zorder=5)
    ax.annotate(
        f"80箱全部交付\n{last_delivery:.3f} h",
        (last_delivery, 80),
        xytext=(-12, -18),
        textcoords="offset points",
        ha="right",
        va="top",
        fontsize=9.0,
        color=INK,
        bbox=dict(boxstyle="round,pad=0.28", facecolor="white", edgecolor=GRID),
    )
    ax.set_xlim(0, last_delivery + 0.06)
    ax.set_ylim(0, 84)
    ax.set_xlabel("交付完成时刻（h）")
    ax.set_ylabel("累计完成交付货箱数")
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.legend(frameon=False, ncol=4, loc="upper left")
    finish(
        ax,
        "第二问80个货箱累计交付进程",
        "横轴截取至最后一箱完成交付时刻；面积按物资类型累计，全部货箱均按期完成交付。",
    )
    save(fig, "图10_第二问货箱累计交付进程")


def plot_q2_tradeoff_heatmap() -> None:
    plans = read_q2("方案对照")
    plans = plans.dropna(subset=["方案"]).iloc[:3].copy()
    metrics = ["加权延误", "迟到箱数", "最后返航_s", "总能耗_kWh", "总架次"]
    values = plans[metrics].astype(float).to_numpy()
    lo = values.min(axis=0)
    hi = values.max(axis=0)
    norm = np.divide(values - lo, hi - lo, out=np.zeros_like(values), where=(hi - lo) > 0)
    annotations = np.empty_like(values, dtype=object)
    for i in range(values.shape[0]):
        annotations[i, 0] = f"{values[i, 0]:,.0f}"
        annotations[i, 1] = f"{values[i, 1]:.0f}箱"
        annotations[i, 2] = f"{values[i, 2] / 3600:.2f} h"
        annotations[i, 3] = f"{values[i, 3]:.2f} kWh"
        annotations[i, 4] = f"{values[i, 4]:.0f}架次"

    cmap = LinearSegmentedColormap.from_list("relative_cost", ["#2C7890", "#F2E6A2", "#D85B55"])
    fig, ax = plt.subplots(figsize=(11.6, 5.6), dpi=180)
    im = ax.imshow(norm, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i in range(norm.shape[0]):
        for j in range(norm.shape[1]):
            ax.text(
                j,
                i,
                annotations[i, j],
                ha="center",
                va="center",
                fontsize=10.0,
                fontweight="bold",
                color="white" if norm[i, j] > 0.72 or norm[i, j] < 0.15 else INK,
            )
    ax.set_xticks(np.arange(5))
    ax.set_xticklabels(["加权延误", "迟到箱数", "最后返航", "总能耗", "总架次"])
    ax.set_yticks(np.arange(3))
    ax.set_yticklabels(
        ["19架次\n局部搜索", "20架次\n候选组批+CP-SAT", "21架次\nALNS+CP-SAT"]
    )
    ax.set_xticks(np.arange(-0.5, 5, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 3, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=2.2)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.tick_params(axis="both", length=0, pad=10)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cbar = fig.colorbar(im, ax=ax, fraction=0.032, pad=0.035)
    cbar.set_label("列内相对代价（0优，1劣）", color=INK)
    cbar.ax.tick_params(colors=MUTED)
    ax.set_title("19—21架次方案的多目标权衡", loc="left", fontsize=16,
                 fontweight="bold", pad=30, color=INK)
    ax.text(
        0,
        1.035,
        "颜色按各指标列独立归一化；单元格保留原始数值，用于比较及时性、完成时间、能耗和架次的取舍。",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.5,
        color=MUTED,
    )
    save(fig, "图8_第二问候选方案多目标权衡热力图")


def main() -> None:
    setup_style()
    plot_q1_safe_payload()
    plot_q1_service_bubbles()
    plot_q1_sensitivity()
    plot_q2_tradeoff_heatmap()
    plot_q2_gantt()
    plot_q2_delivery_progress()


if __name__ == "__main__":
    main()
