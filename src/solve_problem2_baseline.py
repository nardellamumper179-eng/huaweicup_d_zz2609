from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from solve_problem1 import (
    BASE_DIR,
    OUTPUT_DIR,
    build_route_geometry,
    flight_time,
    load_dem,
    load_inputs,
    leg_energy,
    load_inputs,
    operation_time,
)


P1 = OUTPUT_DIR / "问题一计算结果.xlsx"
OUT = OUTPUT_DIR / "问题二基线调度.xlsx"


def charger_time(soc: float, full: float) -> float:
    if soc < 0.90:
        return full * (0.65 * (0.90 - soc) / 0.90 + 0.35)
    return full * 0.35 * (1.0 - soc) / 0.10


def load_resource_data():
    raw = pd.read_excel(BASE_DIR / "运输无人机数据.xlsx", sheet_name="数据", header=None)
    # Rows 8:16 contain all eight physical transport drones U01-U08.
    drones = raw.iloc[8:16, :3].copy()
    drones.columns = ["无人机编号", "机型", "初始位置"]
    drones = drones.dropna(subset=["无人机编号", "机型"]).reset_index(drop=True)
    assert len(drones) == 8 and set(drones["无人机编号"].astype(str)) == {f"U{i:02d}" for i in range(1, 9)}
    batteries = raw.iloc[19:22, :3].copy()
    batteries.columns = ["机型", "电池数", "满充时间_s"]
    return drones, batteries


def make_batches():
    b = pd.read_excel(P1, sheet_name="最优组批方案")
    boxes = pd.read_excel(BASE_DIR / "物资需求与配送时限.xlsx", sheet_name="逐箱货箱清单")
    box_map = boxes.set_index("货箱编号")
    rows = []
    for _, r in b.iterrows():
        ids = [x.strip() for x in str(r["货箱编号"]).split(",")]
        selected = box_map.loc[ids]
        first = selected[selected["是否首批保障"] == "是"]
        first_deadline = first["首批截止时间（s）"].dropna().min() if len(first) else math.inf
        medical = selected[selected["物资类型"] == "医疗物资"]
        medical_deadline = medical["期望送达时间（s）"].min() if len(medical) else math.inf
        expected = selected["期望送达时间（s）"].min()
        rows.append({
            "服务区编号": r["服务区编号"],
            "批次": int(r["批次"]),
            "机型": r["机型"],
            "货箱编号": ", ".join(ids),
            "箱数": len(ids),
            "载荷_kg": float(r["载荷_kg"]),
            "体积_m3": float(r["体积_m3"]),
            "首批截止_s": float(first_deadline),
            "医疗截止_s": float(medical_deadline),
            "期望时限_s": float(expected),
            "首批箱数": len(first),
        })
    result = pd.DataFrame(rows)

    # S002: swap identical water boxes so both first-aid boxes ride in the small batch.
    s002_large = result.index[(result["服务区编号"] == "S002") & (result["载荷_kg"] > 30)][0]
    s002_small = result.index[(result["服务区编号"] == "S002") & (result["载荷_kg"] <= 30)][0]
    result.loc[s002_large, "货箱编号"] = result.loc[s002_large, "货箱编号"].replace("S002-WAT-01", "S002-WAT-04")
    result.loc[s002_small, "货箱编号"] = result.loc[s002_small, "货箱编号"].replace("S002-WAT-04", "S002-WAT-01")
    result.loc[s002_large, ["首批截止_s", "医疗截止_s", "首批箱数"]] = [math.inf, math.inf, 0]
    result.loc[s002_small, ["首批截止_s", "医疗截止_s", "首批箱数"]] = [3600.0, 3600.0, 2]

    # S014: separate the non-urgent food box so an A drone can deliver both first-aid boxes immediately.
    s014 = result.index[result["服务区编号"] == "S014"][0]
    base = result.loc[s014].copy()
    urgent_ids = ["S014-MED-01", "S014-WAT-01"]
    later_ids = ["S014-FOD-01"]

    def batch_row(template, ids, batch_no):
        selected = box_map.loc[ids]
        row = template.copy()
        row["批次"] = batch_no
        row["货箱编号"] = ", ".join(ids)
        row["箱数"] = len(ids)
        row["载荷_kg"] = float(selected["单箱质量（kg）"].sum())
        row["体积_m3"] = float(selected["单箱体积（m³）"].sum())
        first = selected[selected["是否首批保障"] == "是"]
        medical = selected[selected["物资类型"] == "医疗物资"]
        row["首批截止_s"] = float(first["首批截止时间（s）"].min()) if len(first) else math.inf
        row["医疗截止_s"] = float(medical["期望送达时间（s）"].min()) if len(medical) else math.inf
        row["期望时限_s"] = float(selected["期望送达时间（s）"].min())
        row["首批箱数"] = len(first)
        return row

    result = result.drop(index=s014)
    result = pd.concat(
        [result, pd.DataFrame([batch_row(base, urgent_ids, 1), batch_row(base, later_ids, 2)])],
        ignore_index=True,
    )
    return result, box_map


def ordered_box_ids(text: str, box_map: pd.DataFrame):
    ids = [x.strip() for x in text.split(",")]
    return sorted(
        ids,
        key=lambda bid: (
            0 if box_map.loc[bid, "是否首批保障"] == "是" else 1,
            float(box_map.loc[bid, "首批截止时间（s）"])
            if pd.notna(box_map.loc[bid, "首批截止时间（s）"])
            else math.inf,
            float(box_map.loc[bid, "期望送达时间（s）"]),
            -float(box_map.loc[bid, "应急优先系数"]),
            bid,
        ),
    )


def run():
    origin, services, types, _ = load_inputs()
    dem, lat, lon, nodata = load_dem()
    routes = build_route_geometry(origin, services, dem, lat, lon, nodata)
    batches, box_map = make_batches()
    drones, battery_stock = load_resource_data()
    drone_ready = {u: 0.0 for u in drones["无人机编号"]}
    battery_ready = {}
    battery_full = {}
    for _, row in battery_stock.iterrows():
        g = str(row["机型"])
        for k in range(1, int(row["电池数"]) + 1):
            key = f"{g}-BAT-{k:02d}"
            battery_ready[key] = 0.0
            battery_full[key] = float(row["满充时间_s"])

    # Urgent batches first; among equal deadlines, prioritize larger emergency score.
    priority = []
    for idx, r in batches.iterrows():
        selected = box_map.loc[[x.strip() for x in r["货箱编号"].split(",")]]
        score = float(selected["应急优先系数"].sum())
        hard_deadline = min(r["首批截止_s"], r["医疗截止_s"])
        priority.append((
            0 if math.isfinite(hard_deadline) else 1,
            hard_deadline if math.isfinite(hard_deadline) else r["期望时限_s"],
            -score,
            idx,
        ))
    batches = batches.loc[[x[3] for x in sorted(priority)]].reset_index(drop=True)

    schedule = []
    violations = []
    for task_no, r in batches.iterrows():
        route = routes.loc[r["服务区编号"]]
        candidates = []
        for g, typ in types.iterrows():
            g = str(g)
            if r["载荷_kg"] > typ["最大载重"] + 1e-9 or r["体积_m3"] > typ["最大体积"] + 1e-9:
                continue
            drone_candidates = drones[drones["机型"].astype(str) == g]
            bat_candidates = [k for k in battery_ready if k.startswith(g + "-")]
            for _, drow in drone_candidates.iterrows():
                u = drow["无人机编号"]
                for bat in bat_candidates:
                    start = max(drone_ready[u], battery_ready[bat])
                    energy = leg_energy(typ, route["水平距离_m"], route["去程爬升_m"], r["载荷_kg"]) + leg_energy(
                        typ, route["水平距离_m"], route["返程爬升_m"], 0.0
                    )
                    soc_after = 1.0 - energy / float(typ["可用能量"])
                    if soc_after < float(typ["返航余量"]) - 1e-9:
                        continue
                    travel_out = route["去程爬升_m"] / typ["爬升速度"] + route["水平距离_m"] / typ["巡航速度"] + route["去程下降_m"] / typ["下降速度"]
                    arrival = start + float(typ["准备时间"] + r["箱数"] * typ["每箱装载时间"] + travel_out)
                    end = start + operation_time(typ, route, int(r["箱数"]))
                    charge_end = end + charger_time(soc_after, battery_full[bat])
                    candidates.append((arrival, energy, end, start, u, bat, charge_end, soc_after, g))
        if not candidates:
            raise RuntimeError(f"No feasible resource for task {task_no + 1}: {r.to_dict()}")
        arrival, energy, end, start, u, bat, charge_end, soc_after, g = min(candidates)
        typ = types.loc[g]
        ids = ordered_box_ids(r["货箱编号"], box_map)
        delivery_rows = []
        t = arrival + float(typ["基础交接时间"])
        for box_id in ids:
            t += float(typ["每箱交接时间"])
            delivery_rows.append((box_id, t))
        first_deliveries = [t for bid, t in delivery_rows if bool(box_map.loc[bid, "是否首批保障"] == "是")]
        first_delivery = min(first_deliveries) if first_deliveries else math.inf
        expected_lateness = sum(max(0.0, t - float(box_map.loc[bid, "期望送达时间（s）"])) for bid, t in delivery_rows)
        first_late = max(0.0, first_delivery - r["首批截止_s"]) if math.isfinite(r["首批截止_s"]) else 0.0
        if first_late > 0:
            violations.append(("首批", r["服务区编号"], r["批次"], first_late))
        schedule.append({
            "架次": task_no + 1,
            "服务区编号": r["服务区编号"],
            "批次": r["批次"],
            "机型": g,
            "无人机编号": u,
            "电池编号": bat,
            "开始_s": start,
            "到达服务区_s": arrival,
            "返回调度中心_s": end,
            "电池充满_s": charge_end,
            "载荷_kg": r["载荷_kg"],
            "箱数": r["箱数"],
            "能耗_kWh": energy,
            "返航SOC": soc_after,
            "首批送达_s": first_delivery,
            "首批截止_s": r["首批截止_s"],
            "期望时限_s": r["期望时限_s"],
            "期望延误箱秒": expected_lateness,
        })
        drone_ready[u] = end
        battery_ready[bat] = charge_end

    schedule_df = pd.DataFrame(schedule)
    deliveries = []
    for _, s in schedule_df.iterrows():
        ids = ordered_box_ids(batches.loc[int(s["架次"]) - 1, "货箱编号"], box_map)
        typ = types.loc[s["机型"]]
        t = s["到达服务区_s"] + float(typ["基础交接时间"])
        for bid in ids:
            t += float(typ["每箱交接时间"])
            box = box_map.loc[bid]
            deliveries.append({
                "货箱编号": bid,
                "服务区编号": box["服务区编号"],
                "架次": s["架次"],
                "无人机编号": s["无人机编号"],
                "电池编号": s["电池编号"],
                "送达时刻_s": t,
                "首批截止_s": box["首批截止时间（s）"],
                "期望送达_s": box["期望送达时间（s）"],
                "首批是否按时": (pd.isna(box["首批截止时间（s）"]) or t <= box["首批截止时间（s）"] + 1e-9),
                "医疗是否按时": (box["物资类型"] != "医疗物资" or t <= box["期望送达时间（s）"] + 1e-9),
                "期望延误_s": max(0.0, t - box["期望送达时间（s）"]),
                "加权延误": float(box["应急优先系数"]) * max(0.0, t - box["期望送达时间（s）"]),
            })
    deliveries_df = pd.DataFrame(deliveries)
    summary = pd.DataFrame([{
        "总架次": len(schedule_df),
        "总能耗_kWh": schedule_df["能耗_kWh"].sum(),
        "最后返航_s": schedule_df["返回调度中心_s"].max(),
        "首批按时箱数": int(deliveries_df.loc[deliveries_df["首批截止_s"].notna(), "首批是否按时"].sum()),
        "首批箱总数": int(deliveries_df["首批截止_s"].notna().sum()),
        "医疗按时箱数": int(deliveries_df.loc[box_map.loc[deliveries_df["货箱编号"], "物资类型"].to_numpy() == "医疗物资", "医疗是否按时"].sum()),
        "医疗箱总数": int((box_map["物资类型"] == "医疗物资").sum()),
        "期望延误总秒数": deliveries_df["期望延误_s"].sum(),
        "加权延误总值": deliveries_df["加权延误"].sum(),
        "使用运输无人机数": schedule_df["无人机编号"].nunique(),
        "使用电池数": schedule_df["电池编号"].nunique(),
    }])
    drone_summary = schedule_df.groupby(["无人机编号", "机型"], as_index=False).agg(
        执行架次=("架次", "count"),
        首次开始_s=("开始_s", "min"),
        最后返航_s=("返回调度中心_s", "max"),
        总能耗_kWh=("能耗_kWh", "sum"),
    )
    battery_summary = schedule_df.groupby("电池编号", as_index=False).agg(
        使用次数=("架次", "count"),
        首次使用_s=("开始_s", "min"),
        最后返航_s=("返回调度中心_s", "max"),
        最后充满_s=("电池充满_s", "max"),
        最低返航SOC=("返航SOC", "min"),
    )

    assert len(deliveries_df) == len(box_map) == deliveries_df["货箱编号"].nunique()
    for _, row in schedule_df.iterrows():
        assert row["返航SOC"] >= float(types.loc[row["机型"], "返航余量"]) - 1e-9
    assert summary.loc[0, "首批按时箱数"] == summary.loc[0, "首批箱总数"]
    assert summary.loc[0, "医疗按时箱数"] == summary.loc[0, "医疗箱总数"]
    for _, group in schedule_df.groupby("无人机编号"):
        ordered = group.sort_values("开始_s")
        assert all(
            ordered.iloc[i]["开始_s"] >= ordered.iloc[i - 1]["返回调度中心_s"] - 1e-9
            for i in range(1, len(ordered))
        )
    for _, group in schedule_df.groupby("电池编号"):
        ordered = group.sort_values("开始_s")
        assert all(
            ordered.iloc[i]["开始_s"] >= ordered.iloc[i - 1]["电池充满_s"] - 1e-9
            for i in range(1, len(ordered))
        )
    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, sheet_name="架次调度", index=False)
        deliveries_df.to_excel(writer, sheet_name="逐箱送达", index=False)
        summary.to_excel(writer, sheet_name="指标汇总", index=False)
        drone_summary.to_excel(writer, sheet_name="无人机使用汇总", index=False)
        battery_summary.to_excel(writer, sheet_name="电池使用汇总", index=False)
    print(summary.to_string(index=False))
    print("首批 violations:", violations)
    print("Output:", OUT)


if __name__ == "__main__":
    run()
