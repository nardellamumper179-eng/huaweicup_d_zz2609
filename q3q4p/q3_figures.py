from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, LightSource, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle
from matplotlib.path import Path as MplPath
from scipy.interpolate import RegularGridInterpolator
from scipy.io import loadmat
from mpl_toolkits.mplot3d import proj3d


ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "inputs"
OUTPUT_DIR = ROOT / "figures"
Q3_PATH = INPUT_DIR / "问题三运输与中继联合调度最终结果.json"
SENSITIVITY_PATH = INPUT_DIR / "问题三中继链路损耗敏感性.json"
DEM_PATH = INPUT_DIR / "镇龙乡及周边30米DEM.mat"
NODE_PATH = INPUT_DIR / "调度中心与服务区.xlsx"

INK = "#30343A"
MUTED = "#66727C"
GRID = "#DCE5EA"
PANEL = "#F6F9FA"
GROUP = "#EEF2F4"
CYAN = "#A9DDE0"
YELLOW = "#F3DEA0"
PINK = "#E9A09B"
GREEN = "#DCEAB8"
BLUE = "#5576D6"
RED = "#E89B98"

REGION_COLORS = {
    "中央": "#4E79A7",
    "东部": "#62B7B4",
    "西部": "#E9C75B",
    "北部": "#E88982",
}
SERVICE_REGIONS = {
    "S002": "中央", "S007": "中央",
    "S010": "东部", "S012": "东部", "S013": "东部", "S014": "东部",
    "S003": "西部", "S009": "西部", "S015": "西部",
    "S004": "北部", "S005": "北部", "S008": "北部",
}


def setup_style() -> None:
    for font_path in (
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
    ):
        if font_path.exists():
            mpl.font_manager.fontManager.addfont(str(font_path))
            mpl.rcParams["font.family"] = mpl.font_manager.FontProperties(
                fname=str(font_path)
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(fig: mpl.figure.Figure, name: str) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for text, ax, bounds in getattr(fig, '_flow_checks', []):
        x, y, w, h = bounds
        bb = text.get_window_extent(renderer)
        lo, hi = ax.transData.transform([(x, y), (x+w, y+h)])
        assert bb.x0 >= lo[0]+2 and bb.x1 <= hi[0]-2 and bb.y0 >= lo[1]+2 and bb.y1 <= hi[1]-2, text.get_text()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = OUTPUT_DIR / name
    fig.savefig(stem.with_suffix(".png"), dpi=320, bbox_inches="tight", pad_inches=0.14)
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.14)
    fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.14)
    plt.close(fig)
    print(stem.with_suffix(".png"))


def flow_box(ax, x, y, w, h, text, fill="white", fs=9.5, color=INK):
    ax.add_patch(
        Rectangle(
            (x, y), w, h, facecolor=fill, edgecolor=INK,
            linewidth=1.15, zorder=3,
        )
    )
    text_artist = ax.text(
        x + w / 2, y + h / 2, text, ha="center", va="center",
        fontsize=fs, color=color, linespacing=1.22, zorder=4,
    )
    if not hasattr(ax.figure, '_flow_checks'):
        ax.figure._flow_checks = []
    ax.figure._flow_checks.append((text_artist, ax, (x,y,w,h)))
    return {"x": x, "y": y, "w": w, "h": h}


def flow_group(ax, x, y, w, h, title):
    ax.add_patch(
        Rectangle(
            (x, y), w, h, facecolor=GROUP, edgecolor="#555A60",
            linewidth=1.15, linestyle=(0, (4, 3)), alpha=0.72, zorder=0,
        )
    )
    ax.text(
        x + w / 2, y + h - 0.34, title, ha="center", va="center",
        fontsize=11.0, color="#555A60",
    )


def flow_diamond(ax, cx, cy, w, h, text, fill=CYAN, fs=8.5):
    points = [
        (cx, cy + h / 2), (cx + w / 2, cy),
        (cx, cy - h / 2), (cx - w / 2, cy),
    ]
    ax.add_patch(
        Polygon(points, closed=True, facecolor=fill, edgecolor=INK, linewidth=1.15, zorder=3)
    )
    ax.text(
        cx, cy, text, ha="center", va="center", fontsize=fs,
        linespacing=1.18, zorder=4,
    )
    return {"cx": cx, "cy": cy, "w": w, "h": h}


def flow_arrow(ax, points, label=None, label_xy=None):
    vertices = [(float(x), float(y)) for x, y in points]
    path = MplPath(
        vertices,
        [MplPath.MOVETO] + [MplPath.LINETO] * (len(vertices) - 1),
    )
    ax.add_patch(
        FancyArrowPatch(
            path=path, arrowstyle="-|>", mutation_scale=10,
            linewidth=1.15, color=INK, shrinkA=0, shrinkB=0, zorder=2,
        )
    )
    if label and label_xy:
        ax.text(
            label_xy[0], label_xy[1], label, fontsize=8.0,
            ha="center", va="center",
            bbox=dict(facecolor="white", edgecolor="none", pad=0.4), zorder=5,
        )


def plot_flowchart() -> None:
    fig, ax = plt.subplots(figsize=(17.6, 7.1), dpi=180)
    ax.set_xlim(0, 25)
    ax.set_ylim(0, 10)
    ax.axis("off")
    columns = [
        ("输入与直连检查", [
            ("读取运输方案、DEM\n与通信参数", "white"),
            ("逐秒计算位置与链路损耗\n检查地形遮挡", CYAN),
            ("提取17个运输架次的\n19段直连缺口", YELLOW)]),
        ("选择中继悬停点", [
            ("按位置与高度生成候选点", "white"),
            ("筛选接入、回传与\n高度约束均满足的点", CYAN),
            ("选取中央、东部、西部、北部\n4个悬停点", GREEN)]),
        ("安排中继轮换", [
            ("计算往返飞行与悬停能耗\n检查返航SOC", CYAN),
            ("R01：中央→西部\nR02：东部→北部", PINK),
            ("安排建链与服务时段\n返航后周转300 s", "white")]),
        ("调整与复核", [
            ("调整相关运输架次时刻\n保留货箱组批与路线", YELLOW),
            ("检查交付时限、设备占用\n及返航能量约束", "white"),
            ("逐秒复核通信\n切换边界按0.05 s加密", CYAN)]),
        ("结果与敏感性", [
            ("检查样本内通信中断为0\n80箱全部按期交付", GREEN),
            ("汇总21个运输架次\n与4个中继架次", BLUE),
            ("固定航线、位置与时序\n比较附加链路损耗情景", YELLOW)]),
    ]
    ys = [6.9, 4.6, 2.3]
    for i, (title, steps) in enumerate(columns):
        x = .3 + 5 * i
        flow_group(ax, x, 1.3, 4.4, 8.0, title)
        for j, (label, fill) in enumerate(steps):
            flow_box(ax, x+.38, ys[j], 3.64, 1.05, label, fill=fill,
                     fs=10, color="white" if fill == BLUE else INK)
            if j:
                flow_arrow(ax, [(x+2.2, ys[j-1]), (x+2.2, ys[j]+1.05)])
        if i < 4:
            flow_arrow(ax, [(x+4.02, 2.825), (x+4.68, 2.825),
                            (x+4.68, 7.425), (x+5.38, 7.425)])
    ax.text(12.5, .55, "若时序或链路检查不通过，重新调整悬停点、轮换安排或运输时刻。",
            ha="center", fontsize=10, color=MUTED)
    save(fig, "图11_第三问运输与通信联合调度流程图")


def load_nodes() -> tuple[dict, pd.DataFrame]:
    raw = pd.read_excel(NODE_PATH, sheet_name="数据", header=None)
    center = raw.iloc[2, :5].tolist()
    origin = {
        "编号": str(center[0]), "名称": str(center[1]),
        "经度": float(center[2]), "纬度": float(center[3]), "海拔": float(center[4]),
    }
    services = raw.iloc[6:21, :6].copy()
    services.columns = ["编号", "名称", "经度", "纬度", "海拔", "保障人口"]
    for column in ["经度", "纬度", "海拔", "保障人口"]:
        services[column] = pd.to_numeric(services[column])
    return origin, services.reset_index(drop=True)


def load_dem() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    source = loadmat(DEM_PATH)
    dem = np.asarray(source["dem"], dtype=float)
    lat = np.asarray(source["latitude"], dtype=float).ravel()
    lon = np.asarray(source["longitude"], dtype=float).ravel()
    nodata = float(np.asarray(source["nodata"]).ravel()[0])
    dem[dem == nodata] = np.nan
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        dem = dem[::-1, :]
    if lon[0] > lon[-1]:
        lon = lon[::-1]
        dem = dem[:, ::-1]
    return dem, lat, lon


def local_xy(lon, lat, lon0, lat0):
    x = (np.asarray(lon) - lon0) * 111.320 * np.cos(np.deg2rad(lat0))
    y = (np.asarray(lat) - lat0) * 110.574
    return x, y


def route_cruise_height(
    relay_lon: float,
    relay_lat: float,
    hover_z: float,
    origin: dict,
    interpolator: RegularGridInterpolator,
) -> float:
    lon_a, lat_a, lon_b, lat_b = np.radians([origin["经度"], origin["纬度"], relay_lon, relay_lat])
    hav = np.sin((lat_b-lat_a)/2)**2 + np.cos(lat_a)*np.cos(lat_b)*np.sin((lon_b-lon_a)/2)**2
    distance = 6371008.8 * 2 * np.arcsin(np.sqrt(hav))
    samples = np.linspace(0.0, 1.0, max(2, int(np.ceil(distance/5.0))+1))
    line_lon = origin["经度"] + samples * (relay_lon - origin["经度"])
    line_lat = origin["纬度"] + samples * (relay_lat - origin["纬度"])
    terrain = interpolator(np.c_[line_lat, line_lon])
    return max(float(np.nanmax(terrain)) + 50.0, hover_z)


def plot_terrain_routes(q3: dict) -> None:
    origin, services = load_nodes()
    dem, lat, lon = load_dem()
    missions = q3["中继架次"]

    all_lon = np.r_[
        origin["经度"], services["经度"].to_numpy(),
        [mission["经度"] for mission in missions],
    ]
    all_lat = np.r_[
        origin["纬度"], services["纬度"].to_numpy(),
        [mission["纬度"] for mission in missions],
    ]
    lon_min, lon_max = all_lon.min() - 0.018, all_lon.max() + 0.018
    lat_min, lat_max = all_lat.min() - 0.016, all_lat.max() + 0.016
    col = (lon >= lon_min) & (lon <= lon_max)
    row = (lat >= lat_min) & (lat <= lat_max)
    lon_c, lat_c = lon[col], lat[row]
    dem_c = dem[np.ix_(row, col)]

    lon0, lat0 = origin["经度"], origin["纬度"]
    x_c, _ = local_xy(lon_c, np.full_like(lon_c, lat0), lon0, lat0)
    _, y_c = local_xy(np.full_like(lat_c, lon0), lat_c, lon0, lat0)
    x_grid, y_grid = np.meshgrid(x_c, y_c)

    interpolator = RegularGridInterpolator((lat, lon), dem, method="nearest", bounds_error=False, fill_value=np.nan)
    origin_ground = float(origin["海拔"])
    service_ground = interpolator(
        np.c_[services["纬度"].to_numpy(), services["经度"].to_numpy()]
    )
    sx, sy = local_xy(
        services["经度"].to_numpy(), services["纬度"].to_numpy(), lon0, lat0
    )

    terrain_cmap = LinearSegmentedColormap.from_list(
        "paper_terrain",
        ["#214f78", "#3f7da3", "#72abc1", "#add1c8", "#e6dfaa", "#f3d793"],
        N=256,
    )
    valid = dem_c[np.isfinite(dem_c)]
    vmin, vmax = np.percentile(valid, [1.5, 98.5])
    norm = Normalize(vmin=vmin, vmax=vmax)
    light = LightSource(azdeg=315, altdeg=42)
    rgb = light.shade(dem_c, cmap=terrain_cmap, norm=norm, vert_exag=0.65, blend_mode="soft")

    fig = plt.figure(figsize=(14.6, 8.7), dpi=180)
    ax = fig.add_subplot(111, projection="3d")
    ax.computed_zorder = False
    step = max(1, int(max(dem_c.shape) / 260))
    surface = ax.plot_surface(
        x_grid[::step, ::step], y_grid[::step, ::step], dem_c[::step, ::step],
        facecolors=rgb[::step, ::step], linewidth=0, antialiased=True,
        shade=False, rcount=260, ccount=260, alpha=0.75, zorder=0,
    )
    # Matplotlib 3.3 predates computed_zorder=False. Project terrain normally,
    # then sort this translucent context surface behind the highlighted routes.
    if tuple(int(x) for x in mpl.__version__.split('.')[:2]) < (3, 5):
        original_projection = surface.do_3d_projection
        def project_context_surface(*args, **kwargs):
            original_projection(*args, **kwargs)
            return float('inf')
        surface.do_3d_projection = project_context_surface
    floor_z = max(0.0, float(np.nanmin(dem_c)) - 45.0)
    contour_levels = np.arange(
        np.floor(vmin / 100) * 100, np.ceil(vmax / 100) * 100 + 1, 100
    )
    ax.contour(
        x_grid[::step, ::step], y_grid[::step, ::step], dem_c[::step, ::step],
        levels=contour_levels, zdir="z", offset=floor_z,
        colors="#718695", linewidths=0.34, alpha=0.38,
    )

    for code, x, y, z in zip(services["编号"], sx, sy, service_ground):
        region = SERVICE_REGIONS.get(str(code))
        color = REGION_COLORS.get(region, "#8B969E")
        ax.scatter([x], [y], [z + 28], s=24, color=color, edgecolor="white", linewidth=0.7, zorder=5)
        ax.text(
            x, y, z + 55, str(code), fontsize=6.9, ha="center", va="bottom",
            color=INK, bbox=dict(boxstyle="round,pad=0.08", fc="white", ec="none", alpha=0.65),
            zorder=7,
        )

    gateway_z = origin_ground + 20.0
    ax.scatter([0], [0], [origin_ground + 12], marker="*", s=150, color="#941818",
               edgecolor="white", linewidth=0.9, zorder=9)
    ax.plot([0, 0], [0, 0], [origin_ground, gateway_z], color="#781616", linewidth=2.0, zorder=8)
    ax.scatter([0], [0], [gateway_z], marker="s", s=48, color="#30343A",
               edgecolor="white", linewidth=0.8, zorder=9)

    for mission in missions:
        region = mission["服务区域"]
        color = REGION_COLORS[region]
        relay_x, relay_y = local_xy(mission["经度"], mission["纬度"], lon0, lat0)
        relay_x, relay_y = float(relay_x), float(relay_y)
        hover_z = float(mission["悬停海拔_m"])
        ground_z = float(mission["地面高程_m"])
        cruise_z = route_cruise_height(
            float(mission["经度"]), float(mission["纬度"]), hover_z, origin, interpolator
        )

        path_x = [0.0, 0.0, relay_x, relay_x]
        path_y = [0.0, 0.0, relay_y, relay_y]
        path_z = [origin_ground, cruise_z, cruise_z, hover_z]
        ax.plot(path_x, path_y, path_z, color=color, linewidth=2.6, zorder=8)
        # Inbound and outbound traces coincide geometrically: no artificial offset.
        ax.plot(path_x[::-1], path_y[::-1], path_z[::-1], color="white",
                linewidth=.8, linestyle=(0, (4, 5)), zorder=9)
        ax.quiver(relay_x*.32, relay_y*.32, cruise_z,
                  -relay_x*.12, -relay_y*.12, 0, color=color,
                  linewidth=1.8, arrow_length_ratio=.35, zorder=10)
        distance = float(np.hypot(relay_x, relay_y)) * 1000
        # Compare reconstructed climb/cruise/descent timing with final results.
        la, pa, lb, pb = np.radians([origin["经度"], origin["纬度"], mission["经度"], mission["纬度"]])
        hav = np.sin((pb-pa)/2)**2 + np.cos(pa)*np.cos(pb)*np.sin((lb-la)/2)**2
        distance = 6371008.8 * 2 * np.arcsin(np.sqrt(hav))
        out_time = (cruise_z-origin_ground)/4 + distance/15 + (cruise_z-hover_z)/3
        assert abs(out_time-mission["去程时间_s"]) < .05, (region, out_time, mission["去程时间_s"])

        arrow_start = 0.53
        arrow_delta = 0.13
        ax.quiver(
            relay_x * arrow_start, relay_y * arrow_start, cruise_z,
            relay_x * arrow_delta, relay_y * arrow_delta, 0,
            color=color, linewidth=1.9, arrow_length_ratio=0.32,
            normalize=False, zorder=10,
        )

        ax.plot(
            [relay_x, relay_x], [relay_y, relay_y], [ground_z, hover_z],
            color=color, linewidth=1.2, linestyle=(0, (3, 2)), alpha=0.85, zorder=7,
        )
        ax.scatter(
            [relay_x], [relay_y], [hover_z], marker="D", s=62,
            color=color, edgecolor="white", linewidth=1.0, zorder=10,
        )
        ax.plot(
            [relay_x, 0.0], [relay_y, 0.0], [hover_z, gateway_z],
            color="#4F5962", linewidth=0.9, linestyle=(0, (3, 3)), alpha=0.72, zorder=6,
        )

    ax.set_title("第三问四个中继架次的三维地形与往返航迹", loc="left", pad=15,
                 fontsize=15.5, weight="bold")
    ax.text2D(
        0.0, 0.965,
        "彩色航迹上的双向箭头表示往返；去返程空间重合。灰色虚线表示回传链路。",
        transform=ax.transAxes, fontsize=9.4, color=MUTED,
    )
    ax.set_xlabel("东西方向 / km", labelpad=9)
    ax.set_ylabel("南北方向 / km", labelpad=9)
    ax.set_zlabel("海拔 / m", labelpad=7)
    ax.set_zlim(floor_z, max(float(np.nanmax(dem_c)), max(m["悬停海拔_m"] for m in missions)) + 120)
    ax.view_init(elev=61, azim=-66)
    ax.set_box_aspect((np.ptp(x_c), np.ptp(y_c), np.ptp(dem_c) / 145))
    label_offsets = {'中央': (48, 32), '西部': (-62,-8), '东部': (48,20), '北部': (20,42)}
    for mission in missions:
        region = mission['服务区域']
        px, py = local_xy(mission['经度'], mission['纬度'], lon0, lat0)
        pz = mission['悬停海拔_m']
        u, v, _ = proj3d.proj_transform(px, py, pz, ax.get_proj())
        dx, dy = label_offsets[region]
        text_color = '#927017' if region == '西部' else REGION_COLORS[region]
        ax.annotate(f"{mission['中继架次']}  {region}\n悬停海拔 {pz:.0f} m", (u,v),
                    xytext=(dx,dy), textcoords='offset points', ha='center', fontsize=8.6,
                    color=text_color, weight='bold',
                    bbox=dict(boxstyle='round,pad=.28',fc='white',ec=REGION_COLORS[region],alpha=1),
                    arrowprops=dict(arrowstyle='-',color=REGION_COLORS[region],lw=.8),zorder=1000)
        cz = route_cruise_height(mission['经度'],mission['纬度'],pz,origin,interpolator)
        for a,b in [(.54,.70),(.35,.20)]:
            a1,a2,_ = proj3d.proj_transform(px*a,py*a,cz,ax.get_proj())
            b1,b2,_ = proj3d.proj_transform(px*b,py*b,cz,ax.get_proj())
            ax.annotate('',(b1,b2),xytext=(a1,a2),arrowprops=dict(arrowstyle='-|>',
                        mutation_scale=15,color=REGION_COLORS[region],lw=1.8),zorder=900)
    u,v,_ = proj3d.proj_transform(0,0,gateway_z,ax.get_proj())
    ax.annotate('O01 / G01',(u,v),xytext=(14,-26),textcoords='offset points',fontsize=9,
                color='#781616',weight='bold',bbox=dict(fc='white',ec='none',alpha=1),
                arrowprops=dict(arrowstyle='-',color='#781616',lw=.8),zorder=1000)
    for text in ax.texts:
        text.set_zorder(1000)
    for line in ax.lines:
        line.set_zorder(100)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.97, 0.98, 0.985, 0.55))
        axis.pane.set_edgecolor((0.75, 0.78, 0.80, 0.45))
    ax.grid(True, linewidth=0.35, alpha=0.38)

    handles = [
        Line2D([0], [0], color=REGION_COLORS[r], linewidth=2.5, label=f"{m}  {r}")
        for r, m in [("中央", "R-M01"), ("东部", "R-M02"), ("西部", "R-M03"), ("北部", "R-M04")]
    ]
    handles.extend(
        [
            Line2D([0], [0], marker="*", color="none", markerfacecolor="#941818",
                   markeredgecolor="white", markersize=11, label="调度中心 O01"),
            Line2D([0], [0], marker="s", color="none", markerfacecolor="#30343A",
                   markeredgecolor="white", markersize=7, label="固定网关 G01"),
            Line2D([0], [0], color="#4F5962", linewidth=1.0, linestyle=(0, (3, 3)),
                   label="回传链路"),
        ]
    )
    ax.legend(
        handles=handles, loc="upper right", bbox_to_anchor=(0.98, 0.91),
        frameon=True, facecolor="white", framealpha=0.88,
        edgecolor="#C8CED3", fontsize=8.0, ncol=1,
    )
    fig.text(
        0.5, 0.035,
        "注：航迹巡航海拔取沿线最高地形以上50 m与悬停海拔的较大值；服务区颜色表示其所属通信保障区域，灰色节点为全程直连服务区。",
        ha="center", fontsize=8.6, color=MUTED,
    )
    save(fig, "图12_第三问三维地形与中继航迹")


def plot_relay_gantt(q3: dict) -> None:
    missions = sorted(q3["中继架次"], key=lambda row: (row["中继无人机"], row["准备开始_s"]))
    gap_ranges = q3["区域缺口时间范围"]
    y_map = {"R01": 1, "R02": 0}
    phase_colors = {
        "准备": "#B7C0C7",
        "飞往悬停点": "#C9DDE8",
        "建链": "#F3DEA0",
        "通信服务": None,
        "返航": "#7E8E99",
        "周转": "#D8DEE2",
    }

    fig, ax = plt.subplots(figsize=(12.4, 6.6), dpi=180)
    row_height = 0.46
    for mission in missions:
        y = y_map[mission["中继无人机"]]
        region = mission["服务区域"]
        color = REGION_COLORS[region]
        phases = [
            ("准备", mission["准备开始_s"], mission["起飞_s"]),
            ("飞往悬停点", mission["起飞_s"], mission["到达悬停点_s"]),
            ("建链", mission["到达悬停点_s"], mission["建链完成_服务开始_s"]),
            ("通信服务", mission["建链完成_服务开始_s"], mission["服务结束_s"]),
            ("返航", mission["服务结束_s"], mission["返回O01_s"]),
        ]
        for phase, start, end in phases:
            face = color if phase == "通信服务" else phase_colors[phase]
            alpha = 0.90 if phase == "通信服务" else 0.95
            hatch = "///" if phase == "建链" else None
            ax.barh(
                y, (end - start) / 3600.0, left=start / 3600.0,
                height=row_height, color=face, edgecolor="white",
                linewidth=0.85, alpha=alpha, hatch=hatch, zorder=3,
            )

        service_mid = (mission["建链完成_服务开始_s"] + mission["服务结束_s"]) / 7200.0
        ax.text(
            service_mid, y + 0.02, f"{mission['中继架次']}  {region}",
            ha="center", va="center", fontsize=8.7, weight="bold",
            color="white" if region in ("中央", "东部", "北部") else INK,
            zorder=5,
        )

        gap = gap_ranges[region]
        gap_start = gap["最早缺口_s"] / 3600.0
        gap_end = gap["最晚缺口结束_s"] / 3600.0
        ax.plot(
            [gap_start, gap_end], [y - 0.34, y - 0.34],
            color=color, linewidth=5.0, alpha=0.42,
            solid_capstyle="butt", zorder=2,
        )
        ax.scatter(
            [mission["建链完成_服务开始_s"] / 3600.0], [y + 0.30],
            marker="v", s=30, color=color, edgecolor="white", linewidth=0.6, zorder=6,
        )

    by_drone = {drone: [m for m in missions if m["中继无人机"] == drone] for drone in y_map}
    for drone, rows in by_drone.items():
        rows = sorted(rows, key=lambda row: row["准备开始_s"])
        if len(rows) > 1:
            start = rows[0]["返回O01_s"] / 3600.0
            end = rows[1]["准备开始_s"] / 3600.0
            ax.barh(
                y_map[drone], end - start, left=start, height=row_height,
                color=phase_colors["周转"], edgecolor="white", linewidth=0.8,
                hatch="..", zorder=3,
            )
            ax.text((start + end) / 2, y_map[drone], "周转", ha="center", va="center",
                    fontsize=7.6, color=MUTED, zorder=5)

    finish_h = q3["指标汇总"]["联合任务完成时间_s"] / 3600.0
    ax.axvline(finish_h, color="#D85852", linestyle="--", linewidth=1.25, zorder=2)
    ax.text(
        finish_h - 0.015, 1.52, "联合任务完成\n8277.90 s",
        ha="right", va="top", fontsize=8.7, color="#D85852",
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.82, pad=1.0),
    )
    ax.set_xlim(0, finish_h)
    ax.set_ylim(-0.62, 1.65)
    ax.set_yticks([1, 0])
    ax.set_yticklabels(["R01", "R02"])
    ax.set_xlabel("任务时间 / h")
    ax.set_ylabel("中继无人机")
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_title("两架中继无人机的四区域轮换调度", loc="left", fontsize=16,
                 fontweight="bold", pad=22)
    ax.text(
        0, 1.03,
        "条带表示准备、飞行、建链、通信服务和返航；下方粗线表示对应区域的直连缺口时间范围。",
        transform=ax.transAxes, ha="left", va="bottom", fontsize=9.5, color=MUTED,
    )

    legend = [
        mpl.patches.Patch(facecolor=REGION_COLORS[region], edgecolor="white", label=region)
        for region in ["中央", "东部", "西部", "北部"]
    ]
    legend.extend(
        [
            mpl.patches.Patch(facecolor="#B7C0C7", edgecolor="white", label="准备"),
            mpl.patches.Patch(facecolor="#C9DDE8", edgecolor="white", label="去程飞行"),
            mpl.patches.Patch(facecolor="#F3DEA0", edgecolor="white", hatch="///", label="建链"),
            mpl.patches.Patch(facecolor="#7E8E99", edgecolor="white", label="返航"),
        ]
    )
    ax.legend(handles=legend, frameon=False, ncol=4, loc="upper left", bbox_to_anchor=(0, 1.01),
              fontsize=8.2, columnspacing=1.0, handlelength=1.5)
    ax.text(
        0.995, 0.02, "▼ 建链完成时刻",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=8.2, color=MUTED,
    )
    save(fig, "图13_第三问中继无人机轮换调度甘特图")


def plot_link_sensitivity(sensitivity: dict) -> None:
    fig, ax = plt.subplots(figsize=(11.8, 6.8), dpi=180)
    first_failure = {}
    for region_row in sensitivity["区域结果"]:
        region = region_row["服务区域"]
        total = float(region_row["直连缺口样本数"])
        scenarios = region_row["附加损耗情景"]
        losses = np.array([row["额外损耗_dB"] for row in scenarios], dtype=float)
        counts = np.array([row["失去中继覆盖样本数"] for row in scenarios], dtype=float)
        ratios = counts / total * 100.0
        margin = float(region_row["最小双段裕量_dB"])
        ax.plot(
            losses, ratios, marker="o", markersize=6.2, linewidth=2.2,
            color=REGION_COLORS[region],
            label=f"{region}（基准最小裕量 {margin:.3f} dB）", zorder=3,
        )
        positive = np.flatnonzero(counts > 0)
        if len(positive):
            idx = int(positive[0])
            first_failure[region] = (losses[idx], ratios[idx], int(counts[idx]))

    annotations = {
        "北部": (8, 10),
        "中央": (8, 9),
        "西部": (-8, 12),
    }
    for region, (x, y, count) in first_failure.items():
        dx, dy = annotations.get(region, (7, 7))
        ax.annotate(
            f"{region}：{count}个样本\n失去覆盖",
            (x, y), xytext=(dx, dy), textcoords="offset points",
            ha="left" if dx >= 0 else "right", va="bottom", fontsize=8.6,
            color=REGION_COLORS[region],
            arrowprops=dict(arrowstyle="-", color=REGION_COLORS[region], linewidth=0.8),
        )

    ax.axvline(0.1, color="#87939C", linewidth=0.9, linestyle=(0, (3, 3)), zorder=1)
    ax.text(0.105, 36.8, "0.1 dB压力情景", ha="left", va="top", fontsize=8.5, color=MUTED)
    ax.set_xlim(-0.02, 1.05)
    ax.set_ylim(0, 38)
    ax.set_xticks([0, 0.1, 0.25, 0.5, 1.0])
    ax.set_xticklabels(["0", "0.10", "0.25", "0.50", "1.00"])
    ax.set_xlabel("中继接入与回传链路的额外传播损耗 / dB")
    ax.set_ylabel("失去中继覆盖的缺口样本比例 / %")
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, loc="upper left", fontsize=8.7, bbox_to_anchor=(0, 0.93))
    ax.set_title("附加链路损耗对中继覆盖的影响", loc="left", fontsize=16,
                 fontweight="bold", pad=22)
    ax.text(
        0, 1.03,
        "固定缺口、航线、位置和时序；仅增加中继链路损耗，连线用于指示已计算情景。",
        transform=ax.transAxes, ha="left", va="bottom", fontsize=9.5, color=MUTED,
    )
    save(fig, "图14_第三问中继链路损耗敏感性")


def plot_relay_energy(q3: dict) -> None:
    rows = q3["中继架次"]
    flight = np.array([row["往返飞行能耗_kWh"] for row in rows], dtype=float)
    hover = np.array([row["悬停通信能耗_kWh"] for row in rows], dtype=float)
    total = np.array([row["总能耗_kWh"] for row in rows], dtype=float)
    assert np.allclose(flight + hover, total)
    assert np.isclose(total.sum(), q3["指标汇总"]["中继能耗_kWh"])
    protected = [len(row["保障运输架次"].split(", ")) for row in rows]

    fig, ax = plt.subplots(figsize=(11.8, 6.8), dpi=180)
    fig.subplots_adjust(left=.11, right=.96, bottom=.18, top=.79)
    x = np.arange(len(rows))
    ax.bar(x, flight, width=.58, color="#AFC9D8", edgecolor="white",
           linewidth=1.0, label="往返飞行能耗", zorder=3)
    ax.bar(x, hover, width=.58, bottom=flight,
           color=[REGION_COLORS[row["服务区域"]] for row in rows],
           edgecolor="white", linewidth=1.0, label="悬停通信能耗", zorder=3)
    for i, (f, h, t) in enumerate(zip(flight, hover, total)):
        ax.text(i, t+.035, f"{t:.3f}", ha="center", va="bottom",
                fontsize=10, fontweight="bold")
        ax.text(i, f+h/2, f"{100*h/t:.0f}%", ha="center", va="center",
                fontsize=9, color="white", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([
        f'{row["中继架次"]}\n{row["服务区域"]} · 保障{count}架次'
        for row, count in zip(rows, protected)
    ])
    ax.set_ylabel("中继能耗 / kWh")
    ax.set_ylim(0, max(total)*1.20)
    ax.grid(axis="y", color=GRID, linewidth=.8, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    handles = [
        mpl.patches.Patch(facecolor="#AFC9D8", edgecolor="white", label="往返飞行能耗"),
        mpl.patches.Patch(facecolor="#4E79A7", edgecolor="white", label="悬停通信能耗（颜色对应区域）"),
    ]
    ax.legend(handles=handles, frameon=False, ncol=2, loc="upper left",
              bbox_to_anchor=(0, 1.02))
    fig.suptitle("四个中继架次的能耗构成", x=.11, y=.965,
                 ha="left", fontsize=17, fontweight="bold")
    fig.text(.11, .905, "柱顶为总能耗；柱内百分数为悬停通信能耗占该架次总能耗的比例。",
             fontsize=10, color=MUTED)
    fig.text(.11, .055,
             f'四个中继架次合计耗能{total.sum():.3f} kWh；悬停通信是各架次的主要能耗来源。',
             fontsize=9.5, color=MUTED)
    save(fig, "图23_第三问中继架次能耗构成")


def plot_link_margins(q3: dict) -> None:
    rows = q3["通信保障汇总"]
    regions = [row["服务区域"] for row in rows]
    access = np.array([row["最小接入裕量_dB"] for row in rows], dtype=float)
    backhaul = np.array([row["回传裕量_dB"] for row in rows], dtype=float)
    minimum = np.array([row["最小双段裕量_dB"] for row in rows], dtype=float)
    assert np.allclose(np.minimum(access, backhaul), minimum)
    assert all(row["中断样本数"] == 0 for row in rows)

    fig, ax = plt.subplots(figsize=(11.8, 6.8), dpi=180)
    fig.subplots_adjust(left=.15, right=.96, bottom=.16, top=.77)
    y = np.arange(len(rows))[::-1]
    h = .28
    colors = [REGION_COLORS[region] for region in regions]
    ax.barh(y+h/2, access, height=h, color=colors, edgecolor="white",
            linewidth=1, label="运输无人机—中继：最小接入裕量", zorder=3)
    ax.barh(y-h/2, backhaul, height=h, color=colors, alpha=.35,
            edgecolor=colors, linewidth=1, hatch="///",
            label="中继—G01：回传裕量", zorder=2)
    for yy, a, b, m in zip(y, access, backhaul, minimum):
        endpoint_y = yy+h/2 if a <= b else yy-h/2
        ax.scatter([m], [endpoint_y], s=55, facecolor="white", edgecolor=INK,
                   linewidth=1.2, zorder=5)
        ax.annotate(f"瓶颈 {m:.3f} dB", (m, endpoint_y), xytext=(7, 0),
                    textcoords="offset points", va="center", fontsize=8.8,
                    color=INK, zorder=6)
    ax.set_yticks(y)
    ax.set_yticklabels([f'{row["服务区域"]} · {row["中继架次"]}' for row in rows])
    ax.set_xlim(0, 20.5)
    ax.set_xlabel("链路裕量 / dB")
    ax.grid(axis="x", color=GRID, linewidth=.8, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, ncol=2, loc="upper left", bbox_to_anchor=(0, 1.04),
              fontsize=9)
    fig.suptitle("四个中继区域的链路裕量比较", x=.15, y=.965,
                 ha="left", fontsize=17, fontweight="bold")
    fig.text(.15, .895,
             "白心标记为两段链路中的较小裕量；裕量大于0表示满足对应通信门限。",
             fontsize=10, color=MUTED)
    fig.text(.15, .055,
             "北部链路的最小裕量仅0.069 dB，是基准方案中最接近门限的区域；检查样本内四区中断数均为0。",
             fontsize=9.5, color=MUTED)
    save(fig, "图24_第三问中继链路裕量比较")


def _merge_communication_stages(stages: list[dict]) -> list[dict]:
    merged = []
    for row in sorted(stages, key=lambda item: item["开始时刻_s"]):
        key = (row["保障方式"], row["中继架次编号"])
        if merged and merged[-1]["key"] == key and abs(merged[-1]["end"]-row["开始时刻_s"]) < 1e-6:
            merged[-1]["end"] = row["结束时刻_s"]
        else:
            merged.append({"start": row["开始时刻_s"], "end": row["结束时刻_s"], "key": key})
    return merged


def plot_communication_timeline(q3: dict) -> None:
    details = q3["通信保障明细"]
    sorties = sorted({row["运输架次编号"] for row in details},
                     key=lambda item: int(item.split("-")[-1]))
    assert len(sorties) == q3["指标汇总"]["运输架次"] == 21
    relay_regions = {row["中继架次"]: row["服务区域"] for row in q3["中继架次"]}
    grouped = {sortie: [row for row in details if row["运输架次编号"] == sortie]
               for sortie in sorties}
    relayed = {sortie for sortie, rows in grouped.items()
               if any(row["保障方式"] == "空中中继" for row in rows)}
    assert len(relayed) == 17

    fig, ax = plt.subplots(figsize=(13.2, 9.4), dpi=180)
    fig.subplots_adjust(left=.11, right=.97, bottom=.12, top=.82)
    y_values = np.arange(len(sorties))[::-1]
    max_end = 0.0
    for y, sortie in zip(y_values, sorties):
        for stage in _merge_communication_stages(grouped[sortie]):
            start, end = stage["start"]/3600, stage["end"]/3600
            max_end = max(max_end, end)
            mode, relay = stage["key"]
            color = "#B7C0C7" if mode == "G01直连" else REGION_COLORS[relay_regions[relay]]
            ax.barh(y, end-start, left=start, height=.68, color=color,
                    edgecolor="white", linewidth=.65, zorder=3)
    ax.set_yticks(y_values)
    ax.set_yticklabels(sorties, fontsize=8.8)
    ax.set_xlim(0, max_end*1.03)
    ax.set_xlabel("任务时间 / h")
    ax.set_ylabel("运输架次")
    ax.grid(axis="x", color=GRID, linewidth=.8, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    handles = [mpl.patches.Patch(facecolor="#B7C0C7", edgecolor="white", label="G01直连")]
    handles.extend(mpl.patches.Patch(facecolor=REGION_COLORS[r], edgecolor="white",
                                    label=f"{r}中继")
                   for r in ["中央", "东部", "西部", "北部"])
    ax.legend(handles=handles, frameon=False, ncol=5, loc="upper left",
              bbox_to_anchor=(0, 1.02), fontsize=9)
    fig.suptitle("21个运输架次的通信保障时序", x=.11, y=.965,
                 ha="left", fontsize=17, fontweight="bold")
    fig.text(.11, .905,
             "灰色表示固定网关G01直连，彩色表示由相应区域的中继架次提供保障。",
             fontsize=10, color=MUTED)
    fig.text(.11, .045,
             "17个运输架次在部分飞行阶段需要空中中继；Q2-03、Q2-04、Q2-10和Q2-21全程保持G01直连。",
             fontsize=9.5, color=MUTED)
    save(fig, "图25_第三问运输架次通信保障时序")


def supplementary_figures(q3: dict) -> None:
    plot_relay_energy(q3)
    plot_link_margins(q3)
    plot_communication_timeline(q3)


def check_inputs() -> None:
    required = [Q3_PATH, SENSITIVITY_PATH, DEM_PATH, NODE_PATH]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少绘图输入文件：" + "、".join(missing))


def main() -> None:
    check_inputs()
    setup_style()
    q3 = load_json(Q3_PATH)
    sensitivity = load_json(SENSITIVITY_PATH)
    plot_flowchart()
    plot_terrain_routes(q3)
    plot_relay_gantt(q3)
    plot_link_sensitivity(sensitivity)
    supplementary_figures(q3)
    print(f"第三问图件已生成：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
