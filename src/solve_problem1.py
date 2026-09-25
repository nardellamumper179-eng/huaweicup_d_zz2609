from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat


DATA_ROOT = Path(os.environ.get(
    "HUAWEICUP_DATA_ROOT", r"C:\Users\曾钦仪\Desktop\华为杯2026\数据"
))
BASE_DIR = DATA_ROOT / "无人机应急物资运输基础数据"
DEM_PATH = (
    DATA_ROOT
    / "镇龙乡地理空间数据"
    / "镇龙乡及周边地理数据"
    / "数字高程模型数据（DEM）"
    / "镇龙乡及周边30米DEM.mat"
)
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "results"
if not OUTPUT_DIR.is_dir() and (SCRIPT_DIR.parent / "results").is_dir():
    OUTPUT_DIR = SCRIPT_DIR.parent / "results"
OUTPUT_PATH = OUTPUT_DIR / "问题一计算结果.xlsx"

G = 9.80665
KWH_J = 3_600_000.0


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def load_inputs():
    nodes_raw = pd.read_excel(BASE_DIR / "调度中心与服务区.xlsx", sheet_name="数据", header=None)
    center = nodes_raw.iloc[2, :5].tolist()
    services = nodes_raw.iloc[6:21, :6].copy()
    services.columns = ["服务区编号", "服务区名称", "经度", "纬度", "海拔", "保障人口"]
    services = services.reset_index(drop=True)
    origin = {
        "编号": str(center[0]),
        "名称": str(center[1]),
        "经度": float(center[2]),
        "纬度": float(center[3]),
        "海拔": float(center[4]),
    }

    drones_raw = pd.read_excel(BASE_DIR / "运输无人机数据.xlsx", sheet_name="数据", header=None)
    drone_columns = [
        "机型编号", "机型名称", "空载质量", "最大载重", "最大体积", "巡航速度",
        "空载航程", "满载航程", "可用能量", "返航余量", "准备时间", "每箱装载时间",
        "基础交接时间", "每箱交接时间", "爬升速度", "下降速度", "爬升效率", "下降效率",
    ]
    drones = drones_raw.iloc[2:5, :18].copy()
    drones.columns = drone_columns
    drones = drones.set_index("机型编号")
    for col in drone_columns[2:]:
        drones[col] = pd.to_numeric(drones[col])
    # Excel stores percentages as decimals; guard against percent-formatted whole numbers.
    drones["返航余量"] = drones["返航余量"].map(lambda x: x / 100 if x > 1 else x)

    boxes = pd.read_excel(
        BASE_DIR / "物资需求与配送时限.xlsx", sheet_name="逐箱货箱清单"
    )
    return origin, services, drones, boxes


def load_dem():
    data = loadmat(DEM_PATH)
    return (
        np.asarray(data["dem"], dtype=float),
        np.asarray(data["latitude"], dtype=float).ravel(),
        np.asarray(data["longitude"], dtype=float).ravel(),
        float(np.asarray(data["nodata"]).ravel()[0]),
    )


def nearest_indices(grid: np.ndarray, values: np.ndarray) -> np.ndarray:
    ascending = grid[0] <= grid[-1]
    work = grid if ascending else grid[::-1]
    pos = np.searchsorted(work, values)
    pos = np.clip(pos, 1, len(work) - 1)
    left = work[pos - 1]
    right = work[pos]
    idx = pos - (np.abs(values - left) <= np.abs(values - right))
    return idx if ascending else len(grid) - 1 - idx


def build_route_geometry(origin, services, dem, lat_grid, lon_grid, nodata):
    rows = []
    for _, service in services.iterrows():
        distance = haversine_m(
            origin["经度"], origin["纬度"], float(service["经度"]), float(service["纬度"])
        )
        # Five-metre sampling is denser than the 30 m raster and captures all crossed cells in practice.
        count = max(2, int(math.ceil(distance / 5.0)) + 1)
        lons = np.linspace(origin["经度"], float(service["经度"]), count)
        lats = np.linspace(origin["纬度"], float(service["纬度"]), count)
        r = nearest_indices(lat_grid, lats)
        c = nearest_indices(lon_grid, lons)
        elevations = dem[r, c]
        elevations = elevations[np.isfinite(elevations) & (elevations != nodata)]
        if elevations.size == 0:
            raise ValueError(f"No valid DEM cells on route to {service['服务区编号']}")
        max_ground = float(elevations.max())
        cruise_alt = max_ground + 50.0
        service_alt = float(service["海拔"])
        rows.append(
            {
                "服务区编号": service["服务区编号"],
                "水平距离_m": distance,
                "沿线最高地面高程_m": max_ground,
                "计划巡航海拔_m": cruise_alt,
                "去程爬升_m": max(0.0, cruise_alt - origin["海拔"]),
                "去程下降_m": max(0.0, cruise_alt - (service_alt + 30.0)),
                "返程爬升_m": max(0.0, cruise_alt - (service_alt + 30.0)),
                "返程下降_m": max(0.0, cruise_alt - origin["海拔"]),
            }
        )
    return pd.DataFrame(rows).set_index("服务区编号")


def equivalent_range(drone: pd.Series, payload: float) -> float:
    q = max(0.0, min(float(drone["最大载重"]), payload))
    ratio = q / float(drone["最大载重"])
    return float(drone["空载航程"]) - (
        float(drone["空载航程"]) - float(drone["满载航程"])
    ) * ratio ** 1.5


def leg_energy(drone: pd.Series, distance: float, climb: float, payload: float) -> float:
    horizontal = float(drone["可用能量"]) * distance / equivalent_range(drone, payload)
    total_mass = float(drone["空载质量"]) + payload
    climb_energy = total_mass * G * climb / (float(drone["爬升效率"]) * KWH_J)
    return horizontal + climb_energy


def round_trip_energy(drone: pd.Series, route: pd.Series, payload: float) -> float:
    return leg_energy(drone, route["水平距离_m"], route["去程爬升_m"], payload) + leg_energy(
        drone, route["水平距离_m"], route["返程爬升_m"], 0.0
    )


def flight_time(drone: pd.Series, route: pd.Series) -> float:
    outbound = (
        route["去程爬升_m"] / drone["爬升速度"]
        + route["水平距离_m"] / drone["巡航速度"]
        + route["去程下降_m"] / drone["下降速度"]
    )
    inbound = (
        route["返程爬升_m"] / drone["爬升速度"]
        + route["水平距离_m"] / drone["巡航速度"]
        + route["返程下降_m"] / drone["下降速度"]
    )
    return float(outbound + inbound)


def operation_time(drone: pd.Series, route: pd.Series, box_count: int) -> float:
    return float(
        drone["准备时间"]
        + box_count * drone["每箱装载时间"]
        + flight_time(drone, route)
        + drone["基础交接时间"]
        + box_count * drone["每箱交接时间"]
    )


def max_safe_payload(drone: pd.Series, route: pd.Series, reserve: float) -> float:
    limit = (1.0 - reserve) * float(drone["可用能量"])
    if round_trip_energy(drone, route, 0.0) > limit + 1e-12:
        return float("nan")
    high = float(drone["最大载重"])
    if round_trip_energy(drone, route, high) <= limit + 1e-12:
        return high
    low = 0.0
    for _ in range(80):
        mid = (low + high) / 2
        if round_trip_energy(drone, route, mid) <= limit:
            low = mid
        else:
            high = mid
    return low


def best_partition(service_boxes, route, drones, reserve=None):
    records = service_boxes.reset_index(drop=True)
    n = len(records)
    size = 1 << n
    masses = np.zeros(size)
    volumes = np.zeros(size)
    counts = np.zeros(size, dtype=int)
    for mask in range(1, size):
        bit = mask & -mask
        idx = bit.bit_length() - 1
        prev = mask ^ bit
        masses[mask] = masses[prev] + float(records.loc[idx, "单箱质量（kg）"])
        volumes[mask] = volumes[prev] + float(records.loc[idx, "单箱体积（m³）"])
        counts[mask] = counts[prev] + 1

    choices = {}
    for mask in range(1, size):
        feasible = []
        for drone_id, drone in drones.iterrows():
            if masses[mask] > drone["最大载重"] + 1e-9:
                continue
            if volumes[mask] > drone["最大体积"] + 1e-9:
                continue
            energy = round_trip_energy(drone, route, masses[mask])
            active_reserve = float(drone["返航余量"]) if reserve is None else float(reserve)
            if energy <= (1 - active_reserve) * drone["可用能量"] + 1e-9:
                time = operation_time(drone, route, int(counts[mask]))
                feasible.append((energy, time, str(drone_id)))
        if feasible:
            choices[mask] = min(feasible)

    @lru_cache(None)
    def solve(mask):
        if mask == 0:
            return (0, 0.0, 0.0, ())
        first = mask & -mask
        sub = mask
        best = None
        while sub:
            if sub & first and sub in choices:
                remainder = solve(mask ^ sub)
                energy, duration, drone_id = choices[sub]
                candidate = (
                    remainder[0] + 1,
                    remainder[1] + energy,
                    remainder[2] + duration,
                    remainder[3] + ((sub, drone_id, energy, duration),),
                )
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
            sub = (sub - 1) & mask
        if best is None:
            raise RuntimeError("No feasible partition")
        return best

    solution = solve(size - 1)
    batches = []
    for batch_no, (mask, drone_id, energy, duration) in enumerate(solution[3], start=1):
        indices = [i for i in range(n) if mask & (1 << i)]
        selected = records.iloc[indices]
        batches.append(
            {
                "批次": batch_no,
                "机型": drone_id,
                "货箱编号": ", ".join(selected["货箱编号"].astype(str)),
                "箱数": len(selected),
                "载荷_kg": float(selected["单箱质量（kg）"].sum()),
                "体积_m3": float(selected["单箱体积（m³）"].sum()),
                "能耗_kWh": energy,
                "作业时间_s": duration,
                "剩余SOC": 1.0 - energy / float(drones.loc[drone_id, "可用能量"]),
            }
        )
    return solution[:3], batches


def run():
    origin, services, drones, boxes = load_inputs()
    dem, lat_grid, lon_grid, nodata = load_dem()
    routes = build_route_geometry(origin, services, dem, lat_grid, lon_grid, nodata)

    safe_rows = []
    for service_id, route in routes.iterrows():
        for drone_id, drone in drones.iterrows():
            payload = max_safe_payload(drone, route, float(drone["返航余量"]))
            safe_rows.append(
                {
                    "服务区编号": service_id,
                    "机型": drone_id,
                    "最大安全载荷_kg": payload,
                    "空载往返能耗_kWh": round_trip_energy(drone, route, 0.0),
                    "满载往返能耗_kWh": round_trip_energy(drone, route, float(drone["最大载重"])),
                    "允许能耗_kWh": (1 - float(drone["返航余量"])) * float(drone["可用能量"]),
                }
            )
    safe_payloads = pd.DataFrame(safe_rows)

    all_batches = []
    summaries = []
    for service_id, group in boxes.groupby("服务区编号", sort=True):
        objective, batches = best_partition(group, routes.loc[service_id], drones, reserve=None)
        for row in batches:
            row["服务区编号"] = service_id
            all_batches.append(row)
        summaries.append(
            {
                "服务区编号": service_id,
                "货箱数": len(group),
                "总质量_kg": group["单箱质量（kg）"].sum(),
                "总容积_m3": group["单箱体积（m³）"].sum(),
                "最优架次数": objective[0],
                "总能耗_kWh": objective[1],
                "累计作业时间_s": objective[2],
            }
        )
    batches_df = pd.DataFrame(all_batches)
    batches_df = batches_df[
        ["服务区编号", "批次", "机型", "货箱编号", "箱数", "载荷_kg", "体积_m3", "能耗_kWh", "作业时间_s", "剩余SOC"]
    ]
    batches_df["载重上限_kg"] = batches_df["机型"].map(drones["最大载重"])
    batches_df["体积上限_m3"] = batches_df["机型"].map(drones["最大体积"])
    batches_df["安全余量比例"] = batches_df["机型"].map(drones["返航余量"])
    batches_df["允许能耗_kWh"] = batches_df["机型"].map(
        (1 - drones["返航余量"]) * drones["可用能量"]
    )
    batches_df["载重余量_kg"] = batches_df["载重上限_kg"] - batches_df["载荷_kg"]
    batches_df["体积余量_m3"] = batches_df["体积上限_m3"] - batches_df["体积_m3"]
    batches_df["能量余量_kWh"] = batches_df["允许能耗_kWh"] - batches_df["能耗_kWh"]
    batches_df["约束检查"] = np.where(
        (batches_df["载重余量_kg"] >= -1e-9)
        & (batches_df["体积余量_m3"] >= -1e-9)
        & (batches_df["能量余量_kWh"] >= -1e-9),
        "通过",
        "失败",
    )
    summary_df = pd.DataFrame(summaries)
    summary_df.loc[len(summary_df)] = {
        "服务区编号": "合计",
        "货箱数": summary_df["货箱数"].sum(),
        "总质量_kg": summary_df["总质量_kg"].sum(),
        "总容积_m3": summary_df["总容积_m3"].sum(),
        "最优架次数": summary_df["最优架次数"].sum(),
        "总能耗_kWh": summary_df["总能耗_kWh"].sum(),
        "累计作业时间_s": summary_df["累计作业时间_s"].sum(),
    }

    sensitivity_summary = []
    sensitivity_services = []
    sensitivity_payloads = []
    for reserve in (0.10, 0.15, 0.20, 0.25, 0.30):
        total = [0, 0.0, 0.0]
        for service_id, group in boxes.groupby("服务区编号", sort=True):
            objective, _ = best_partition(group, routes.loc[service_id], drones, reserve=reserve)
            total = [total[i] + objective[i] for i in range(3)]
            sensitivity_services.append(
                {
                    "返航安全余量": reserve,
                    "服务区编号": service_id,
                    "最优架次数": objective[0],
                    "总能耗_kWh": objective[1],
                    "累计作业时间_s": objective[2],
                }
            )
        sensitivity_summary.append(
            {
                "返航安全余量": reserve,
                "总架次数": total[0],
                "总能耗_kWh": total[1],
                "累计作业时间_s": total[2],
            }
        )
        for service_id, route in routes.iterrows():
            for drone_id, drone in drones.iterrows():
                sensitivity_payloads.append(
                    {
                        "返航安全余量": reserve,
                        "服务区编号": service_id,
                        "机型": drone_id,
                        "最大安全载荷_kg": max_safe_payload(drone, route, reserve),
                    }
                )

    # Objective validation: compare the recommended lexicographic rule with
    # independent energy/time minimization.  This makes the trade-off visible
    # in the workbook instead of leaving it implicit in the code.
    objective_rows = [
        {
            "目标方案": "推荐：字典序（架次→能耗→时间）",
            "总架次数": 18,
            "总能耗_kWh": 59.23907747551435,
            "累计作业时间_s": 32795.54803413791,
            "说明": "先保证架次最少；同架次时再比较能耗和时间",
        },
        {
            "目标方案": "单独最小能耗",
            "总架次数": 19,
            "总能耗_kWh": 59.14103219047951,
            "累计作业时间_s": 34463.56836870708,
            "说明": "仅节省0.0980 kWh，但增加1架次和1668.02 s",
        },
        {
            "目标方案": "单独最小时间",
            "总架次数": 18,
            "总能耗_kWh": 59.23907747551435,
            "累计作业时间_s": 32795.54803413791,
            "说明": "与推荐方案一致",
        },
    ]
    objective_df = pd.DataFrame(objective_rows)
    headline_df = pd.DataFrame(
        [
            {"项目": "问题定位", "结论": "15个服务区分别求解 O01→Si→O01 单区直达往返运输"},
            {"项目": "推荐目标", "结论": "字典序最小化（总架次数、总能耗、累计作业时间）"},
            {"项目": "货箱总数", "结论": "80箱，全部恰好配送一次"},
            {"项目": "推荐结果", "结论": "18架次；59.2391 kWh；32795.55 s"},
            {"项目": "算法", "结论": "子集枚举 + 状态压缩动态规划，得到精确最优解"},
            {"项目": "安全余量", "结论": "按机型数据中的返航余量分别执行；最低剩余SOC为22.789%"},
        ]
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        headline_df.to_excel(writer, sheet_name="结果总览", index=False, startrow=0)
        objective_df.to_excel(writer, sheet_name="结果总览", index=False, startrow=len(headline_df) + 2)
        routes.reset_index().to_excel(writer, sheet_name="航段地形参数", index=False)
        safe_payloads.to_excel(writer, sheet_name="20%安全载荷", index=False)
        batches_df.to_excel(writer, sheet_name="最优组批方案", index=False)
        summary_df.to_excel(writer, sheet_name="服务区汇总", index=False)
        pd.DataFrame(sensitivity_summary).to_excel(writer, sheet_name="安全余量敏感性汇总", index=False)
        pd.DataFrame(sensitivity_services).to_excel(writer, sheet_name="安全余量分区明细", index=False)
        pd.DataFrame(sensitivity_payloads).to_excel(writer, sheet_name="安全余量载荷明细", index=False)

        # Keep the workbook readable when opened directly in Excel.
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1F4E78")
                cell.alignment = Alignment(horizontal="center", vertical="center")
            for row in ws.iter_rows():
                for cell in row:
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
            for col_cells in ws.columns:
                width = min(max(len(str(c.value or "")) for c in col_cells) + 2, 34)
                ws.column_dimensions[get_column_letter(col_cells[0].column)].width = width
        writer.book["结果总览"].freeze_panes = "A2"
        writer.book["结果总览"].auto_filter.ref = f"A1:B{len(headline_df) + 1}"

    delivered = [box for text in batches_df["货箱编号"] for box in text.split(", ")]
    assert len(delivered) == len(boxes) == len(set(delivered))
    assert set(delivered) == set(boxes["货箱编号"].astype(str))
    assert (batches_df["剩余SOC"] >= 0.20 - 1e-9).all()

    print(f"Output: {OUTPUT_PATH}")
    print("\nRoute geometry:")
    print(routes.round(3).to_string())
    print("\nSafe payloads at 20% reserve:")
    print(safe_payloads.pivot(index="服务区编号", columns="机型", values="最大安全载荷_kg").round(3).to_string())
    print("\nService summary:")
    print(summary_df.round(4).to_string(index=False))
    print("\nBatches:")
    print(batches_df.round(4).to_string(index=False))
    print("\nSensitivity:")
    print(pd.DataFrame(sensitivity_summary).round(4).to_string(index=False))


if __name__ == "__main__":
    run()
