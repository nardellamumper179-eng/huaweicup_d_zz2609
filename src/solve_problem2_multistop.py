from __future__ import annotations

import itertools
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from solve_problem1 import (
    BASE_DIR,
    OUTPUT_DIR,
    equivalent_range,
    haversine_m,
    leg_energy,
    load_dem,
    load_inputs,
    nearest_indices,
)
from solve_problem2_baseline import charger_time, load_resource_data, make_batches, ordered_box_ids


OUT_JSON = OUTPUT_DIR / "问题二多点优化搜索结果.json"
RANDOM_SEED = 20260923


def build_all_segments(origin, services, dem, lat_grid, lon_grid, nodata):
    nodes = {origin["编号"]: {"经度": origin["经度"], "纬度": origin["纬度"], "作业海拔": origin["海拔"]}}
    for _, s in services.iterrows():
        nodes[str(s["服务区编号"])] = {
            "经度": float(s["经度"]),
            "纬度": float(s["纬度"]),
            "作业海拔": float(s["海拔"]) + 30.0,
        }
    rows = []
    for a, b in itertools.permutations(nodes, 2):
        na, nb = nodes[a], nodes[b]
        distance = haversine_m(na["经度"], na["纬度"], nb["经度"], nb["纬度"])
        count = max(2, int(math.ceil(distance / 5.0)) + 1)
        lons = np.linspace(na["经度"], nb["经度"], count)
        lats = np.linspace(na["纬度"], nb["纬度"], count)
        rr = nearest_indices(lat_grid, lats)
        cc = nearest_indices(lon_grid, lons)
        elev = dem[rr, cc]
        elev = elev[np.isfinite(elev) & (elev != nodata)]
        cruise = float(elev.max()) + 50.0
        rows.append({
            "起点": a,
            "终点": b,
            "水平距离_m": distance,
            "最高地形_m": cruise - 50.0,
            "巡航海拔_m": cruise,
            "爬升_m": max(0.0, cruise - na["作业海拔"]),
            "下降_m": max(0.0, cruise - nb["作业海拔"]),
        })
    return pd.DataFrame(rows).set_index(["起点", "终点"])


def segment_time(typ, seg):
    return float(
        seg["爬升_m"] / typ["爬升速度"]
        + seg["水平距离_m"] / typ["巡航速度"]
        + seg["下降_m"] / typ["下降速度"]
    )


def task_from_batch(row, box_map, task_id):
    ids = [x.strip() for x in row["货箱编号"].split(",")]
    return {"任务编号": task_id, "停靠": ((str(row["服务区编号"]), tuple(ids)),), "来源": f"{row['服务区编号']}-B{int(row['批次'])}"}


def task_stats(task, box_map):
    ids = [bid for _, group in task["停靠"] for bid in group]
    selected = box_map.loc[ids]
    first = selected[selected["是否首批保障"] == "是"]
    medical = selected[selected["物资类型"] == "医疗物资"]
    hard = math.inf
    if len(first):
        hard = min(hard, float(first["首批截止时间（s）"].min()))
    if len(medical):
        hard = min(hard, float(medical["期望送达时间（s）"].min()))
    return {
        "箱数": len(ids),
        "质量": float(selected["单箱质量（kg）"].sum()),
        "体积": float(selected["单箱体积（m³）"].sum()),
        "硬截止": hard,
        "软截止": float(selected["期望送达时间（s）"].min()),
        "优先分": float(selected["应急优先系数"].sum()),
    }


def evaluate_task_model(task, g, typ, segments, box_map):
    stats = task_stats(task, box_map)
    if stats["质量"] > typ["最大载重"] + 1e-9 or stats["体积"] > typ["最大体积"] + 1e-9:
        return None
    payload = stats["质量"]
    energy = 0.0
    elapsed = float(typ["准备时间"] + stats["箱数"] * typ["每箱装载时间"])
    deliveries = {}
    current = "O01"
    for stop, ids_tuple in task["停靠"]:
        seg = segments.loc[(current, stop)]
        energy += leg_energy(typ, seg["水平距离_m"], seg["爬升_m"], payload)
        elapsed += segment_time(typ, seg)
        elapsed += float(typ["基础交接时间"])
        ids = ordered_box_ids(", ".join(ids_tuple), box_map)
        for bid in ids:
            elapsed += float(typ["每箱交接时间"])
            deliveries[bid] = elapsed
        payload -= float(box_map.loc[ids, "单箱质量（kg）"].sum())
        current = stop
    seg = segments.loc[(current, "O01")]
    energy += leg_energy(typ, seg["水平距离_m"], seg["爬升_m"], payload)
    elapsed += segment_time(typ, seg)
    if energy > (1 - float(typ["返航余量"])) * typ["可用能量"] + 1e-9:
        return None
    delivery_meta = []
    for bid, offset in deliveries.items():
        box = box_map.loc[bid]
        hard_deadline = math.inf
        if box["是否首批保障"] == "是":
            hard_deadline = min(hard_deadline, float(box["首批截止时间（s）"]))
        if box["物资类型"] == "医疗物资":
            hard_deadline = min(hard_deadline, float(box["期望送达时间（s）"]))
        delivery_meta.append((bid, offset, hard_deadline, float(box["期望送达时间（s）"]), float(box["应急优先系数"])))
    return {
        "机型": str(g), "能耗": energy, "时长": elapsed, "送达偏移": deliveries,
        "送达数据": delivery_meta, "返航SOC": 1 - energy / typ["可用能量"],
    }


def merge_tasks(a, b, order, box_map, task_id):
    stop_boxes = {}
    sources = []
    for task in (a, b):
        sources.append(task["来源"])
        for stop, ids in task["停靠"]:
            stop_boxes.setdefault(stop, []).extend(ids)
    stops = tuple((s, tuple(stop_boxes[s])) for s in order)
    return {"任务编号": task_id, "停靠": stops, "来源": "+".join(sources)}


def hard_violation(box, delivery):
    violation = 0.0
    if box["是否首批保障"] == "是":
        violation = max(violation, delivery - float(box["首批截止时间（s）"]))
    if box["物资类型"] == "医疗物资":
        violation = max(violation, delivery - float(box["期望送达时间（s）"]))
    return max(0.0, violation)


def default_orders(tasks, box_map):
    stats = {t["任务编号"]: task_stats(t, box_map) for t in tasks}

    def hard_key(t):
        s = stats[t["任务编号"]]
        return (
            0 if math.isfinite(s["硬截止"]) else 1,
            s["硬截止"] if math.isfinite(s["硬截止"]) else s["软截止"],
            -s["优先分"],
            t["任务编号"],
        )

    def effective_key(t):
        s = stats[t["任务编号"]]
        return (min(s["硬截止"], s["软截止"]), 0 if math.isfinite(s["硬截止"]) else 1, -s["优先分"], t["任务编号"])

    def soft_key(t):
        s = stats[t["任务编号"]]
        return (s["软截止"], 0 if math.isfinite(s["硬截止"]) else 1, -s["优先分"], t["任务编号"])

    return [
        [t["任务编号"] for t in sorted(tasks, key=hard_key)],
        [t["任务编号"] for t in sorted(tasks, key=effective_key)],
        [t["任务编号"] for t in sorted(tasks, key=soft_key)],
    ]


def schedule_plan(tasks, model_cache, drones, battery_stock, box_map, task_order=None, detail=True):
    drone_ready = {str(u): 0.0 for u in drones["无人机编号"]}
    battery_ready, battery_full = {}, {}
    for _, row in battery_stock.iterrows():
        g = str(row["机型"])
        for k in range(1, int(row["电池数"]) + 1):
            key = f"{g}-BAT-{k:02d}"
            battery_ready[key] = 0.0
            battery_full[key] = float(row["满充时间_s"])

    task_by_id = {t["任务编号"]: t for t in tasks}
    ordered_tasks = [task_by_id[x] for x in task_order] if task_order is not None else [task_by_id[x] for x in default_orders(tasks, box_map)[0]]
    schedule, deliveries = [], []
    total_hard_count = 0
    total_hard_lateness = 0.0
    total_weighted_lateness = 0.0
    total_energy = 0.0
    final_return = 0.0
    for task in ordered_tasks:
        candidates = []
        for g, model in model_cache[task["任务编号"]].items():
            model_drones = drones.loc[drones["机型"].astype(str) == g, "无人机编号"].astype(str)
            u = min(model_drones, key=lambda x: (drone_ready[x], x))
            model_batteries = [x for x in battery_ready if x.startswith(g + "-")]
            bat = min(model_batteries, key=lambda x: (battery_ready[x], x))
            start = max(drone_ready[u], battery_ready[bat])
            box_deliveries = {bid: start + offset for bid, offset in model["送达偏移"].items()}
            hard_values = [max(0.0, start + offset - hard) for _, offset, hard, _, _ in model["送达数据"]]
            hard_count = sum(x > 1e-9 for x in hard_values)
            hard_total = sum(hard_values)
            weighted_late = sum(weight * max(0.0, start + offset - expected) for _, offset, _, expected, weight in model["送达数据"])
            end = start + model["时长"]
            candidates.append((hard_count, hard_total, weighted_late, end, model["能耗"], start, u, bat, model, box_deliveries))
        if not candidates:
            return None
        hard_count, hard_total, weighted_late, end, energy, start, u, bat, model, box_deliveries = min(candidates)
        g = model["机型"]
        charge_end = end + charger_time(model["返航SOC"], battery_full[bat])
        total_hard_count += hard_count
        total_hard_lateness += hard_total
        total_weighted_lateness += weighted_late
        total_energy += energy
        final_return = max(final_return, end)
        if detail:
            stats = task_stats(task, box_map)
            schedule.append({
                "任务编号": task["任务编号"], "来源批次": task["来源"],
                "路线": "O01-" + "-".join(s for s, _ in task["停靠"]) + "-O01",
                "机型": g, "无人机编号": u, "电池编号": bat,
                "开始_s": start, "返回_s": end, "充满_s": charge_end,
                "箱数": stats["箱数"], "载荷_kg": stats["质量"],
                "体积_m3": stats["体积"], "能耗_kWh": model["能耗"], "返航SOC": model["返航SOC"],
            })
            for bid, tm in box_deliveries.items():
                box = box_map.loc[bid]
                deliveries.append({
                    "货箱编号": bid, "服务区编号": box["服务区编号"], "任务编号": task["任务编号"],
                    "送达时刻_s": tm, "首批截止_s": box["首批截止时间（s）"], "期望送达_s": box["期望送达时间（s）"],
                    "硬约束延误_s": hard_violation(box, tm),
                    "期望延误_s": max(0.0, tm - float(box["期望送达时间（s）"])),
                    "加权延误": float(box["应急优先系数"]) * max(0.0, tm - float(box["期望送达时间（s）"])),
                })
        drone_ready[u] = end
        battery_ready[bat] = charge_end
    objective = (
        int(total_hard_count), float(total_hard_lateness), float(total_weighted_lateness),
        float(final_return), float(total_energy), len(tasks),
    )
    if not detail:
        return objective, None, None
    s = pd.DataFrame(schedule)
    d = pd.DataFrame(deliveries)
    return objective, s, d


def mutate_order(order, rng):
    result = list(order)
    move = rng.randrange(3)
    if move == 0:
        i = rng.randrange(len(result) - 1)
        result[i], result[i + 1] = result[i + 1], result[i]
    elif move == 1:
        i, j = rng.sample(range(len(result)), 2)
        result[i], result[j] = result[j], result[i]
    else:
        i, j = sorted(rng.sample(range(len(result)), 2))
        item = result.pop(i)
        result.insert(j, item)
    return result


def search_orders(tasks, cache, drones, battery_stock, box_map, seed_orders, iterations, rng):
    seen = set()
    evaluated = []

    def consider(order):
        key = tuple(order)
        if key in seen:
            return None
        seen.add(key)
        result = schedule_plan(tasks, cache, drones, battery_stock, box_map, order, detail=False)
        if result is not None:
            evaluated.append((result[0], list(order), result))
        return result

    for order in seed_orders:
        consider(order)
    best = min(evaluated, key=lambda x: x[0])
    zero_hard = [x for x in evaluated if x[0][0] == 0]
    best_zero = min(zero_hard, key=lambda x: x[0]) if zero_hard else None

    for k in range(iterations):
        anchor = best_zero if best_zero is not None and rng.random() < 0.8 else best
        candidate_order = list(anchor[1])
        for _ in range(1 if rng.random() < 0.75 else rng.randint(2, 4)):
            candidate_order = mutate_order(candidate_order, rng)
        result = consider(candidate_order)
        if result is None:
            continue
        entry = evaluated[-1]
        if entry[0] < best[0]:
            best = entry
        if entry[0][0] == 0 and (best_zero is None or entry[0] < best_zero[0]):
            best_zero = entry

    return best, best_zero, len(seen)


def replacement_orders(base_order, removed, merged_id):
    positions = [base_order.index(x) for x in removed]
    stripped = [x for x in base_order if x not in removed]
    inserts = {min(positions), max(positions) - 1, len(stripped)}
    result = []
    for pos in inserts:
        order = list(stripped)
        order.insert(max(0, min(pos, len(order))), merged_id)
        result.append(order)
    return result


def records(df):
    return json.loads(df.to_json(orient="records", force_ascii=False))


def run():
    origin, services, types, _ = load_inputs()
    boxes_df = pd.read_excel(BASE_DIR / "物资需求与配送时限.xlsx", sheet_name="逐箱货箱清单")
    box_map = boxes_df.set_index("货箱编号")
    batches, _ = make_batches()
    drones, battery_stock = load_resource_data()
    dem, lat, lon, nodata = load_dem()
    segments = build_all_segments(origin, services, dem, lat, lon, nodata)

    base_tasks = [task_from_batch(row, box_map, f"T{i:02d}") for i, (_, row) in enumerate(batches.iterrows(), start=1)]

    def models_for(task):
        result = {}
        for g, typ in types.iterrows():
            model = evaluate_task_model(task, str(g), typ, segments, box_map)
            if model is not None:
                result[str(g)] = model
        return result

    base_cache = {t["任务编号"]: models_for(t) for t in base_tasks}
    rng = random.Random(RANDOM_SEED)
    base_search, base_zero, base_count = search_orders(
        base_tasks, base_cache, drones, battery_stock, box_map,
        default_orders(base_tasks, box_map), 5000, rng,
    )
    base_best = base_zero or base_search
    candidate_log = [{"候选": "19架次顺序优化", "合并": "无", "目标": str(base_best[0]), "搜索顺序数": base_count}]

    counter = 1000
    merge_candidates = []
    for i, j in itertools.combinations(range(len(base_tasks)), 2):
        a, b = base_tasks[i], base_tasks[j]
        unique_stops = list(dict.fromkeys([s for s, _ in a["停靠"]] + [s for s, _ in b["停靠"]]))
        for order in itertools.permutations(unique_stops):
            counter += 1
            merged = merge_tasks(a, b, order, box_map, f"M{counter}")
            merged_models = models_for(merged)
            if not merged_models:
                continue
            plan = [t for k, t in enumerate(base_tasks) if k not in (i, j)] + [merged]
            cache = {t["任务编号"]: (merged_models if t is merged else base_cache[t["任务编号"]]) for t in plan}
            removed = [a["任务编号"], b["任务编号"]]
            seeds = default_orders(plan, box_map) + replacement_orders(base_best[1], removed, merged["任务编号"])
            evaluated = []
            for seed in seeds:
                result = schedule_plan(plan, cache, drones, battery_stock, box_map, seed, detail=False)
                if result is not None:
                    evaluated.append((result[0], seed, result))
            if not evaluated:
                continue
            initial = min(evaluated, key=lambda x: x[0])
            candidate_log.append({"候选": merged["任务编号"], "合并": merged["来源"] + " / " + "-".join(order), "目标": str(initial[0]), "搜索顺序数": len(seeds)})
            if initial[0][0] == 0:
                merge_candidates.append((initial, plan, cache, merged))

    merge_candidates.sort(key=lambda x: x[0][0])
    finalists = merge_candidates[:30]
    best_18 = None
    total_18_orders = 0
    for initial, plan, cache, merged in finalists:
        searched, zero, count = search_orders(
            plan, cache, drones, battery_stock, box_map,
            default_orders(plan, box_map) + [initial[1]], 1000, rng,
        )
        total_18_orders += count
        contender = zero or searched
        candidate_log.append({
            "候选": merged["任务编号"] + "-局部搜索", "合并": merged["来源"],
            "目标": str(contender[0]), "搜索顺序数": count,
        })
        if contender[0][0] == 0 and (best_18 is None or contender[0] < best_18[0][0]):
            best_18 = (contender, plan, cache)

    # The declared lexicographic objective is used for the primary output.
    # The best feasible 18-trip plan remains a Pareto comparison, not an
    # automatic replacement of the primary plan.
    chosen, chosen_tasks, chosen_cache = base_best, base_tasks, base_cache
    objective, chosen_order, _ = chosen
    objective, schedule_df, deliveries_df = schedule_plan(
        chosen_tasks, chosen_cache, drones, battery_stock, box_map, chosen_order, detail=True
    )
    summary = pd.DataFrame([{
        "硬约束迟到箱数": objective[0], "硬约束延误总秒": objective[1], "加权延误": objective[2],
        "最后返航_s": objective[3], "总能耗_kWh": objective[4], "总架次": objective[5],
        "使用无人机数": schedule_df["无人机编号"].nunique(), "使用电池数": schedule_df["电池编号"].nunique(),
    }])
    assert len(deliveries_df) == 80 and deliveries_df["货箱编号"].nunique() == 80
    for _, row in schedule_df.iterrows():
        assert row["返航SOC"] >= float(types.loc[row["机型"], "返航余量"]) - 1e-9
    payload = {
        "随机种子": RANDOM_SEED,
        "19架次搜索顺序数": base_count,
        "18架次候选数": len(merge_candidates),
        "深入搜索候选数": len(finalists),
        "18架次深入搜索顺序数": total_18_orders,
        "选择方案": "按字典序目标的19架次方案",
        "任务顺序": chosen_order,
        "指标汇总": records(summary),
        "运输架次": records(schedule_df),
        "逐箱送达": records(deliveries_df),
        "对照指标": [
            {"方案": "19架次顺序优化", "目标": list(base_best[0])},
            {"方案": "18架次最佳可行" if best_18 is not None else "18架次未找到硬约束可行解", "目标": list(best_18[0][0]) if best_18 is not None else None},
        ],
        "候选搜索": candidate_log,
        "全航段参数": records(segments.reset_index()),
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))
    print(schedule_df.to_string(index=False))
    print("19-trip best:", base_best[0])
    print("18-trip best:", best_18[0][0] if best_18 is not None else None)
    print("Output:", OUT_JSON)


if __name__ == "__main__":
    run()
