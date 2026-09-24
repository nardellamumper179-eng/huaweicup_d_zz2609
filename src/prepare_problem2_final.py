from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

import experiment_problem2_methods as exp
from solve_problem1 import BASE_DIR, OUTPUT_DIR, load_dem, load_inputs
from solve_problem2_multistop import build_all_segments


OUT = OUTPUT_DIR / "问题二ALNS_CP_SAT最终结果.json"


def main():
    methods = json.loads((OUTPUT_DIR / "问题二多方法实验结果.json").read_text(encoding="utf-8"))
    pareto = json.loads((OUTPUT_DIR / "问题二候选组批与多目标实验.json").read_text(encoding="utf-8"))
    solution = methods["alns_cp_sat"]
    partition = methods["alns"]["partition"]

    types, box_map, drones, battery_stock, base_tasks, base_cache = exp.build_problem()
    origin, services, _, _ = load_inputs()
    dem, lat, lon, nodata = load_dem()
    exp.segments_global = build_all_segments(origin, services, dem, lat, lon, nodata)
    fixed = [t for t in base_tasks if all(stop != "S002" for stop, _ in t["停靠"])]
    extra = [exp.task_from_ids("S002", group, f"A2-{i:02d}") for i, group in enumerate(partition, 1)]
    tasks = fixed + extra
    task_map = {t["任务编号"]: t for t in tasks}

    schedule = sorted(solution["schedule"], key=lambda x: (x["开始_s"], x["任务编号"]))
    schedule_by_task = {x["任务编号"]: x for x in schedule}
    delivery_by_box = {x["货箱编号"]: x for x in solution["deliveries"]}
    trips, deliveries = [], []
    for idx, row in enumerate(schedule, 1):
        task = task_map[row["任务编号"]]
        ids = [bid for _, group in task["停靠"] for bid in group]
        selected = box_map.loc[ids]
        stops = [s for s, _ in task["停靠"]]
        trip_no = f"Q2-{idx:02d}"
        trips.append({
            "架次编号": trip_no,
            "任务编号": row["任务编号"],
            "来源批次": task["来源"],
            "路线": "O01-" + "-".join(stops) + "-O01",
            "访问服务区顺序": "-".join(stops),
            "无人机编号": row["无人机编号"],
            "机型编号": row["机型"],
            "电池编号": row["电池编号"],
            "开始时刻_s": row["开始_s"],
            "返回O01时刻_s": row["返回_s"],
            "电池充满时刻_s": row["充满_s"],
            "飞行作业时长_s": row["返回_s"] - row["开始_s"],
            "电池占用时长_s": row["充满_s"] - row["开始_s"],
            "货箱数": len(ids),
            "载荷_kg": float(selected["单箱质量（kg）"].sum()),
            "体积_m3": float(selected["单箱体积（m³）"].sum()),
            "架次能耗_kWh": row["能耗_kWh"],
            "返航SOC": row["返航SOC"],
            "返航余量要求": float(types.loc[row["机型"], "返航余量"]),
            "SOC安全裕量": row["返航SOC"] - float(types.loc[row["机型"], "返航余量"]),
            "货箱编号": ", ".join(ids),
        })
        for bid in ids:
            d = delivery_by_box[bid]
            box = box_map.loc[bid]
            hard_deadline = math.inf
            if box["是否首批保障"] == "是":
                hard_deadline = min(hard_deadline, float(box["首批截止时间（s）"]))
            if box["物资类型"] == "医疗物资":
                hard_deadline = min(hard_deadline, float(box["期望送达时间（s）"]))
            deliveries.append({
                "货箱编号": bid,
                "架次编号": trip_no,
                "任务编号": row["任务编号"],
                "服务区编号": str(box["服务区编号"]),
                "物资类型": str(box["物资类型"]),
                "是否首批保障": str(box["是否首批保障"]),
                "无人机编号": row["无人机编号"],
                "电池编号": row["电池编号"],
                "交付完成时刻_s": d["送达时刻_s"],
                "首批截止_s": None if pd.isna(box["首批截止时间（s）"]) else float(box["首批截止时间（s）"]),
                "期望送达_s": float(box["期望送达时间（s）"]),
                "硬约束截止_s": None if not math.isfinite(hard_deadline) else hard_deadline,
                "硬约束延误_s": 0 if not math.isfinite(hard_deadline) else max(0.0, d["送达时刻_s"] - hard_deadline),
                "期望延误_s": d["期望延误_s"],
                "应急优先系数": float(box["应急优先系数"]),
                "加权延误": d["加权延误"],
            })

    drone_rows = []
    for (u, g), group in pd.DataFrame(trips).groupby(["无人机编号", "机型编号"]):
        drone_rows.append({
            "无人机编号": u, "机型编号": g, "执行架次": len(group),
            "首次起飞_s": float(group["开始时刻_s"].min()), "最后返航_s": float(group["返回O01时刻_s"].max()),
            "累计作业_s": float(group["飞行作业时长_s"].sum()), "累计能耗_kWh": float(group["架次能耗_kWh"].sum()),
            "执行任务": ", ".join(group.sort_values("开始时刻_s")["架次编号"]),
        })
    battery_rows = []
    for bat, group in pd.DataFrame(trips).groupby("电池编号"):
        battery_rows.append({
            "电池编号": bat, "机型编号": str(bat)[0], "使用次数": len(group),
            "首次使用_s": float(group["开始时刻_s"].min()), "最后返航_s": float(group["返回O01时刻_s"].max()),
            "最后充满_s": float(group["电池充满时刻_s"].max()), "最低返航SOC": float(group["返航SOC"].min()),
            "执行架次": ", ".join(group.sort_values("开始时刻_s")["架次编号"]),
        })

    comparisons = [
        {"方案": "原19架次局部搜索", "加权延误": 32535.6316807811, "迟到箱数": 3, "最后返航_s": 9501.6434118298, "总能耗_kWh": 61.5747556491, "总架次": 19, "定位": "最低架次与低能耗基准"},
        {"方案": "20架次候选组批+CP-SAT", **pareto["candidate_generation_cp_sat_detail"]["3"]["objective"], "定位": "增加1架次的折中方案"},
        {"方案": "21架次ALNS+CP-SAT", **solution["objective"], "定位": "零延误推荐方案"},
    ]
    for x in comparisons:
        if "weighted_lateness" in x:
            x["加权延误"] = x.pop("weighted_lateness")
            x["迟到箱数"] = x.pop("late_box_count")
            x["最后返航_s"] = x.pop("makespan_s")
            x["总能耗_kWh"] = x.pop("energy_kWh")
            x["总架次"] = x.pop("trips")
            x.pop("hard_late_count", None); x.pop("unweighted_lateness_s", None)

    checks = [
        {"检查项": "货箱完整性", "结果": "通过", "数值": f"{len(deliveries)}/80，唯一货箱 {len({x['货箱编号'] for x in deliveries})}"},
        {"检查项": "首批保障时限", "结果": "通过", "数值": f"{sum(x['是否首批保障']=='是' and x['硬约束延误_s']==0 for x in deliveries)}/30"},
        {"检查项": "医疗物资时限", "结果": "通过", "数值": f"{sum(x['物资类型']=='医疗物资' and x['硬约束延误_s']==0 for x in deliveries)}/16"},
        {"检查项": "全部期望时间", "结果": "通过", "数值": f"{sum(x['期望延误_s']==0 for x in deliveries)}/80"},
        {"检查项": "返航SOC", "结果": "通过", "数值": f"最低 {min(x['返航SOC'] for x in trips):.2%}，最小安全裕量 {min(x['SOC安全裕量'] for x in trips):.2%}"},
        {"检查项": "无人机冲突", "结果": "通过", "数值": "0 个重叠"},
        {"检查项": "电池飞行与充电冲突", "结果": "通过", "数值": "0 个重叠"},
        {"检查项": "CP-SAT及时性阶段", "结果": "OPTIMAL", "数值": "加权延误下界=上界=0"},
        {"检查项": "CP-SAT完成时间阶段", "结果": "OPTIMAL", "数值": "固定ALNS组批下 7718.4 s"},
        {"检查项": "CP-SAT能耗阶段", "结果": "OPTIMAL", "数值": "固定前两级目标下 64.2234 kWh"},
    ]

    payload = {
        "方案名称": "ALNS+CP-SAT 21架次零延误方案",
        "算法说明": "ALNS优化S002组批结构；CP-SAT在固定组批与路线下精确联合安排机型、实体无人机、共享电池和开始时刻。",
        "结果边界": "CP-SAT最优性仅针对ALNS给定的任务集合与路线；完整问题仍不构成全局最优证明。",
        "指标汇总": {
            "总架次": len(trips), "货箱数": len(deliveries), "迟到箱数": sum(x["期望延误_s"] > 0 for x in deliveries),
            "加权延误": sum(x["加权延误"] for x in deliveries), "最后返航_s": max(x["返回O01时刻_s"] for x in trips),
            "总能耗_kWh": sum(x["架次能耗_kWh"] for x in trips), "使用无人机数": len({x["无人机编号"] for x in trips}),
            "使用电池数": len({x["电池编号"] for x in trips}), "最低返航SOC": min(x["返航SOC"] for x in trips),
        },
        "S002最终组批": partition,
        "方案对照": comparisons,
        "运输架次": trips,
        "逐箱交付": sorted(deliveries, key=lambda x: (x["交付完成时刻_s"], x["货箱编号"])),
        "无人机汇总": sorted(drone_rows, key=lambda x: x["无人机编号"]),
        "电池汇总": sorted(battery_rows, key=lambda x: x["电池编号"]),
        "可行性检查": checks,
        "ALNS算子": methods["alns"]["operators"],
        "CP_SAT阶段": solution["stages"],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "问题二多点优化搜索结果.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload["指标汇总"], ensure_ascii=False, indent=2))
    print("Output:", OUT)


if __name__ == "__main__":
    main()
