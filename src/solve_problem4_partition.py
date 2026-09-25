from __future__ import annotations

import itertools
import json
import heapq
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "results"
if not OUTPUT_DIR.is_dir() and (SCRIPT_DIR.parent / "results").is_dir():
    OUTPUT_DIR = SCRIPT_DIR.parent / "results"
SOURCE = OUTPUT_DIR / "问题三运输与中继联合调度最终结果.json"
OUT = OUTPUT_DIR / "问题四任务分区与资源配置结果.json"
RELAY_TURNAROUND_S = 300.0
INVENTORY = {
    "A型运输无人机": 4, "B型运输无人机": 2, "C型运输无人机": 2,
    "A型共享电池": 6, "B型共享电池": 4, "C型共享电池": 4,
    "中继无人机": 2, "中继能源组件": 6,
}


def peak_overlap(intervals):
    events = []
    for start, end in intervals:
        events.extend(((float(start), 1), (float(end), -1)))
    active = peak = 0
    for _, change in sorted(events, key=lambda item: (item[0], item[1])):
        active += change
        peak = max(peak, active)
    return peak


def assign_resources(rows, task_key, start_key, end_key, prefix, turnaround=0.0):
    active = []
    available = []
    assignments = {}
    count = 0
    intervals = []
    for row in sorted(rows, key=lambda x: (x[start_key], x[task_key])):
        start = float(row[start_key])
        end = float(row[end_key]) + turnaround
        while active and active[0][0] <= start:
            _, resource = heapq.heappop(active)
            heapq.heappush(available, resource)
        if available:
            resource = heapq.heappop(available)
        else:
            count += 1
            resource = count
        assignments[row[task_key]] = f"{prefix}{resource:02d}"
        heapq.heappush(active, (end, resource))
        intervals.append((start, end))
    assert count == peak_overlap(intervals)
    return count, assignments


def atomic_units(data):
    trips = {x["架次编号"]: x for x in data["运输架次"]}
    all_services = {x["服务区编号"] for x in data["逐箱交付"]}
    units = []
    used = set()
    for relay in data["中继架次"]:
        trip_ids = relay["保障运输架次"].split(", ")
        services = set()
        for trip_id in trip_ids:
            services.update(trips[trip_id]["访问服务区顺序"].split(", "))
        assert not (used & services), "中继任务服务区交叉，不能直接构造独立分区"
        used.update(services)
        units.append({"名称": relay["服务区域"], "服务区": sorted(services)})
    for service in sorted(all_services - used):
        units.append({"名称": service, "服务区": [service]})
    assert set().union(*(set(x["服务区"]) for x in units)) == all_services
    return units


def group_metrics(data, services, group_name):
    services = set(services)
    trips = [x for x in data["运输架次"] if set(x["访问服务区顺序"].split(", ")) <= services]
    boxes = [x for x in data["逐箱交付"] if x["服务区编号"] in services]
    trip_ids = {x["架次编号"] for x in trips}
    relays = [x for x in data["中继架次"] if set(x["保障运输架次"].split(", ")) <= trip_ids]
    assert len(boxes) == sum(x["货箱数"] for x in trips)
    assert all(set(x["访问服务区顺序"].split(", ")) <= services for x in trips)

    need = {}
    peak = {}
    reassigned = {}
    replacement = {}
    for model in "ABC":
        subset = [x for x in trips if x["机型编号"] == model]
        need[f"{model}型运输无人机"] = len({x["无人机编号"] for x in subset})
        need[f"{model}型共享电池"] = len({x["电池编号"] for x in subset})
        drone_count, drone_ids = assign_resources(
            subset, "架次编号", "开始时刻_s", "返回O01时刻_s", f"{group_name}-{model}-U"
        )
        battery_count, battery_ids = assign_resources(
            subset, "架次编号", "开始时刻_s", "电池充满时刻_s", f"{group_name}-{model}-BAT"
        )
        peak[f"{model}型运输无人机"] = drone_count
        peak[f"{model}型共享电池"] = battery_count
        reassigned[f"{model}型运输无人机"] = drone_count
        reassigned[f"{model}型共享电池"] = battery_count
        for trip in subset:
            tid = trip["架次编号"]
            replacement[tid] = {"机型": model, "组内无人机": drone_ids[tid],
                                "组内电池": battery_ids[tid]}
    need["中继无人机"] = len({x["中继无人机"] for x in relays})
    need["中继能源组件"] = len({x["能源组件"] for x in relays})
    relay_count, relay_ids = assign_resources(
        relays, "中继架次", "准备开始_s", "返回O01_s", f"{group_name}-R-U",
        RELAY_TURNAROUND_S,
    )
    component_count, component_ids = assign_resources(
        relays, "中继架次", "准备开始_s", "能源组件充满_s", f"{group_name}-R-BAT"
    )
    peak["中继无人机"] = relay_count
    peak["中继能源组件"] = component_count
    reassigned["中继无人机"] = relay_count
    reassigned["中继能源组件"] = component_count
    for mission in relays:
        mid = mission["中继架次"]
        replacement[mid] = {"组内中继无人机": relay_ids[mid],
                            "组内能源组件": component_ids[mid]}
    return {
        "服务区": sorted(services), "服务区数": len(services), "货箱数": len(boxes),
        "运输架次": len(trips), "中继架次": len(relays),
        "运输架次编号": sorted(trip_ids), "中继架次编号": [x["中继架次"] for x in relays],
        "运输能耗_kWh": sum(x["架次能耗_kWh"] for x in trips),
        "中继能耗_kWh": sum(x["总能耗_kWh"] for x in relays),
        "任务占用时长_s": sum(x["返回O01时刻_s"] - x["开始时刻_s"] for x in trips)
        + sum(x["返回O01_s"] - x["准备开始_s"] for x in relays),
        "联合完成时间_s": max([x["返回O01时刻_s"] for x in trips] +
                               [x["返回O01_s"] for x in relays]),
        "固定编号资源需求": need, "同时占用峰值": peak,
        "组内重派资源需求": reassigned, "组内重派架次安排": replacement,
        "固定编号相对峰值冗余": {k: need[k] - peak[k] for k in need},
        "运输无人机编号": sorted({x["无人机编号"] for x in trips}),
        "共享电池编号": sorted({x["电池编号"] for x in trips}),
        "中继无人机编号": sorted({x["中继无人机"] for x in relays}),
        "中继能源组件编号": sorted({x["能源组件"] for x in relays}),
    }


def partition_metrics(data, units, assignment, group_count):
    groups = []
    for group_id in range(group_count):
        services = [s for unit, assigned in zip(units, assignment)
                    if assigned == group_id for s in unit["服务区"]]
        metrics = group_metrics(data, services, f"G{group_id + 1}")
        metrics["任务组"] = f"G{group_id + 1}"
        groups.append(metrics)
    total_need = {key: sum(x["固定编号资源需求"][key] for x in groups) for key in INVENTORY}
    total_peak = {key: sum(x["同时占用峰值"][key] for x in groups) for key in INVENTORY}
    deficit = {key: max(0, total_need[key] - inventory) for key, inventory in INVENTORY.items()}
    reassigned_deficit = {
        key: max(0, total_peak[key] - inventory) for key, inventory in INVENTORY.items()
    }
    boxes = [x["货箱数"] for x in groups]
    trip_loads = [x["运输架次"] + x["中继架次"] for x in groups]
    energy_loads = [x["运输能耗_kWh"] + x["中继能耗_kWh"] for x in groups]
    duty_loads = [x["任务占用时长_s"] for x in groups]
    assert sum(x["服务区数"] for x in groups) == 15
    assert sum(boxes) == 80
    assert sum(x["运输架次"] for x in groups) == 21
    assert sum(x["中继架次"] for x in groups) == 4
    assert len(set().union(*(set(x["服务区"]) for x in groups))) == 15
    assert abs(sum(x["运输能耗_kWh"] + x["中继能耗_kWh"] for x in groups)
               - data["指标汇总"]["总能耗_kWh"]) < 1e-7
    assert all(total_peak[key] <= total_need[key] for key in INVENTORY)
    return {
        "任务组": groups, "资源总需求": total_need, "资源总峰值": total_peak,
        "资源缺口": deficit, "缺口合计": sum(deficit.values()),
        "组内重派资源总需求": total_peak,
        "组内重派资源缺口": reassigned_deficit,
        "组内重派缺口合计": sum(reassigned_deficit.values()),
        "相对峰值冗余": {key: total_need[key] - total_peak[key] for key in INVENTORY},
        "货箱数极差": max(boxes) - min(boxes),
        "架次数极差": max(trip_loads) - min(trip_loads),
        "能耗极差_kWh": max(energy_loads) - min(energy_loads),
        "任务占用时长极差_s": max(duty_loads) - min(duty_loads),
    }


def select_best(candidates, deficit_key):
    return min(candidates, key=lambda x: (
        x[deficit_key], x["货箱数极差"], x["架次数极差"],
        x["能耗极差_kWh"], x["任务占用时长极差_s"],
        sum(x["资源总需求"].values()),
    ))


def within_balance(row, group_count, tolerance):
    return all(
        abs(group["货箱数"] - 80 / group_count) <= tolerance * 80 / group_count + 1e-9
        and abs(group["运输架次"] + group["中继架次"] - 25 / group_count)
        <= tolerance * 25 / group_count + 1e-9
        for group in row["任务组"]
    )


def solve(data, group_count):
    units = atomic_units(data)
    candidates = []
    for tail in itertools.product(range(group_count), repeat=len(units) - 1):
        assignment = (0,) + tail
        if set(assignment) != set(range(group_count)):
            continue
        # Relabel in first-appearance order to remove equivalent permutations.
        seen = {}
        canonical = tuple(seen.setdefault(x, len(seen)) for x in assignment)
        if assignment != canonical:
            continue
        row = partition_metrics(data, units, assignment, group_count)
        row["原子单元分配"] = {unit["名称"]: f"G{x + 1}" for unit, x in zip(units, assignment)}
        candidates.append(row)
    best = select_best(candidates, "缺口合计")
    best_reassigned = select_best(candidates, "组内重派缺口合计")
    balanced = [x for x in candidates if within_balance(x, group_count, 0.25)]
    sweep = []
    for tolerance in (0.10, 0.20, 0.25, 0.30, 0.40):
        feasible = [x for x in candidates if within_balance(x, group_count, tolerance)]
        sweep.append({
            "允许偏离均值": tolerance,
            "可行分区数": len(feasible),
            "固定编号最小缺口": min((x["缺口合计"] for x in feasible), default=None),
            "组内重派最小缺口": min((x["组内重派缺口合计"] for x in feasible), default=None),
        })
    return {
        "可行分区枚举数": len(candidates),
        "最小缺口方案数": sum(x["缺口合计"] == best["缺口合计"] for x in candidates),
        "库存缺口最小方案": best,
        "组内重派缺口最小方案": best_reassigned,
        "25%均衡约束下缺口最小方案": select_best(balanced, "缺口合计") if balanced else None,
        "25%均衡约束下组内重派缺口最小方案":
            select_best(balanced, "组内重派缺口合计") if balanced else None,
        "25%均衡约束可行方案数": len(balanced),
        "均衡阈值敏感性": sweep,
    }


def main():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert all(x["结果"] == "通过" for x in data["可行性检查"])
    units = atomic_units(data)
    results = {str(k): solve(data, k) for k in (2, 3)}
    result = {
        "数据来源": SOURCE.name,
        "计算口径": "问题三的任务时间、组批、路线和通信保障关系固定；分别计算保留原执行编号与只在组内重派同机型设备的配置，组间资源不得调配。",
        "优化次序": "分别在固定编号及组内重派口径下最小化库存缺口；同缺口时依次比较货箱数、联合架次数、能耗、任务占用时长的极差。25%均衡约束及阈值敏感性是附加比较，不是题目硬约束。",
        "库存": INVENTORY, "不可拆分任务单元": units, "分区方案": results,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for key, variants in results.items():
        for variant_name in ("库存缺口最小方案", "组内重派缺口最小方案",
                             "25%均衡约束下缺口最小方案", "25%均衡约束下组内重派缺口最小方案"):
            value = variants[variant_name]
            deficit_key = "组内重派缺口合计" if "重派" in variant_name else "缺口合计"
            print(f"{key}组 {variant_name}: 缺口{value[deficit_key]}, "
                  f"货箱极差{value['货箱数极差']}, 架次极差{value['架次数极差']}, "
                  f"能耗极差{value['能耗极差_kWh']:.2f} kWh")
            for group in value["任务组"]:
                print(" ", group["任务组"], group["服务区"], group["货箱数"],
                      group["运输架次"], group["中继架次"])
    print("Output:", OUT)


if __name__ == "__main__":
    main()
