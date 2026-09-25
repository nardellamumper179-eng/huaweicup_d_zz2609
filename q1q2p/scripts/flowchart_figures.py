from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle
from matplotlib.path import Path as MplPath

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
OUT = PACKAGE_ROOT / "figures"
INK = "#30343A"
GROUP = "#EEF2F4"
CYAN = "#A9DDE0"
YELLOW = "#F3DEA0"
PINK = "#E9A09B"
GREEN = "#DCEAB8"
BLUE = "#5576D6"
RED = "#E89B98"


def setup():
    font = Path("C:/Windows/Fonts/simhei.ttf")
    if font.exists():
        mpl.font_manager.fontManager.addfont(str(font))
        mpl.rcParams["font.family"] = "SimHei"
    mpl.rcParams.update({"axes.unicode_minus": False, "svg.fonttype": "none", "pdf.fonttype": 42,
                         "figure.facecolor": "white", "savefig.facecolor": "white"})


def box(ax, x, y, w, h, text, fill="white", fs=10, color=INK):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=INK, linewidth=1.15, zorder=3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color=color, linespacing=1.25, zorder=4)
    return {"x": x, "y": y, "w": w, "h": h}


def group(ax, x, y, w, h, title):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=GROUP, edgecolor="#555A60",
                           linewidth=1.15, linestyle=(0, (4, 3)), alpha=.72, zorder=0))
    ax.text(x + w / 2, y + h - .32, title, ha="center", va="center", fontsize=11.2, color="#555A60")


def diamond(ax, cx, cy, w, h, text, fill=CYAN, fs=9):
    pts = [(cx, cy+h/2), (cx+w/2, cy), (cx, cy-h/2), (cx-w/2, cy)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=fill, edgecolor=INK, linewidth=1.15, zorder=3))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, linespacing=1.18, zorder=4)
    return {"cx": cx, "cy": cy, "w": w, "h": h}


def arrow(ax, points, label=None, xy=None):
    verts = [(float(x), float(y)) for x, y in points]
    patch = FancyArrowPatch(path=MplPath(verts, [MplPath.MOVETO] + [MplPath.LINETO] * (len(verts)-1)),
                            arrowstyle="-|>", mutation_scale=10, linewidth=1.15, color=INK,
                            shrinkA=0, shrinkB=0, zorder=2)
    ax.add_patch(patch)
    if label and xy:
        ax.text(xy[0], xy[1], label, fontsize=8, ha="center", va="center",
                bbox=dict(facecolor="white", edgecolor="none", pad=.4), zorder=5)


def line(ax, points):
    xs, ys = zip(*points); ax.plot(xs, ys, color=INK, linewidth=1.05, zorder=1)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    stem = OUT / name
    fig.savefig(stem.with_suffix(".png"), dpi=320, bbox_inches="tight", pad_inches=.12)
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight", pad_inches=.12)
    fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight", pad_inches=.12)
    plt.close(fig)


def q1_overview():
    fig, ax = plt.subplots(figsize=(18.2, 7.6), dpi=180); ax.set_xlim(0, 24); ax.set_ylim(0, 10); ax.axis("off")
    inp = box(ax, .35, 4.38, 1.7, 1, "第一问\n输入数据", fs=11)
    group(ax, 2.65, .75, 3.05, 8.5, "基础数据")
    sources = [box(ax,3,7.32,2.35,1.02,"调度中心与\n15个服务区"), box(ax,3,5.72,2.35,.82,"30 m DEM"),
               box(ax,3,3.92,2.35,1.02,"A、B、C型\n无人机参数"), box(ax,3,2.32,2.35,.82,"80个不可拆货箱")]
    line(ax, [(2.35,2.73),(2.35,7.83)]); arrow(ax, [(2.05,4.88),(2.35,4.88),(2.35,7.83),(3,7.83)])
    for b in sources[1:]: arrow(ax, [(2.35,b["y"]+b["h"]/2),(3,b["y"]+b["h"]/2)])
    line(ax, [(5.78,2.73),(5.78,7.83)])
    for b in sources: line(ax, [(b["x"]+b["w"],b["y"]+b["h"]/2),(5.78,b["y"]+b["h"]/2)])

    group(ax, 6.25,1.1,3.25,7.8,"航段参数计算")
    pre=[box(ax,6.62,7.1,2.5,.78,"计算水平距离"),box(ax,6.62,5.67,2.5,.78,"提取沿线最高高程"),
         box(ax,6.62,4.05,2.5,.95,"确定巡航海拔与\n往返升降高度"),box(ax,6.62,2.38,2.5,.95,"计算飞行时间与\n载荷相关能耗",fill=CYAN)]
    arrow(ax,[(5.78,7.83),(6.05,7.83),(6.05,7.49),(6.62,7.49)])
    for a,b in zip(pre,pre[1:]): arrow(ax,[(a["x"]+1.25,a["y"]),(a["x"]+1.25,b["y"]+b["h"])] )
    common=box(ax,9.88,4.34,1.78,1.02,"机型—服务区\n航段参数",fill=CYAN,fs=10.3)
    arrow(ax,[(9.12,2.85),(9.66,2.85),(9.66,4.85),(9.88,4.85)])

    group(ax,12.18,5.25,5.55,3.8,"最大安全载荷")
    a=box(ax,12.46,7.18,1.7,.94,"逐机型、逐服务区\n检查空载可行性",fs=8.7)
    d=diamond(ax,15.02,7.65,1.55,1.22,"满载满足\n安全余量？")
    rated=box(ax,16.1,7.32,1.22,.72,"取额定载荷",fill=GREEN,fs=9.2)
    binary=box(ax,13.85,5.72,1.55,.78,"二分搜索\n安全载荷",fill=YELLOW,fs=9.2)
    result=box(ax,16,5.72,1.32,.78,"记录安全载荷",fs=9.1)
    arrow(ax,[(11.66,4.85),(11.9,4.85),(11.9,7.65),(12.46,7.65)]); arrow(ax,[(14.16,7.65),(14.25,7.65)])
    arrow(ax,[(15.795,7.65),(16.1,7.65)],"是",(15.95,7.88)); arrow(ax,[(15.02,7.04),(14.63,6.65),(14.63,6.5)],"否",(15.2,6.8))
    arrow(ax,[(16.71,7.32),(16.71,6.5),(16.66,6.5)]); arrow(ax,[(15.4,6.11),(16,6.11)])

    group(ax,12.18,.55,5.55,4.15,"可行批次生成")
    en=box(ax,12.55,3.1,1.65,.9,"按服务区枚举\n货箱组合",fs=9.2)
    fd=diamond(ax,15.35,3.55,1.78,1.38,"重量、体积\n与能量是否\n均可行？",fs=8)
    keep=box(ax,16.36,3.17,1.02,.78,"保留可行\n批次",fill=GREEN,fs=9.1)
    dis=box(ax,14.63,1.33,1.3,.72,"舍弃组合",fill=RED,fs=9.2)
    arrow(ax,[(11.66,4.85),(11.9,4.85),(11.9,3.55),(12.55,3.55)]); arrow(ax,[(14.2,3.55),(14.46,3.55)])
    arrow(ax,[(16.24,3.55),(16.36,3.55)],"是",(16.3,3.8)); arrow(ax,[(15.35,2.86),(15.35,2.05)],"否",(15.6,2.5))

    group(ax,18.22,.8,3.15,8,"组批优化")
    ops=[box(ax,18.63,6.98,2.32,.92,"状态集合递推",fill=PINK),box(ax,18.63,5.15,2.32,1.08,"按架次—能耗—时间\n比较方案",fill=YELLOW,fs=9.3),
         box(ax,18.63,3.45,2.32,.9,"回溯最优组批",fs=9.5),box(ax,18.63,1.62,2.32,1.02,"检查货箱唯一交付\n与约束满足",fs=9.2)]
    arrow(ax,[(17.38,3.55),(18,3.55),(18,7.44),(18.63,7.44)])
    for a,b in zip(ops,ops[1:]): arrow(ax,[(19.79,a["y"]),(19.79,b["y"]+b["h"])])
    base=box(ax,22,5.22,1.55,.92,"汇总第一问\n计算结果",fs=9.4); sens=box(ax,22,3.23,1.55,1.22,"改变返航\n安全余量并\n重复计算",fill=YELLOW,fs=8.5); out=box(ax,21.88,1.22,1.8,1.18,"载荷、组批、能耗\n时间与敏感性",fill=BLUE,color="white",fs=9.4)
    arrow(ax,[(17.32,6.11),(17.92,6.11),(17.92,9.35),(21.66,9.35),(21.66,5.68),(22,5.68)])
    arrow(ax,[(20.95,2.13),(21.66,2.13),(21.66,5.68),(22,5.68)]); arrow(ax,[(22.775,5.22),(22.775,4.45)]); arrow(ax,[(22.775,3.23),(22.775,2.4)])
    ax.text(12,.12,"货箱不可拆分；每箱配送一次；同时满足载质量、装载体积和返航安全能量余量。",ha="center",fontsize=8.7,color="#60666D")
    save(fig,"图2_第一问建模与求解流程图")


def q1_algorithm():
    fig, ax = plt.subplots(figsize=(18.5,7.5),dpi=180); ax.set_xlim(0,26); ax.set_ylim(0,10); ax.axis("off")
    group(ax,.45,1.15,3.15,7.75,"服务区输入")
    ins=[box(ax,.82,6.92,2.42,.9,"服务区 i 的航段参数",fs=9.7),box(ax,.82,4.74,2.42,.9,"A、B、C型无人机参数",fs=9.3),box(ax,.82,2.51,2.42,1,"服务区 i 的\n货箱集合 K_i",fs=9.1)]
    line(ax,[(3.82,3.01),(3.82,7.37)]); [line(ax,[(b["x"]+b["w"],b["y"]+b["h"]/2),(3.82,b["y"]+b["h"]/2)]) for b in ins]
    group(ax,4.18,5.18,13.75,4.25,"最大安全载荷")
    upper=[box(ax,4.55,7.28,1.55,.82,"读取机型 g",fs=9.5),box(ax,6.45,7.2,1.75,.98,"计算空载\n往返能耗",fs=9.4),diamond(ax,9.2,7.69,1.62,1.28,"空载往返\n是否可行？",fs=8.8),box(ax,8.47,5.62,1.46,.74,"判为不可达",fill=RED,fs=9),box(ax,10.3,7.2,1.78,.98,"计算满载\n往返能耗",fs=9.4),diamond(ax,13.12,7.69,1.62,1.28,"满载满足\n安全余量？",fs=8.8),box(ax,14.38,7.32,1.42,.74,"取额定载荷",fill=GREEN,fs=9.1),box(ax,12.36,5.56,1.84,.92,"二分搜索\n安全载荷",fill=YELLOW,fs=8.7),box(ax,15.34,5.61,1.92,.82,"记录最大安全载荷",fs=9)]
    arrow(ax,[(3.82,7.37),(4.05,7.37),(4.05,7.69),(4.55,7.69)]); arrow(ax,[(6.1,7.69),(6.45,7.69)]); arrow(ax,[(8.2,7.69),(8.39,7.69)]); arrow(ax,[(10.01,7.69),(10.3,7.69)],"是",(10.13,7.94)); arrow(ax,[(9.2,7.05),(9.2,6.36),(9.2,6.36)],"否",(9.45,6.75)); arrow(ax,[(12.08,7.69),(12.31,7.69)]); arrow(ax,[(13.93,7.69),(14.38,7.69)],"是",(14.15,7.94)); arrow(ax,[(13.12,7.05),(13.12,6.48)],"否",(13.38,6.75)); arrow(ax,[(15.09,7.32),(15.09,6.02),(15.34,6.02)]); arrow(ax,[(14.2,6.02),(15.34,6.02)])
    group(ax,4.18,.42,8.2,4.22,"候选批次生成")
    low=[box(ax,4.56,2.82,1.72,.92,"枚举非空货箱组合\n共 2^(n_i)-1 个",fs=8.2),box(ax,6.69,2.82,1.48,.92,"分别尝试\nA、B、C型",fs=9),diamond(ax,9.31,3.28,1.82,1.48,"重量、体积\n与能量是否\n同时满足？",fs=7.9),box(ax,10.45,2.84,1.52,.88,"加入可行批次",fill=GREEN,fs=9),box(ax,8.64,.83,1.36,.72,"舍弃组合",fill=RED,fs=9)]
    arrow(ax,[(3.82,3.01),(4.05,3.01),(4.05,3.28),(4.56,3.28)]); arrow(ax,[(6.28,3.28),(6.69,3.28)]); arrow(ax,[(8.17,3.28),(8.4,3.28)]); arrow(ax,[(10.22,3.28),(10.45,3.28)],"是",(10.25,3.55)); arrow(ax,[(9.31,2.54),(9.31,1.55)],"否",(9.57,2.1))
    group(ax,12.82,.42,5.1,4.22,"组批优化")
    dp=[box(ax,13.25,3.12,4.22,.68,"建立状态集合",fill=PINK,fs=9.2),box(ax,13.25,2.09,4.22,.74,"逐步加入未配送货箱",fs=8.9),box(ax,13.25,.85,4.22,.88,"按架次—能耗—时间更新方案",fill=YELLOW,fs=9)]
    arrow(ax,[(11.97,3.28),(12.6,3.28),(12.6,3.46),(13.25,3.46)]); [arrow(ax,[(15.36,a["y"]),(15.36,b["y"]+b["h"])]) for a,b in zip(dp,dp[1:])]
    group(ax,18.55,.72,6.92,8.42,"结果整理与检查")
    rs=[box(ax,18.98,7.18,2.1,.96,"汇总45个\n机型—服务区载荷上限",fs=8.8),box(ax,18.98,4.92,2.1,.96,"回溯每个服务区的\n最优组批",fs=8.9),box(ax,21.8,5.93,2.94,1.22,"检查唯一交付、载重、体积\n与返航安全能量余量",fs=8.8),box(ax,21.93,3.44,2.68,1.08,"改变10%～30%安全余量\n重新计算",fill=YELLOW,fs=8.9),box(ax,21.93,1.35,2.68,1.18,"整理载荷、组批、能耗、\n时间和敏感性结果",fill=BLUE,color="white",fs=9.1)]
    arrow(ax,[(17.47,6.02),(18.28,6.02),(18.28,7.66),(18.98,7.66)]); arrow(ax,[(17.47,1.29),(18.28,1.29),(18.28,5.4),(18.98,5.4)]); arrow(ax,[(21.08,7.66),(21.43,7.66),(21.43,6.54),(21.8,6.54)]); arrow(ax,[(21.08,5.4),(21.43,5.4),(21.43,6.54),(21.8,6.54)]); arrow(ax,[(23.27,5.93),(23.27,4.52)]); arrow(ax,[(23.27,3.44),(23.27,2.53)])
    ax.text(13,.08,"每个服务区分别求解；候选批次全部列举后，按字典序目标回溯最优方案。",ha="center",fontsize=8.7,color="#60666D")
    save(fig,"图3_第一问安全载荷与组批优化算法流程图")


def q2_flow():
    fig, ax = plt.subplots(figsize=(19,7.7),dpi=180); ax.set_xlim(0,26); ax.set_ylim(0,10); ax.axis("off")
    start=box(ax,.18,4.4,1.62,1,"第二问\n输入数据",fs=10.5); group(ax,2.18,.72,3.38,8.55,"问题二数据与约束")
    inp=[box(ax,2.55,7.42,2.64,.88,"第一问物理规则",fs=9.5),box(ax,2.55,5.57,2.64,.96,"8架实体无人机与机型",fs=9.4),box(ax,2.55,3.67,2.64,1,"共享电池与充电时间",fs=9.2),box(ax,2.55,1.72,2.64,1.08,"80箱时限、首批标记\n与优先系数",fs=8.8)]
    line(ax,[(2.02,2.26),(2.02,7.86)]); arrow(ax,[(1.8,4.9),(2.02,4.9),(2.02,7.86),(2.55,7.86)]); [arrow(ax,[(2.02,b["y"]+b["h"]/2),(2.55,b["y"]+b["h"]/2)]) for b in inp[1:]]; line(ax,[(5.73,2.26),(5.73,7.86)]); [line(ax,[(b["x"]+b["w"],b["y"]+b["h"]/2),(5.73,b["y"]+b["h"]/2)]) for b in inp]
    group(ax,6.05,1.3,3.55,7.35,"任务建立")
    build=[box(ax,6.45,6.88,2.75,.9,"形成初始任务集合",fs=9.2),box(ax,6.45,4.65,2.75,1.18,"检查每个任务的\n载重、体积与返航SOC",fill=CYAN,fs=9),box(ax,6.45,2.33,2.75,1.26,"计算任务时长、能耗\n和逐箱送达时间",fs=9)]
    arrow(ax,[(5.73,7.86),(5.9,7.86),(5.9,7.33),(6.45,7.33)]); [arrow(ax,[(9.2,a["y"]),(9.2,b["y"]+b["h"])]) for a,b in zip(build,build[1:])]
    group(ax,9.98,.52,6.55,8.9,"S002组批调整")
    al=[box(ax,10.4,7.72,2.08,.82,"当前S002组批",fs=9.3),box(ax,10.4,6.2,2.08,.9,"选择调整方式",fill=PINK,fs=9.2),box(ax,10.22,4.43,2.44,1.08,"移动、交换、拆分、合并\n重新组合货箱",fill=YELLOW,fs=8.9),box(ax,10.4,2.72,2.08,.9,"检查新的组批方案",fs=9.1)]
    ev=box(ax,13.34,4.84,2.62,1.18,"安排顺序并评价\n候选方案",fill=CYAN,fs=8.9); up=box(ax,13.34,3.06,2.62,1.02,"更新当前方案\n记录较优方案",fill=GREEN,fs=8.9); end=diamond(ax,14.65,1.58,1.86,1.2,"是否达到\n迭代上限？",fs=8.8)
    arrow(ax,[(9.2,2.96),(9.76,2.96),(9.76,8.13),(10.4,8.13)]); [arrow(ax,[(11.44,a["y"]),(11.44,b["y"]+b["h"])]) for a,b in zip(al,al[1:])]; arrow(ax,[(12.48,3.17),(13.02,3.17),(13.02,5.43),(13.34,5.43)]); arrow(ax,[(14.65,4.84),(14.65,4.08)]); arrow(ax,[(14.65,3.06),(14.65,2.18)]); arrow(ax,[(13.72,1.58),(12.95,1.58),(12.95,7),(12.48,7)],"否",(13.18,1.82))
    best=box(ax,16.88,7.52,1.78,.96,"确定较优S002组批",fill=GREEN,fs=9); arrow(ax,[(15.58,1.58),(16.25,1.58),(16.25,8),(16.88,8)],"是",(16.12,1.83))
    group(ax,16.72,.75,5.42,8.25,"资源与时刻安排")
    cp=[box(ax,17.08,6.05,4.68,.92,"固定组批与任务路线",fs=9.3),box(ax,17.08,4.58,4.68,.94,"安排机型、无人机、电池和开始时刻",fs=9),box(ax,17.08,3.02,4.68,1.02,"检查无人机、电池不重叠\n以及充电和硬时限约束",fill=CYAN,fs=8.8),box(ax,17.08,1.35,4.68,1.06,"依次降低延误、最后返航时刻和总能耗",fill=YELLOW,fs=8.9)]
    arrow(ax,[(17.77,7.52),(17.77,7.18),(19.42,7.18),(19.42,6.97)]); [arrow(ax,[(19.42,a["y"]),(19.42,b["y"]+b["h"])]) for a,b in zip(cp,cp[1:])]
    check=box(ax,22.62,5.35,2.98,1.22,"检查80箱唯一交付、时限、\nSOC与资源不冲突",fs=8.9); output=box(ax,22.62,2.5,2.98,1.6,"得到21架次零延误方案\n最后返航7718.4 s\n总能耗64.2234 kWh",fill=BLUE,color="white",fs=9.1)
    arrow(ax,[(21.76,1.88),(22.34,1.88),(22.34,5.96),(22.62,5.96)]); arrow(ax,[(24.11,5.35),(24.11,4.1)])
    ax.text(13,.1,"资源安排在给定组批与路线下进行；最终方案为精确排程结果，不将完整问题表述为严格全局最优。",ha="center",fontsize=8.7,color="#60666D")
    save(fig,"图7_第二问ALNS与CP-SAT协同求解流程图")


def main():
    setup(); q1_overview(); q1_algorithm(); q2_flow()


if __name__ == "__main__": main()
