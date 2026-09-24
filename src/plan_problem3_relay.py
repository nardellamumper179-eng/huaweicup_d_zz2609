from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from solve_problem1 import G, KWH_J, OUTPUT_DIR, haversine_m, load_dem, load_inputs, nearest_indices


CANDIDATES = OUTPUT_DIR / "问题三中继候选点覆盖分析.json"
OUT = OUTPUT_DIR / "问题三中继任务初步规划.json"

MASS_KG = 23.5
CRUISE_SPEED = 15.0
CRUISE_POWER_KW = 1.15
CLIMB_SPEED = 4.0
DESCENT_SPEED = 3.0
CLIMB_EFF = 0.72
HOVER_COMM_POWER_KW = 1.10
USABLE_ENERGY_KWH = 3.2
RESERVE = 0.20
PREP_S = 180.0
LINK_S = 30.0
TURNAROUND_S = 300.0


def route_metrics(origin, point, dem, lat, lon, nodata):
    distance = haversine_m(origin[0], origin[1], point[0], point[1])
    count = max(2, int(math.ceil(distance / 5.0)) + 1)
    lons = np.linspace(origin[0], point[0], count)
    lats = np.linspace(origin[1], point[1], count)
    rr = nearest_indices(lat, lats); cc = nearest_indices(lon, lons)
    terrain = dem[rr, cc]
    terrain = terrain[np.isfinite(terrain) & (terrain != nodata)]
    cruise_alt = max(float(terrain.max()) + 50.0, point[2])
    out_climb = max(0.0, cruise_alt - origin[2])
    out_descent = max(0.0, cruise_alt - point[2])
    back_climb = max(0.0, cruise_alt - point[2])
    back_descent = max(0.0, cruise_alt - origin[2])
    out_time = out_climb / CLIMB_SPEED + distance / CRUISE_SPEED + out_descent / DESCENT_SPEED
    back_time = back_climb / CLIMB_SPEED + distance / CRUISE_SPEED + back_descent / DESCENT_SPEED
    horizontal_energy = CRUISE_POWER_KW * (2 * distance / CRUISE_SPEED) / 3600.0
    climb_energy = MASS_KG * G * (out_climb + back_climb) / (CLIMB_EFF * KWH_J)
    flight_energy = horizontal_energy + climb_energy
    max_hover = ((1 - RESERVE) * USABLE_ENERGY_KWH - flight_energy) / HOVER_COMM_POWER_KW * 3600.0
    return {
        "水平距离_m": distance, "巡航海拔_m": cruise_alt,
        "去程时间_s": out_time, "返程时间_s": back_time,
        "往返飞行能耗_kWh": flight_energy, "最大通信悬停_s": max_hover,
    }


def main():
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    origin_data, _, _, _ = load_inputs()
    origin = (origin_data["经度"], origin_data["纬度"], origin_data["海拔"])
    dem, lat, lon, nodata = load_dem()
    names = ["GRID-3-4-H300", "GRID-7-3-H300", "O01-S007-MID-H300", "GRID-4-6-H300"]
    rows = []
    for name in names:
        c = next(x for x in data["全部候选"] if x["候选点"] == name)
        point = (c["经度"], c["纬度"], c["悬停海拔_m"])
        rows.append({**{k: c[k] for k in ["候选点", "经度", "纬度", "地面高程_m", "离地高度_m", "悬停海拔_m", "完整覆盖缺口"]}, **route_metrics(origin, point, dem, lat, lon, nodata)})
    result = {"候选点飞行能源": rows}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for x in rows:
        print(x["候选点"], {k: round(x[k], 3) for k in ["水平距离_m", "去程时间_s", "返程时间_s", "往返飞行能耗_kWh", "最大通信悬停_s"]})
    print("Output:", OUT)


if __name__ == "__main__":
    main()
