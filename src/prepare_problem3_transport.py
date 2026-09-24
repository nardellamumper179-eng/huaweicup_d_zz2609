from __future__ import annotations

import copy
import json

import pandas as pd

import experiment_problem2_methods as exp
from solve_problem1 import BASE_DIR, OUTPUT_DIR, load_dem, load_inputs
from solve_problem2_baseline import charger_time, load_resource_data
from solve_problem2_multistop import build_all_segments, evaluate_task_model


SOURCE = OUTPUT_DIR / "问题二ALNS_CP_SAT最终结果.json"
OUT = OUTPUT_DIR / "问题三通信协调运输方案.json"


def main():
    q2 = json.loads(SOURCE.read_text(encoding="utf-8"))
    result = copy.deepcopy(q2)
    shifts = {
        "Q2-05": 7.0, "Q2-06": 7.0, "Q2-07": 7.0, "Q2-08": 7.0, "Q2-11": 7.0,
        "Q2-12": 7.0, "Q2-14": 173.0, "Q2-15": 349.0, "Q2-16": 122.0,
        "Q2-18": 173.0, "Q2-19": 349.0, "Q2-20": 122.0,
    }
    for trip in result["运输架次"]:
        delta = shifts.get(trip["架次编号"], 0.0)
        if trip["架次编号"] == "Q2-13":
            continue
        trip["开始时刻_s"] += delta
        trip["返回O01时刻_s"] += delta
        trip["电池充满时刻_s"] += delta
    for row in result["逐箱交付"]:
        if row["架次编号"] == "Q2-13":
            continue
        delta = shifts.get(row["架次编号"], 0.0)
        row["交付完成时刻_s"] += delta
        row["硬约束延误_s"] = 0.0 if row["硬约束截止_s"] is None else max(0.0, row["交付完成时刻_s"] - row["硬约束截止_s"])
        row["期望延误_s"] = max(0.0, row["交付完成时刻_s"] - row["期望送达_s"])
        row["加权延误"] = row["期望延误_s"] * row["应急优先系数"]

    types, box_map, drones, battery_stock, tasks, cache = exp.build_problem()
    origin, services, _, _ = load_inputs()
    dem, lat, lon, nodata = load_dem()
    segments = build_all_segments(origin, services, dem, lat, lon, nodata)
    t19 = next(t for t in tasks if t["任务编号"] == "T19")
    model_a = evaluate_task_model(t19, "A", types.loc["A"], segments, box_map)
    if model_a is None:
        raise RuntimeError("T19 is not feasible on A")
    _, batteries = load_resource_data()
    full_a = float(batteries.loc[batteries["机型"].astype(str) == "A", "满充时间_s"].iloc[0])
    trip13 = next(x for x in result["运输架次"] if x["架次编号"] == "Q2-13")
    trip13.update({
        "无人机编号": "U02", "机型编号": "A", "电池编号": "A-BAT-04", "开始时刻_s": 0.0,
        "返回O01时刻_s": model_a["时长"],
        "电池充满时刻_s": model_a["时长"] + charger_time(model_a["返航SOC"], full_a),
        "飞行作业时长_s": model_a["时长"],
        "电池占用时长_s": model_a["时长"] + charger_time(model_a["返航SOC"], full_a),
        "架次能耗_kWh": model_a["能耗"], "返航SOC": model_a["返航SOC"],
        "返航余量要求": float(types.loc["A", "返航余量"]),
        "SOC安全裕量": model_a["返航SOC"] - float(types.loc["A", "返航余量"]),
    })
    for row in result["逐箱交付"]:
        if row["架次编号"] != "Q2-13":
            continue
        tm = model_a["送达偏移"][row["货箱编号"]]
        row.update({
            "无人机编号": "U02", "电池编号": "A-BAT-04", "交付完成时刻_s": tm,
            "硬约束延误_s": 0.0 if row["硬约束截止_s"] is None else max(0.0, tm - row["硬约束截止_s"]),
            "期望延误_s": max(0.0, tm - row["期望送达_s"]),
        })
        row["加权延误"] = row["期望延误_s"] * row["应急优先系数"]

    result["方案名称"] = "问题三通信协调运输方案"
    result["运输调整说明"] = "保持问题二组批与路线不变，通过调整部分架次开始时刻并提前S014食品架次，为两架中继无人机留出区域轮换时间。"
    result["指标汇总"] = {
        "总架次": len(result["运输架次"]), "货箱数": len(result["逐箱交付"]),
        "迟到箱数": sum(x["期望延误_s"] > 1e-9 for x in result["逐箱交付"]),
        "加权延误": sum(x["加权延误"] for x in result["逐箱交付"]),
        "最后返航_s": max(x["返回O01时刻_s"] for x in result["运输架次"]),
        "总能耗_kWh": sum(x["架次能耗_kWh"] for x in result["运输架次"]),
        "使用无人机数": len({x["无人机编号"] for x in result["运输架次"]}),
        "使用电池数": len({x["电池编号"] for x in result["运输架次"]}),
        "最低返航SOC": min(x["返航SOC"] for x in result["运输架次"]),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["指标汇总"], ensure_ascii=False, indent=2))
    print("Output:", OUT)


if __name__ == "__main__":
    main()
