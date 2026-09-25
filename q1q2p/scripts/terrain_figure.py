from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, LightSource, Normalize
from matplotlib.lines import Line2D
from scipy.interpolate import RegularGridInterpolator
from scipy.io import loadmat


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PACKAGE_ROOT / "inputs"
DEM_PATH = INPUT_DIR / "镇龙乡及周边30米DEM.mat"
NODE_PATH = INPUT_DIR / "调度中心与服务区.xlsx"
OUTPUT_DIR = PACKAGE_ROOT / "figures"


def configure_style() -> None:
    font_path = Path("C:/Windows/Fonts/simhei.ttf")
    if font_path.exists():
        mpl.font_manager.fontManager.addfont(str(font_path))
        mpl.rcParams["font.family"] = "SimHei"
    mpl.rcParams.update(
        {
            "axes.unicode_minus": False,
            "font.size": 9.5,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "axes.edgecolor": "#7d8790",
            "axes.linewidth": 0.7,
        }
    )


def load_nodes() -> tuple[dict, pd.DataFrame]:
    raw = pd.read_excel(NODE_PATH, sheet_name="数据", header=None)
    center = raw.iloc[2, :5].tolist()
    origin = {
        "编号": str(center[0]),
        "名称": str(center[1]),
        "经度": float(center[2]),
        "纬度": float(center[3]),
        "海拔": float(center[4]),
    }
    services = raw.iloc[6:21, :6].copy()
    services.columns = ["编号", "名称", "经度", "纬度", "海拔", "保障人口"]
    for col in ["经度", "纬度", "海拔", "保障人口"]:
        services[col] = pd.to_numeric(services[col])
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


def local_xy(lon: np.ndarray, lat: np.ndarray, lon0: float, lat0: float):
    x = (np.asarray(lon) - lon0) * 111.320 * np.cos(np.deg2rad(lat0))
    y = (np.asarray(lat) - lat0) * 110.574
    return x, y


def label_offsets() -> dict[str, tuple[float, float]]:
    return {
        "S001": (0.12, 0.20), "S002": (0.12, 0.18), "S003": (-0.58, 0.18),
        "S004": (0.12, 0.20), "S005": (0.12, 0.18), "S006": (-0.55, -0.32),
        "S007": (-0.58, 0.15), "S008": (-0.50, 0.18), "S009": (0.12, 0.17),
        "S010": (0.12, -0.34), "S011": (-0.50, 0.16), "S012": (0.12, 0.16),
        "S013": (0.12, 0.18), "S014": (0.12, -0.35), "S015": (-0.55, 0.15),
    }


def main() -> None:
    configure_style()
    origin, services = load_nodes()
    dem, lat, lon = load_dem()

    node_lon = np.r_[origin["经度"], services["经度"].to_numpy()]
    node_lat = np.r_[origin["纬度"], services["纬度"].to_numpy()]
    lon_pad, lat_pad = 0.020, 0.018
    lon_min, lon_max = node_lon.min() - lon_pad, node_lon.max() + lon_pad
    lat_min, lat_max = node_lat.min() - lat_pad, node_lat.max() + lat_pad
    col = (lon >= lon_min) & (lon <= lon_max)
    row = (lat >= lat_min) & (lat <= lat_max)
    lon_c, lat_c = lon[col], lat[row]
    dem_c = dem[np.ix_(row, col)]

    lon0, lat0 = origin["经度"], origin["纬度"]
    x_c, _ = local_xy(lon_c, np.full_like(lon_c, lat0), lon0, lat0)
    _, y_c = local_xy(np.full_like(lat_c, lon0), lat_c, lon0, lat0)
    x_grid, y_grid = np.meshgrid(x_c, y_c)
    sx, sy = local_xy(services["经度"].to_numpy(), services["纬度"].to_numpy(), lon0, lat0)

    elev = RegularGridInterpolator((lat, lon), dem, bounds_error=False, fill_value=np.nan)
    oz_ground = float(elev([[origin["纬度"], origin["经度"]]])[0])
    sz_ground = elev(np.c_[services["纬度"], services["经度"]])

    terrain_cmap = LinearSegmentedColormap.from_list(
        "paper_terrain",
        ["#214f78", "#3f7da3", "#72abc1", "#add1c8", "#e6dfaa", "#f3d793"],
        N=256,
    )
    z_valid = dem_c[np.isfinite(dem_c)]
    vmin, vmax = np.percentile(z_valid, [1.5, 98.5])
    norm = Normalize(vmin=vmin, vmax=vmax)
    light = LightSource(azdeg=315, altdeg=42)
    rgb = light.shade(dem_c, cmap=terrain_cmap, norm=norm, vert_exag=0.65, blend_mode="soft")

    fig = plt.figure(figsize=(15.8, 7.4), dpi=180)
    grid = fig.add_gridspec(1, 2, width_ratios=[1.28, 1.0], wspace=0.08)
    ax3d = fig.add_subplot(grid[0, 0], projection="3d")
    ax2d = fig.add_subplot(grid[0, 1])

    step = max(1, int(max(dem_c.shape) / 260))
    ax3d.plot_surface(
        x_grid[::step, ::step], y_grid[::step, ::step], dem_c[::step, ::step],
        facecolors=rgb[::step, ::step], linewidth=0, antialiased=True, shade=False,
        rcount=260, ccount=260, alpha=0.72,
    )
    contour_levels = np.arange(np.floor(vmin / 100) * 100, np.ceil(vmax / 100) * 100 + 1, 100)
    floor_z = max(0, np.nanmin(dem_c) - 45)
    ax3d.contour(
        x_grid[::step, ::step], y_grid[::step, ::step], dem_c[::step, ::step],
        levels=contour_levels, zdir="z", offset=floor_z, colors="#718695",
        linewidths=0.35, alpha=0.38,
    )

    marker_lift = 62.0
    for code, x, y, z in zip(services["编号"], sx, sy, sz_ground):
        ax3d.plot(
            [x], [y], [z + marker_lift], marker="o", markersize=6.2,
            color="#ef4b38", markeredgecolor="white", markeredgewidth=1.0,
        )
        ax3d.text(
            x, y, z + marker_lift + 26, code, fontsize=7.4, weight="bold", color="#681b18",
            ha="center", va="bottom", bbox=dict(boxstyle="round,pad=0.10", fc="white", ec="none", alpha=0.72),
        )
    ax3d.plot(
        [0], [0], [oz_ground + marker_lift], marker="*", markersize=13.0,
        color="#941818", markeredgecolor="white", markeredgewidth=1.0,
    )
    ax3d.text(
        0, 0, oz_ground + marker_lift + 28, "O01", fontsize=8.5, weight="bold", color="#781616", ha="center",
        bbox=dict(boxstyle="round,pad=0.10", fc="white", ec="none", alpha=0.75),
    )

    ax3d.set_title("a  三维地形与服务区空间分布", loc="left", pad=8, weight="bold")
    ax3d.set_xlabel("东西方向 / km", labelpad=8)
    ax3d.set_ylabel("南北方向 / km", labelpad=8)
    ax3d.set_zlabel("高程 / m", labelpad=6)
    ax3d.set_zlim(floor_z, np.nanmax(dem_c) + 90)
    ax3d.view_init(elev=52, azim=-58)
    ax3d.set_box_aspect((np.ptp(x_c), np.ptp(y_c), np.ptp(dem_c) / 125))
    for axis in (ax3d.xaxis, ax3d.yaxis, ax3d.zaxis):
        axis.pane.set_facecolor((0.97, 0.98, 0.985, 0.55))
        axis.pane.set_edgecolor((0.75, 0.78, 0.80, 0.45))
    ax3d.grid(True, linewidth=0.35, alpha=0.40)

    ax2d.imshow(
        rgb, extent=[x_c.min(), x_c.max(), y_c.min(), y_c.max()],
        origin="lower", interpolation="bilinear", aspect="equal",
    )
    ax2d.contour(x_grid, y_grid, dem_c, levels=contour_levels, colors="white", linewidths=0.35, alpha=0.40)
    ax2d.scatter(sx, sy, s=34, color="#ef6a4c", edgecolor="white", linewidth=0.8, zorder=6)
    ax2d.scatter([0], [0], marker="*", s=170, color="#9d1f1f", edgecolor="white", linewidth=0.9, zorder=7)
    offsets = label_offsets()
    for code, x, y in zip(services["编号"], sx, sy):
        dx, dy = offsets.get(code, (0.10, 0.15))
        ax2d.text(
            x + dx, y + dy, code, fontsize=8.1, color="#4a2220", weight="bold",
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.58), zorder=8,
        )
    ax2d.text(
        0.18, -0.34, "O01", fontsize=9.2, color="#781616", weight="bold",
        bbox=dict(boxstyle="round,pad=0.14", fc="white", ec="none", alpha=0.68), zorder=8,
    )
    ax2d.set_title("b  服务区俯视分布", loc="left", pad=8, weight="bold")
    ax2d.set_xlabel("东西方向 / km（以O01为原点）")
    ax2d.set_ylabel("南北方向 / km（以O01为原点）")
    ax2d.grid(color="white", linewidth=0.45, alpha=0.35)
    ax2d.set_xlim(x_c.min(), x_c.max())
    ax2d.set_ylim(y_c.min(), y_c.max())
    ax2d.set_aspect("equal", adjustable="box")

    legend = [
        Line2D([0], [0], marker="*", markersize=11, linestyle="", markerfacecolor="#9d1f1f", markeredgecolor="white", label="临时调度中心 O01"),
        Line2D([0], [0], marker="o", markersize=6.5, linestyle="", markerfacecolor="#ef6a4c", markeredgecolor="white", label="服务区 S001–S015"),
    ]
    ax2d.legend(handles=legend, loc="lower right", frameon=True, facecolor="white", framealpha=0.86, edgecolor="#c8ced3", fontsize=8.2)

    fig.suptitle("研究区域三维地形与服务区空间分布", fontsize=16, weight="bold", y=0.965)
    fig.text(
        0.5, 0.055,
        "注：高程来自30 m DEM；节点位置依据调度中心与服务区坐标标注。",
        ha="center", va="center", fontsize=8.7, color="#4f5962",
    )
    sm = mpl.cm.ScalarMappable(norm=norm, cmap=terrain_cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=[ax3d, ax2d], orientation="horizontal", fraction=0.035, pad=0.10, aspect=55)
    cbar.set_label("地面高程 / m", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    cbar.outline.set_linewidth(0.6)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    png = OUTPUT_DIR / "图1_研究区域三维地形与服务区空间分布.png"
    pdf = OUTPUT_DIR / "图1_研究区域三维地形与服务区空间分布.pdf"
    svg = OUTPUT_DIR / "图1_研究区域三维地形与服务区空间分布.svg"
    fig.savefig(png, dpi=320, bbox_inches="tight", pad_inches=0.12)
    fig.savefig(pdf, bbox_inches="tight", pad_inches=0.12)
    fig.savefig(svg, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    print(png)
    print(pdf)
    print(svg)


if __name__ == "__main__":
    main()
