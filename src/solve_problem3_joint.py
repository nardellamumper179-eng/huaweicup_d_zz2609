from __future__ import annotations

import json
from collections import defaultdict

import numpy as np

from solve_problem1 import OUTPUT_DIR, load_dem, load_inputs
from solve_problem2_baseline import charger_time
from solve_problem2_multistop import build_all_segments
from solve_problem3_coverage import ACCESS_LIMIT_DB, BACKHAUL_LIMIT_DB, DIRECT_LIMIT_DB, TerrainLink, build_phases, phase_position
from plan_problem3_relay import (
    HOVER_COMM_POWER_KW,
    LINK_S,
    PREP_S,
    RESERVE,
    TURNAROUND_S,
    USABLE_ENERGY_KWH,
    route_metrics,
)


TRANSPORT = OUTPUT_DIR / "问题三通信协调运输方案.json"
DIRECT = OUTPUT_DIR / "问题三固定网关直连覆盖分析.json"
OUT = OUTPUT_DIR / "问题三运输与中继联合调度最终结果.json"


POINTS = {
    "中央": {
        "候选点": "REF-109.217500-23.032000-H300",
        "经度": 109.2175,
        "纬度": 23.032,
        "地面高程_m": 216.32435607910156,
        "离地高度_m": 300.0,
        "悬停海拔_m": 516.3243560791016,
    },
    "东部": {
        "候选点": "GRID-7-2-H300",
        "经度": 109.2835966,
        "纬度": 23.0175933,
        "地面高程_m": 426.6973876953125,
        "离地高度_m": 300.0,
        "悬停海拔_m": 726.6973876953125,
    },
    "西部": {
        "候选点": "WEST-109.213585-23.021464-H300",
        "经度": 109.2135854,
        "纬度": 23.02146405,
        "地面高程_m": 238.58375549316406,
        "离地高度_m": 300.0,
        "悬停海拔_m": 538.5837554931641,
    },
    "北部": {
        "候选点": "GRID-4-6-H300",
        "经度": 109.2262272,
        "纬度": 23.0671277,
        "地面高程_m": 239.36463928222656,
        "离地高度_m": 300.0,
        "悬停海拔_m": 539.3646392822266,
    },
}


ASSIGNMENTS = {
    "中央": {"Q2-01", "Q2-02", "Q2-09", "Q2-11", "Q2-12"},
    "东部": {"Q2-05", "Q2-06", "Q2-07", "Q2-08", "Q2-13"},
    "西部": {"Q2-15", "Q2-16", "Q2-17", "Q2-20"},
    "北部": {"Q2-14", "Q2-18", "Q2-19"},
}


def validate_transport(data):
    trips = data["运输架次"]
    deliveries = data["逐箱交付"]
    checks = []
    unique_boxes = len({x["货箱编号"] for x in deliveries})
    checks.append({"检查项": "货箱完整性", "结果": unique_boxes == len(deliveries) == 80,
                   "数值": f"{len(deliveries)}/80，唯一货箱 {unique_boxes}"})
    hard_late = sum(x["硬约束延误_s"] > 1e-9 for x in deliveries)
    expected_late = sum(x["期望延误_s"] > 1e-9 for x in deliveries)
    checks.append({"检查项": "硬时限", "结果": hard_late == 0, "数值": f"违约 {hard_late} 箱"})
    checks.append({"检查项": "全部期望时间", "结果": expected_late == 0, "数值": f"迟到 {expected_late} 箱"})
    soc_bad = [x["架次编号"] for x in trips if x["返航SOC"] + 1e-9 < x["返航余量要求"]]
    checks.append({"检查项": "运输机返航SOC", "结果": not soc_bad,
                   "数值": f"最低 {min(x['返航SOC'] for x in trips):.6f}"})

    drone_overlap = []
    by_drone = defaultdict(list)
    for x in trips:
        by_drone[x["无人机编号"]].append(x)
    for drone, rows in by_drone.items():
        rows.sort(key=lambda x: x["开始时刻_s"])
        for left, right in zip(rows, rows[1:]):
            if right["开始时刻_s"] < left["返回O01时刻_s"] - 1e-9:
                drone_overlap.append([drone, left["架次编号"], right["架次编号"]])
    checks.append({"检查项": "运输无人机冲突", "结果": not drone_overlap,
                   "数值": f"{len(drone_overlap)} 个重叠"})

    battery_overlap = []
    by_battery = defaultdict(list)
    for x in trips:
        by_battery[x["电池编号"]].append(x)
    for battery, rows in by_battery.items():
        rows.sort(key=lambda x: x["开始时刻_s"])
        for left, right in zip(rows, rows[1:]):
            if right["开始时刻_s"] < left["电池充满时刻_s"] - 1e-9:
                battery_overlap.append([battery, left["架次编号"], right["架次编号"]])
    checks.append({"检查项": "运输电池飞行与充电冲突", "结果": not battery_overlap,
                   "数值": f"{len(battery_overlap)} 个重叠"})
    if not all(x["结果"] for x in checks):
        raise AssertionError({"checks": checks, "drone_overlap": drone_overlap, "battery_overlap": battery_overlap})
    return checks


def build_missions(direct, origin, dem, lat, lon, nodata):
    gap_bounds = {}
    for region, trip_ids in ASSIGNMENTS.items():
        gaps = [x for x in direct["通信缺口"] if x["架次编号"] in trip_ids]
        gap_bounds[region] = (min(x["缺口开始_s"] for x in gaps), max(x["缺口结束_s"] for x in gaps))

    metrics = {}
    for region, p in POINTS.items():
        pos = (p["经度"], p["纬度"], p["悬停海拔_m"])
        metrics[region] = route_metrics(origin, pos, dem, lat, lon, nodata)

    missions = []

    def add(mission_id, drone, component, region, prep_start, service_end):
        m = metrics[region]
        takeoff = prep_start + PREP_S
        arrival = takeoff + m["去程时间_s"]
        service_start = arrival + LINK_S
        # 建链阶段也需要保持悬停和通信，服务能耗从到达悬停点开始计。
        hover_s = service_end - arrival
        if hover_s < -1e-9:
            raise AssertionError((mission_id, "negative hover"))
        return_time = service_end + m["返程时间_s"]
        hover_energy = HOVER_COMM_POWER_KW * hover_s / 3600.0
        total_energy = m["往返飞行能耗_kWh"] + hover_energy
        return_soc = 1.0 - total_energy / USABLE_ENERGY_KWH
        full_time = return_time + charger_time(return_soc, 1800.0)
        p = POINTS[region]
        missions.append({
            "中继架次": mission_id, "中继无人机": drone, "能源组件": component, "服务区域": region,
            "悬停点": p["候选点"], "经度": p["经度"], "纬度": p["纬度"],
            "地面高程_m": p["地面高程_m"], "离地高度_m": p["离地高度_m"], "悬停海拔_m": p["悬停海拔_m"],
            "准备开始_s": prep_start, "起飞_s": takeoff, "到达悬停点_s": arrival,
            "建链完成_服务开始_s": service_start, "服务结束_s": service_end,
            "返回O01_s": return_time, "能源组件充满_s": full_time,
            "去程时间_s": m["去程时间_s"], "返程时间_s": m["返程时间_s"],
            "通信悬停_s": hover_s, "建链悬停_s": LINK_S, "往返飞行能耗_kWh": m["往返飞行能耗_kWh"],
            "悬停通信能耗_kWh": hover_energy, "总能耗_kWh": total_energy,
            "返航SOC": return_soc, "返航余量要求": RESERVE, "SOC安全裕量": return_soc - RESERVE,
            "保障运输架次": ", ".join(sorted(ASSIGNMENTS[region])),
        })
        return missions[-1]

    central = add("R-M01", "R01", "R-BAT-01", "中央", 0.0, gap_bounds["中央"][1])
    east = add("R-M02", "R02", "R-BAT-02", "东部", 0.0, gap_bounds["东部"][1])
    west_prep = central["返回O01_s"] + TURNAROUND_S
    north_prep = east["返回O01_s"] + TURNAROUND_S
    add("R-M03", "R01", "R-BAT-03", "西部", west_prep, gap_bounds["西部"][1])
    add("R-M04", "R02", "R-BAT-04", "北部", north_prep, gap_bounds["北部"][1])
    return missions, metrics, gap_bounds


def verify_communications(direct, missions, origin, dem, lat, lon, nodata):
    terrain = TerrainLink(dem, lat, lon, nodata)
    gateway = (origin[0], origin[1], origin[2] + 20.0)
    mission_by_region = {x["服务区域"]: x for x in missions}
    trip_region = {trip: region for region, trips in ASSIGNMENTS.items() for trip in trips}
    backhaul = {}
    for region, mission in mission_by_region.items():
        relay = (mission["经度"], mission["纬度"], mission["悬停海拔_m"])
        backhaul[region] = terrain.status(relay, gateway, BACKHAUL_LIMIT_DB)
        if not backhaul[region]["可用"]:
            raise AssertionError((region, "backhaul unavailable", backhaul[region]))

    interruptions = []
    relay_rows = []
    min_access = {x: float("inf") for x in ASSIGNMENTS}
    for row in direct["逐秒样本"]:
        if row["直连可用"]:
            continue
        region = trip_region.get(row["架次编号"])
        if region is None:
            interruptions.append({**row, "原因": "未分配中继区域"})
            continue
        mission = mission_by_region[region]
        active = mission["建链完成_服务开始_s"] <= row["时刻_s"] <= mission["服务结束_s"]
        relay = (mission["经度"], mission["纬度"], mission["悬停海拔_m"])
        transport = (row["经度"], row["纬度"], row["飞行海拔_m"])
        access = terrain.status(transport, relay, ACCESS_LIMIT_DB)
        margin = min(access["链路裕量_dB"], backhaul[region]["链路裕量_dB"])
        min_access[region] = min(min_access[region], access["链路裕量_dB"])
        covered = active and access["可用"] and backhaul[region]["可用"]
        relay_rows.append({
            "架次编号": row["架次编号"], "服务区编号": row["服务区编号"], "时刻_s": row["时刻_s"],
            "中继架次": mission["中继架次"], "服务区域": region, "中继活动": active,
            "接入链路可用": access["可用"], "接入链路遮挡": access["遮挡"],
            "接入损耗_dB": access["总传播损耗_dB"], "接入裕量_dB": access["链路裕量_dB"],
            "回传裕量_dB": backhaul[region]["链路裕量_dB"], "双段最小裕量_dB": margin,
            "中继覆盖": covered,
        })
        if not covered:
            interruptions.append({**relay_rows[-1], "原因": "时序或链路不满足"})
    if interruptions:
        raise AssertionError({"通信中断样本数": len(interruptions), "首批": interruptions[:10]})

    summary = []
    for region, mission in mission_by_region.items():
        rows = [x for x in relay_rows if x["服务区域"] == region]
        summary.append({
            "服务区域": region, "中继架次": mission["中继架次"], "直连缺口样本数": len(rows),
            "最小接入裕量_dB": min(x["接入裕量_dB"] for x in rows),
            "回传裕量_dB": backhaul[region]["链路裕量_dB"],
            "最小双段裕量_dB": min(x["双段最小裕量_dB"] for x in rows),
            "中断样本数": sum(not x["中继覆盖"] for x in rows),
        })
    return relay_rows, summary


def validate_relay_resources(missions):
    checks = []
    timing_violations = []
    by_drone = defaultdict(list)
    for x in missions:
        by_drone[x["中继无人机"]].append(x)
    for drone, rows in by_drone.items():
        rows.sort(key=lambda x: x["准备开始_s"])
        for left, right in zip(rows, rows[1:]):
            earliest = left["返回O01_s"] + TURNAROUND_S
            if right["准备开始_s"] < earliest - 1e-9:
                timing_violations.append([drone, left["中继架次"], right["中继架次"]])
    checks.append({"检查项": "中继无人机周转冲突", "结果": not timing_violations,
                   "数值": f"{len(timing_violations)} 个重叠"})
    soc_bad = [x["中继架次"] for x in missions if x["返航SOC"] < RESERVE - 1e-9]
    checks.append({"检查项": "中继机返航SOC", "结果": not soc_bad,
                   "数值": f"最低 {min(x['返航SOC'] for x in missions):.6f}"})
    components = [x["能源组件"] for x in missions]
    checks.append({"检查项": "中继能源组件数量", "结果": len(set(components)) <= 6,
                   "数值": f"使用 {len(set(components))}/6 组"})
    if not all(x["结果"] for x in checks):
        raise AssertionError(checks)
    return checks


def verify_switch_boundaries(transport, direct, origin_data, services, types, dem, lat, lon, nodata, missions):
    """Check a fine time grid around every direct-link gap boundary."""
    segments = build_all_segments(origin_data, services, dem, lat, lon, nodata)
    nodes = {"O01": (origin_data["经度"], origin_data["纬度"], origin_data["海拔"])}
    for _, row in services.iterrows():
        nodes[str(row["服务区编号"])] = (float(row["经度"]), float(row["纬度"]), float(row["海拔"]))
    gateway = (origin_data["经度"], origin_data["纬度"], origin_data["海拔"] + 20.0)
    terrain = TerrainLink(dem, lat, lon, nodata)
    trips = {x["架次编号"]: x for x in transport["运输架次"]}
    mission_by_trip = {tid: m for m in missions for tid in m["保障运输架次"].split(", ")}
    phases = {
        tid: build_phases(trip, trip["访问服务区顺序"], types, nodes, segments)
        for tid, trip in trips.items()
    }
    checked = 0
    failures = []
    for gap in direct["通信缺口"]:
        trip = trips[gap["架次编号"]]
        mission = mission_by_trip[gap["架次编号"]]
        relay = (mission["经度"], mission["纬度"], mission["悬停海拔_m"])
        for edge in (gap["缺口开始_s"], gap["缺口结束_s"]):
            for tm in np.arange(edge - 1.0, edge + 1.0001, 0.05):
                phase = next((p for p in phases[trip["架次编号"]]
                              if trip["开始时刻_s"] + p["开始偏移_s"] - 1e-8 <= tm <=
                              trip["开始时刻_s"] + p["结束偏移_s"] + 1e-8), None)
                if phase is None:
                    continue
                pos = phase_position(phase, tm - trip["开始时刻_s"] - phase["开始偏移_s"])
                direct_ok = terrain.status(pos, gateway, DIRECT_LIMIT_DB)["可用"]
                relay_ok = (
                    mission["建链完成_服务开始_s"] <= tm <= mission["服务结束_s"]
                    and terrain.status(pos, relay, ACCESS_LIMIT_DB)["可用"]
                    and terrain.status(relay, gateway, BACKHAUL_LIMIT_DB)["可用"]
                )
                checked += 1
                if not direct_ok and not relay_ok:
                    failures.append((gap["缺口编号"], round(float(tm), 4)))
    return checked, failures


def main():
    transport = json.loads(TRANSPORT.read_text(encoding="utf-8"))
    direct = json.loads(DIRECT.read_text(encoding="utf-8"))
    origin_data, services, types, _ = load_inputs()
    origin = (origin_data["经度"], origin_data["纬度"], origin_data["海拔"])
    dem, lat, lon, nodata = load_dem()
    checks = validate_transport(transport)
    missions, _, gap_bounds = build_missions(direct, origin, dem, lat, lon, nodata)
    relay_rows, coverage_summary = verify_communications(direct, missions, origin, dem, lat, lon, nodata)
    checks.extend(validate_relay_resources(missions))
    boundary_samples, boundary_failures = verify_switch_boundaries(
        transport, direct, origin_data, services, types, dem, lat, lon, nodata, missions
    )
    checks.append({"检查项": "通信切换边界加密检查", "结果": not boundary_failures,
                   "数值": f"检查 {boundary_samples} 个边界样本，中断 {len(boundary_failures)} 点"})
    checks.append({"检查项": "连续通信", "结果": True,
                   "数值": f"逐秒检查 {len(direct['逐秒样本'])} 点，直连缺口 {len(relay_rows)} 点，中断 0 点"})

    transport_energy = sum(x["架次能耗_kWh"] for x in transport["运输架次"])
    relay_energy = sum(x["总能耗_kWh"] for x in missions)
    joint_finish = max(
        max(x["返回O01时刻_s"] for x in transport["运输架次"]),
        max(x["返回O01_s"] for x in missions),
    )
    mission_for_trip = {
        trip: next(x["中继架次"] for x in missions if x["服务区域"] == region)
        for region, trips in ASSIGNMENTS.items() for trip in trips
    }
    gaps_by_trip = defaultdict(list)
    for gap in direct["通信缺口"]:
        gaps_by_trip[gap["架次编号"]].append(gap)
    communication_detail = []
    for trip in transport["运输架次"]:
        trip_id = trip["架次编号"]
        cursor = trip["开始时刻_s"]
        stage_no = 1
        for gap in sorted(gaps_by_trip[trip_id], key=lambda x: x["缺口开始_s"]):
            detail_start = max(trip["开始时刻_s"], gap["缺口开始_s"] - 1.0)
            if detail_start > cursor + 1e-9:
                communication_detail.append({
                    "运输架次编号": trip_id, "通信阶段": f"阶段{stage_no}",
                    "开始时刻_s": cursor, "结束时刻_s": detail_start,
                    "保障方式": "G01直连", "中继架次编号": None,
                })
                stage_no += 1
            detail_end = min(trip["返回O01时刻_s"], gap["缺口结束_s"] + 1.0)
            communication_detail.append({
                "运输架次编号": trip_id, "通信阶段": f"阶段{stage_no}",
                # Expand the reported 1 s gap by one second on each side so
                # the submission table remains conservative at switch edges.
                    "开始时刻_s": detail_start, "结束时刻_s": detail_end,
                    "保障方式": "空中中继", "中继架次编号": mission_for_trip[trip_id],
            })
            stage_no += 1
            cursor = detail_end
        if trip["返回O01时刻_s"] > cursor + 1e-9:
            communication_detail.append({
                "运输架次编号": trip_id, "通信阶段": f"阶段{stage_no}",
                "开始时刻_s": cursor, "结束时刻_s": trip["返回O01时刻_s"],
                "保障方式": "G01直连", "中继架次编号": None,
            })
    result = {
        "方案名称": "问题三运输与中继联合调度方案",
        "方法说明": "继承问题二ALNS+CP-SAT零延误组批与路线，联合调整运输时刻；采用DEM候选点搜索确定四个悬停点，并用两架中继无人机轮换执行四个架次；最终按1秒时间采样、切换边界0.05秒加密采样和不超过20米的DEM视线采样检查通信状态。",
        "最优性边界": "候选悬停点与轮换顺序采用启发式搜索，结果为经逐秒验证的可行优质方案，不宣称完整混合离散-连续问题的全局最优。",
        "指标汇总": {
            "货箱数": len(transport["逐箱交付"]),
            "迟到箱数": sum(x["期望延误_s"] > 1e-9 for x in transport["逐箱交付"]),
            "加权延误": sum(x["加权延误"] for x in transport["逐箱交付"]),
            "运输架次": len(transport["运输架次"]), "中继架次": len(missions),
            "联合架次": len(transport["运输架次"]) + len(missions),
            "使用运输无人机": len({x["无人机编号"] for x in transport["运输架次"]}),
            "使用中继无人机": len({x["中继无人机"] for x in missions}),
            "使用运输电池": len({x["电池编号"] for x in transport["运输架次"]}),
            "使用中继能源组件": len({x["能源组件"] for x in missions}),
            "运输能耗_kWh": transport_energy, "中继能耗_kWh": relay_energy,
            "总能耗_kWh": transport_energy + relay_energy,
            "运输完成时间_s": max(x["返回O01时刻_s"] for x in transport["运输架次"]),
            "联合任务完成时间_s": joint_finish,
            "最低运输返航SOC": min(x["返航SOC"] for x in transport["运输架次"]),
            "最低中继返航SOC": min(x["返航SOC"] for x in missions),
            "通信检查样本": len(direct["逐秒样本"]), "边界加密样本": boundary_samples,
            "通信中断样本": 0,
        },
        "权衡说明": [
            "保持80箱零延误，优先级高于减少联合完成时间和能耗。",
            "为满足两架中继无人机的区域轮换，运输完成时间由问题二的7718.4秒增加到8067.4秒。",
            "采用四个区域中继架次，以少量中继能耗换取运输全过程连续通信；四个不同能源组件避免等待充电。",
        ],
        "链路门限": direct["链路门限"],
        "区域缺口时间范围": {k: {"最早缺口_s": v[0], "最晚缺口结束_s": v[1]} for k, v in gap_bounds.items()},
        "中继架次": missions,
        "通信保障汇总": coverage_summary,
        "通信保障明细": communication_detail,
        "运输架次": transport["运输架次"],
        "逐箱交付": transport["逐箱交付"],
        "可行性检查": [{**x, "结果": "通过" if x["结果"] else "不通过"} for x in checks],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["指标汇总"], ensure_ascii=False, indent=2))
    print(json.dumps(result["通信保障汇总"], ensure_ascii=False, indent=2))
    print("Output:", OUT)


if __name__ == "__main__":
    main()
