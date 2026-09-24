from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from solve_problem1 import BASE_DIR, OUTPUT_DIR, haversine_m, load_dem, load_inputs, nearest_indices
from solve_problem2_multistop import build_all_segments


Q2 = OUTPUT_DIR / "问题三通信协调运输方案.json"
OUT = OUTPUT_DIR / "问题三固定网关直连覆盖分析.json"
FREQ_MHZ = 2400.0
SYSTEM_LOSS_DB = 3.0
OBSTRUCTION_LOSS_DB = 10.0
RECEIVER_THRESHOLD_DBM = -98.0 + 8.0
DIRECT_LIMIT_DB = 122.0
ACCESS_LIMIT_DB = 116.0
BACKHAUL_LIMIT_DB = 126.0


def fspl_db(distance_m: float) -> float:
    distance_km = max(distance_m / 1000.0, 1e-6)
    return 32.45 + 20.0 * math.log10(FREQ_MHZ) + 20.0 * math.log10(distance_km)


def distance_3d(a, b) -> float:
    horizontal = haversine_m(a[0], a[1], b[0], b[1])
    return math.hypot(horizontal, a[2] - b[2])


class TerrainLink:
    def __init__(self, dem, lat_grid, lon_grid, nodata):
        self.dem = dem
        self.lat_grid = lat_grid
        self.lon_grid = lon_grid
        self.nodata = nodata

    def obstructed(self, a, b) -> bool:
        horizontal = haversine_m(a[0], a[1], b[0], b[1])
        if horizontal < 1.0:
            return False
        count = max(3, int(math.ceil(horizontal / 20.0)) + 1)
        fractions = np.linspace(0.0, 1.0, count)[1:-1]
        lons = a[0] + fractions * (b[0] - a[0])
        lats = a[1] + fractions * (b[1] - a[1])
        line_alt = a[2] + fractions * (b[2] - a[2])
        rr = nearest_indices(self.lat_grid, lats)
        cc = nearest_indices(self.lon_grid, lons)
        ground = self.dem[rr, cc]
        valid = np.isfinite(ground) & (ground != self.nodata)
        return bool(np.any(ground[valid] >= line_alt[valid] - 1e-9))

    def status(self, a, b, limit_db):
        blocked = self.obstructed(a, b)
        distance = distance_3d(a, b)
        fspl = fspl_db(distance)
        path_loss = fspl + (OBSTRUCTION_LOSS_DB if blocked else 0.0)
        return {
            "可用": path_loss <= limit_db + 1e-9,
            "遮挡": blocked,
            "三维距离_m": distance,
            "自由空间损耗_dB": fspl,
            "总传播损耗_dB": path_loss,
            "链路裕量_dB": limit_db - path_loss,
        }


def phase_position(phase, elapsed):
    duration = phase["结束偏移_s"] - phase["开始偏移_s"]
    frac = 1.0 if duration <= 0 else min(1.0, max(0.0, elapsed / duration))
    a, b = phase["起点位置"], phase["终点位置"]
    return (
        a[0] + frac * (b[0] - a[0]),
        a[1] + frac * (b[1] - a[1]),
        a[2] + frac * (b[2] - a[2]),
    )


def build_phases(trip, task, types, nodes, segments):
    g = trip["机型编号"]
    typ = types.loc[g]
    ids = [x.strip() for x in trip["货箱编号"].split(",")]
    service = task
    seg_out = segments.loc[("O01", service)]
    seg_back = segments.loc[(service, "O01")]
    origin = nodes["O01"]
    dest = nodes[service]
    cruise_out = float(seg_out["巡航海拔_m"])
    cruise_back = float(seg_back["巡航海拔_m"])
    origin_work = (origin[0], origin[1], origin[2])
    dest_work = (dest[0], dest[1], dest[2] + 30.0)
    origin_out_high = (origin[0], origin[1], cruise_out)
    dest_out_high = (dest[0], dest[1], cruise_out)
    dest_back_high = (dest[0], dest[1], cruise_back)
    origin_back_high = (origin[0], origin[1], cruise_back)
    phases = []
    cursor = 0.0

    def add(name, duration, start_pos, end_pos):
        nonlocal cursor
        phases.append({
            "阶段": name, "开始偏移_s": cursor, "结束偏移_s": cursor + float(duration),
            "起点位置": start_pos, "终点位置": end_pos,
        })
        cursor += float(duration)

    add("O01准备装载", float(typ["准备时间"] + len(ids) * typ["每箱装载时间"]), origin_work, origin_work)
    add("去程爬升", float(seg_out["爬升_m"] / typ["爬升速度"]), origin_work, origin_out_high)
    add("去程巡航", float(seg_out["水平距离_m"] / typ["巡航速度"]), origin_out_high, dest_out_high)
    add("去程下降", float(seg_out["下降_m"] / typ["下降速度"]), dest_out_high, dest_work)
    add("服务区交接", float(typ["基础交接时间"] + len(ids) * typ["每箱交接时间"]), dest_work, dest_work)
    add("返程爬升", float(seg_back["爬升_m"] / typ["爬升速度"]), dest_work, dest_back_high)
    add("返程巡航", float(seg_back["水平距离_m"] / typ["巡航速度"]), dest_back_high, origin_back_high)
    add("返程下降", float(seg_back["下降_m"] / typ["下降速度"]), origin_back_high, origin_work)
    expected = trip["返回O01时刻_s"] - trip["开始时刻_s"]
    if abs(cursor - expected) > 0.3:
        raise AssertionError((trip["架次编号"], cursor, expected))
    return phases


def intervals_from_samples(samples):
    intervals = []
    active = None
    for row in samples:
        unavailable = not row["直连可用"]
        if unavailable and active is None:
            active = dict(row)
            active["缺口开始_s"] = row["时刻_s"]
            active["最小链路裕量_dB"] = row["链路裕量_dB"]
            active["最大总传播损耗_dB"] = row["总传播损耗_dB"]
            active["遮挡采样数"] = int(row["遮挡"])
            active["采样数"] = 1
        elif unavailable and active is not None:
            active["最小链路裕量_dB"] = min(active["最小链路裕量_dB"], row["链路裕量_dB"])
            active["最大总传播损耗_dB"] = max(active["最大总传播损耗_dB"], row["总传播损耗_dB"])
            active["遮挡采样数"] += int(row["遮挡"])
            active["采样数"] += 1
            active["终止阶段"] = row["阶段"]
            active["终点经度"] = row["经度"]
            active["终点纬度"] = row["纬度"]
            active["终点海拔_m"] = row["飞行海拔_m"]
        elif not unavailable and active is not None:
            active["缺口结束_s"] = row["时刻_s"]
            active["持续时间_s"] = active["缺口结束_s"] - active["缺口开始_s"]
            intervals.append(active)
            active = None
    if active is not None:
        active["缺口结束_s"] = samples[-1]["时刻_s"]
        active["持续时间_s"] = active["缺口结束_s"] - active["缺口开始_s"]
        intervals.append(active)
    return intervals


def main():
    q2 = json.loads(Q2.read_text(encoding="utf-8"))
    origin, services, types, _ = load_inputs()
    dem, lat_grid, lon_grid, nodata = load_dem()
    segments = build_all_segments(origin, services, dem, lat_grid, lon_grid, nodata)
    nodes = {"O01": (origin["经度"], origin["纬度"], origin["海拔"])}
    for _, row in services.iterrows():
        nodes[str(row["服务区编号"])] = (float(row["经度"]), float(row["纬度"]), float(row["海拔"]))
    gateway = (origin["经度"], origin["纬度"], origin["海拔"] + 20.0)
    terrain = TerrainLink(dem, lat_grid, lon_grid, nodata)
    all_samples, gaps, trip_summary, phase_summary = [], [], [], []
    for trip in q2["运输架次"]:
        service = trip["访问服务区顺序"].split("-")[0]
        phases = build_phases(trip, service, types, nodes, segments)
        samples = []
        for phase in phases:
            start_abs = trip["开始时刻_s"] + phase["开始偏移_s"]
            end_abs = trip["开始时刻_s"] + phase["结束偏移_s"]
            times = list(np.arange(math.ceil(start_abs), math.floor(end_abs) + 1, 1.0))
            times.extend([start_abs, end_abs])
            phase_rows = []
            for tm in sorted(set(round(float(x), 6) for x in times)):
                pos = phase_position(phase, tm - start_abs)
                link = terrain.status(pos, gateway, DIRECT_LIMIT_DB)
                row = {
                    "架次编号": trip["架次编号"], "任务编号": trip["任务编号"], "无人机编号": trip["无人机编号"],
                    "服务区编号": service, "阶段": phase["阶段"], "时刻_s": tm,
                    "经度": pos[0], "纬度": pos[1], "飞行海拔_m": pos[2],
                    "直连可用": link["可用"], "遮挡": link["遮挡"], "三维距离_m": link["三维距离_m"],
                    "总传播损耗_dB": link["总传播损耗_dB"], "链路裕量_dB": link["链路裕量_dB"],
                }
                samples.append(row); phase_rows.append(row)
            phase_summary.append({
                "架次编号": trip["架次编号"], "服务区编号": service, "阶段": phase["阶段"],
                "开始_s": start_abs, "结束_s": end_abs, "持续_s": end_abs - start_abs,
                "直连可用比例": sum(x["直连可用"] for x in phase_rows) / len(phase_rows),
                "最小链路裕量_dB": min(x["链路裕量_dB"] for x in phase_rows),
                "遮挡比例": sum(x["遮挡"] for x in phase_rows) / len(phase_rows),
            })
        samples.sort(key=lambda x: (x["时刻_s"], x["阶段"]))
        # Remove duplicate phase-boundary samples, preferring the later phase label.
        samples = list({x["时刻_s"]: x for x in samples}.values())
        samples.sort(key=lambda x: x["时刻_s"])
        trip_gaps = intervals_from_samples(samples)
        for i, gap in enumerate(trip_gaps, 1):
            gap["缺口编号"] = f"{trip['架次编号']}-G{i:02d}"
            gap["起始阶段"] = gap.pop("阶段")
            gap["起点经度"] = gap.pop("经度")
            gap["起点纬度"] = gap.pop("纬度")
            gap["起点海拔_m"] = gap.pop("飞行海拔_m")
        gaps.extend(trip_gaps)
        all_samples.extend(samples)
        trip_summary.append({
            "架次编号": trip["架次编号"], "服务区编号": service,
            "任务开始_s": trip["开始时刻_s"], "任务返回_s": trip["返回O01时刻_s"],
            "检查时长_s": trip["返回O01时刻_s"] - trip["开始时刻_s"],
            "直连可用比例": sum(x["直连可用"] for x in samples) / len(samples),
            "通信缺口段数": len(trip_gaps), "通信缺口总时长_s": sum(x["持续时间_s"] for x in trip_gaps),
            "最小链路裕量_dB": min(x["链路裕量_dB"] for x in samples),
            "最大三维距离_m": max(x["三维距离_m"] for x in samples),
        })

    result = {
        "链路门限": {"运输无人机_G01_dB": DIRECT_LIMIT_DB, "运输无人机_中继_dB": ACCESS_LIMIT_DB, "中继_G01_dB": BACKHAUL_LIMIT_DB},
        "采样说明": "各阶段边界及每1秒采样；地形视线按不超过20米水平间距检查30米DEM。",
        "汇总": {
            "运输架次": len(q2["运输架次"]), "检查样本数": len(all_samples),
            "存在直连缺口架次": sum(x["通信缺口段数"] > 0 for x in trip_summary),
            "缺口段数": len(gaps), "缺口累计时长_s": sum(x["持续时间_s"] for x in gaps),
            "最差链路裕量_dB": min(x["链路裕量_dB"] for x in all_samples),
        },
        "架次汇总": trip_summary,
        "阶段汇总": phase_summary,
        "通信缺口": sorted(gaps, key=lambda x: (x["缺口开始_s"], x["架次编号"])),
        "逐秒样本": all_samples,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["汇总"], ensure_ascii=False, indent=2))
    print(pd.DataFrame(trip_summary).to_string(index=False))
    print("Output:", OUT)


if __name__ == "__main__":
    main()
