from __future__ import annotations

import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
from ortools.sat.python import cp_model

from solve_problem1 import BASE_DIR, OUTPUT_DIR, load_dem, load_inputs
from solve_problem2_baseline import charger_time, load_resource_data, make_batches
from solve_problem2_multistop import (
    RANDOM_SEED,
    build_all_segments,
    default_orders,
    evaluate_task_model,
    search_orders,
    schedule_plan,
    task_from_batch,
)


OUT = OUTPUT_DIR / "问题二多方法实验结果.json"
TIME_SCALE = 10  # 0.1 second units
ENERGY_SCALE = 10000


def build_problem():
    origin, services, types, _ = load_inputs()
    boxes = pd.read_excel(BASE_DIR / "物资需求与配送时限.xlsx", sheet_name="逐箱货箱清单")
    box_map = boxes.set_index("货箱编号")
    batches, _ = make_batches()
    drones, battery_stock = load_resource_data()
    dem, lat, lon, nodata = load_dem()
    segments = build_all_segments(origin, services, dem, lat, lon, nodata)
    tasks = [task_from_batch(row, box_map, f"T{i:02d}") for i, (_, row) in enumerate(batches.iterrows(), 1)]

    def models_for(task):
        result = {}
        for g, typ in types.iterrows():
            model = evaluate_task_model(task, str(g), typ, segments, box_map)
            if model is not None:
                result[str(g)] = model
        return result

    cache = {t["任务编号"]: models_for(t) for t in tasks}
    return types, box_map, drones, battery_stock, tasks, cache


def cp_sat_schedule(types, box_map, drones, battery_stock, tasks, cache, time_limit=120):
    model = cp_model.CpModel()
    horizon = 20000 * TIME_SCALE
    task_ids = [t["任务编号"] for t in tasks]
    start = {tid: model.NewIntVar(0, horizon, f"start_{tid}") for tid in task_ids}
    end = {tid: model.NewIntVar(0, horizon, f"end_{tid}") for tid in task_ids}
    choices = defaultdict(list)
    drone_intervals = defaultdict(list)
    battery_intervals = defaultdict(list)
    delivery = {}
    lateness = {}
    choice_meta = {}

    battery_full = {}
    for _, row in battery_stock.iterrows():
        g = str(row["机型"])
        for k in range(1, int(row["电池数"]) + 1):
            battery_full[f"{g}-BAT-{k:02d}"] = float(row["满充时间_s"])

    drones_by_type = {
        g: drones.loc[drones["机型"].astype(str) == g, "无人机编号"].astype(str).tolist()
        for g in types.index.astype(str)
    }
    batteries_by_type = {g: sorted(x for x in battery_full if x.startswith(g + "-")) for g in types.index.astype(str)}

    for task in tasks:
        tid = task["任务编号"]
        for g, tm in cache[tid].items():
            flight = int(math.ceil(tm["时长"] * TIME_SCALE))
            charge = int(math.ceil(charger_time(tm["返航SOC"], battery_full[batteries_by_type[g][0]]) * TIME_SCALE))
            for u in drones_by_type[g]:
                for bat in batteries_by_type[g]:
                    key = (tid, g, u, bat)
                    p = model.NewBoolVar("use_" + "_".join(key))
                    choices[tid].append(p)
                    model.Add(end[tid] == start[tid] + flight).OnlyEnforceIf(p)
                    dint = model.NewOptionalIntervalVar(start[tid], flight, end[tid], p, "dr_" + "_".join(key))
                    bend = model.NewIntVar(0, horizon + 10000 * TIME_SCALE, "bend_" + "_".join(key))
                    model.Add(bend == start[tid] + flight + charge).OnlyEnforceIf(p)
                    bint = model.NewOptionalIntervalVar(start[tid], flight + charge, bend, p, "bat_" + "_".join(key))
                    drone_intervals[u].append(dint)
                    battery_intervals[bat].append(bint)
                    choice_meta[key] = {
                        "presence": p, "flight": flight, "charge": charge, "model": tm,
                        "energy": int(round(tm["能耗"] * ENERGY_SCALE)),
                    }
        model.AddExactlyOne(choices[tid])

        ids = [bid for _, group in task["停靠"] for bid in group]
        for bid in ids:
            delivery[bid] = model.NewIntVar(0, horizon, f"delivery_{bid}")
            box = box_map.loc[bid]
            for (ctid, g, u, bat), meta in choice_meta.items():
                if ctid != tid:
                    continue
                offset = int(math.ceil(meta["model"]["送达偏移"][bid] * TIME_SCALE))
                model.Add(delivery[bid] == start[tid] + offset).OnlyEnforceIf(meta["presence"])
            hard_deadlines = []
            if box["是否首批保障"] == "是":
                hard_deadlines.append(float(box["首批截止时间（s）"]))
            if box["物资类型"] == "医疗物资":
                hard_deadlines.append(float(box["期望送达时间（s）"]))
            if hard_deadlines:
                model.Add(delivery[bid] <= int(math.floor(min(hard_deadlines) * TIME_SCALE)))
            expected = int(round(float(box["期望送达时间（s）"]) * TIME_SCALE))
            lateness[bid] = model.NewIntVar(0, horizon, f"late_{bid}")
            model.Add(lateness[bid] >= delivery[bid] - expected)

    for intervals in drone_intervals.values():
        model.AddNoOverlap(intervals)
    for intervals in battery_intervals.values():
        model.AddNoOverlap(intervals)

    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, list(end.values()))
    weighted_lateness = sum(int(round(float(box_map.loc[bid, "应急优先系数"]))) * var for bid, var in lateness.items())
    energy = sum(meta["energy"] * meta["presence"] for meta in choice_meta.values())

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = RANDOM_SEED
    solver.parameters.log_search_progress = False

    stages = []
    for name, expression, limit in [
        ("weighted_lateness", weighted_lateness, time_limit * 0.55),
        ("makespan", makespan, time_limit * 0.30),
        ("energy", energy, time_limit * 0.15),
    ]:
        model.Minimize(expression)
        solver.parameters.max_time_in_seconds = max(5, limit)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(f"CP-SAT failed at {name}: {solver.StatusName(status)}")
        value = int(round(solver.Value(expression)))
        stages.append({"stage": name, "status": solver.StatusName(status), "value": value, "bound": solver.BestObjectiveBound()})
        model.Add(expression == value)

    rows = []
    for task in tasks:
        tid = task["任务编号"]
        selected = None
        for key, meta in choice_meta.items():
            if key[0] == tid and solver.BooleanValue(meta["presence"]):
                selected = (key, meta)
                break
        if selected is None:
            raise RuntimeError(f"No selected assignment for {tid}")
        (tid, g, u, bat), meta = selected
        rows.append({
            "任务编号": tid, "机型": g, "无人机编号": u, "电池编号": bat,
            "开始_s": solver.Value(start[tid]) / TIME_SCALE,
            "返回_s": solver.Value(end[tid]) / TIME_SCALE,
            "充满_s": (solver.Value(start[tid]) + meta["flight"] + meta["charge"]) / TIME_SCALE,
            "能耗_kWh": meta["model"]["能耗"], "返航SOC": meta["model"]["返航SOC"],
        })
    delivery_rows = []
    for bid in delivery:
        t = solver.Value(delivery[bid]) / TIME_SCALE
        expected = float(box_map.loc[bid, "期望送达时间（s）"])
        late = max(0.0, t - expected)
        delivery_rows.append({
            "货箱编号": bid, "送达时刻_s": t, "期望送达_s": expected,
            "期望延误_s": late, "权重": float(box_map.loc[bid, "应急优先系数"]),
            "加权延误": late * float(box_map.loc[bid, "应急优先系数"]),
        })
    return {
        "method": "CP-SAT固定组批与路线精确资源排程",
        "stages": stages,
        "objective": {
            "hard_late_count": 0,
            "weighted_lateness": sum(x["加权延误"] for x in delivery_rows),
            "unweighted_lateness_s": sum(x["期望延误_s"] for x in delivery_rows),
            "late_box_count": sum(x["期望延误_s"] > 1e-9 for x in delivery_rows),
            "makespan_s": max(x["返回_s"] for x in rows),
            "energy_kWh": sum(x["能耗_kWh"] for x in rows),
            "trips": len(rows),
        },
        "schedule": rows,
        "deliveries": delivery_rows,
    }


def task_from_ids(service, ids, task_id):
    return {"任务编号": task_id, "停靠": ((service, tuple(ids)),), "来源": f"{service}-ALNS"}


def canonical_partition(groups):
    return tuple(sorted(tuple(sorted(g)) for g in groups if g))


def alns_s002(types, box_map, drones, battery_stock, base_tasks, base_cache, iterations=350):
    rng = random.Random(RANDOM_SEED + 17)
    fixed = [t for t in base_tasks if all(stop != "S002" for stop, _ in t["停靠"])]
    s002_tasks = [t for t in base_tasks if any(stop == "S002" for stop, _ in t["停靠"])]
    initial = canonical_partition([[bid for _, ids in t["停靠"] for bid in ids] for t in s002_tasks])
    model_cache = {}
    evaluation_cache = {}

    def models_for(task):
        ids_key = tuple(sorted(bid for _, ids in task["停靠"] for bid in ids))
        if ids_key not in model_cache:
            models = {}
            for g, typ in types.iterrows():
                tm = evaluate_task_model(task, str(g), typ, segments_global, box_map)
                if tm is not None:
                    models[str(g)] = tm
            model_cache[ids_key] = models
        return model_cache[ids_key]

    def build(partition):
        extra = [task_from_ids("S002", group, f"A2-{i:02d}") for i, group in enumerate(partition, 1)]
        tasks = fixed + extra
        cache = {t["任务编号"]: (base_cache[t["任务编号"]] if t in fixed else models_for(t)) for t in tasks}
        if any(not cache[t["任务编号"]] for t in tasks):
            return None, None
        return tasks, cache

    def evaluate(partition):
        key = canonical_partition(partition)
        if key in evaluation_cache:
            return evaluation_cache[key]
        tasks, cache = build(key)
        if tasks is None:
            evaluation_cache[key] = None
            return None
        searched, zero, count = search_orders(
            tasks, cache, drones, battery_stock, box_map,
            default_orders(tasks, box_map), 180, rng,
        )
        best = zero or searched
        result = {"objective": best[0], "order": best[1], "tasks": tasks, "cache": cache, "orders": count}
        evaluation_cache[key] = result
        return result

    def score(obj):
        return obj[0] * 1e12 + obj[1] * 1e8 + obj[2] * 1e3 + obj[3] + obj[4] + obj[5]

    def feasible_groups(groups):
        key = canonical_partition(groups)
        if not key or len(key) > 5:
            return None
        all_ids = [x for group in key for x in group]
        expected = sorted(box_map[box_map["服务区编号"] == "S002"].index.astype(str))
        if sorted(all_ids) != expected or len(all_ids) != len(set(all_ids)):
            return None
        for i, group in enumerate(key, 1):
            if not models_for(task_from_ids("S002", group, f"CHK{i}")):
                return None
        return key

    def mutate(partition, op):
        groups = [list(g) for g in partition]
        if op == "move" and groups:
            src = rng.randrange(len(groups)); bid = rng.choice(groups[src]); groups[src].remove(bid)
            targets = list(range(len(groups) + 1)); dst = rng.choice(targets)
            if dst == len(groups): groups.append([bid])
            else: groups[dst].append(bid)
        elif op == "swap" and len(groups) >= 2:
            a, b = rng.sample(range(len(groups)), 2); ia = rng.randrange(len(groups[a])); ib = rng.randrange(len(groups[b])); groups[a][ia], groups[b][ib] = groups[b][ib], groups[a][ia]
        elif op == "split" and groups:
            candidates = [i for i, g in enumerate(groups) if len(g) >= 2]
            if candidates:
                i = rng.choice(candidates); rng.shuffle(groups[i]); cut = rng.randrange(1, len(groups[i])); groups.append(groups[i][cut:]); groups[i] = groups[i][:cut]
        elif op == "merge" and len(groups) >= 2:
            a, b = sorted(rng.sample(range(len(groups)), 2)); groups[a].extend(groups[b]); groups.pop(b)
        elif op == "repack":
            ids = [x for g in groups for x in g]
            rng.shuffle(ids); groups = []
            for bid in ids:
                positions = list(range(len(groups) + 1)); rng.shuffle(positions); placed = False
                for pos in positions:
                    trial = [list(g) for g in groups]
                    if pos == len(trial): trial.append([bid])
                    else: trial[pos].append(bid)
                    if feasible_groups(trial): groups = trial; placed = True; break
                if not placed: groups.append([bid])
        return feasible_groups(groups)

    operators = ["move", "swap", "split", "merge", "repack"]
    weights = {op: 1.0 for op in operators}
    usage = {op: 0 for op in operators}
    wins = {op: 0 for op in operators}
    current = initial
    current_eval = evaluate(current)
    best, best_eval = current, current_eval
    temperature = max(1.0, score(current_eval["objective"]) * 0.02)
    history = []
    for it in range(iterations):
        op = rng.choices(operators, weights=[weights[x] for x in operators], k=1)[0]
        usage[op] += 1
        candidate = mutate(current, op)
        if candidate is None or candidate == current:
            continue
        ev = evaluate(candidate)
        if ev is None:
            continue
        delta = score(ev["objective"]) - score(current_eval["objective"])
        accepted = delta <= 0 or rng.random() < math.exp(-min(delta / max(temperature, 1e-9), 50))
        if accepted:
            current, current_eval = candidate, ev
        reward = 0.2
        if ev["objective"] < best_eval["objective"]:
            best, best_eval = candidate, ev
            wins[op] += 1
            reward = 5.0
            history.append({"iteration": it, "operator": op, "partition": best, "objective": best_eval["objective"]})
        elif accepted:
            reward = 1.0
        weights[op] = 0.85 * weights[op] + 0.15 * reward
        temperature *= 0.985

    return {
        "partition": best,
        "heuristic_objective": best_eval["objective"],
        "operators": {op: {"uses": usage[op], "wins": wins[op], "weight": weights[op]} for op in operators},
        "unique_partitions": len(evaluation_cache),
        "history": history,
        "tasks": best_eval["tasks"], "cache": best_eval["cache"],
    }


def main():
    started = time.time()
    types, box_map, drones, battery_stock, tasks, cache = build_problem()
    current = json.loads((OUTPUT_DIR / "问题二多点优化搜索结果.json").read_text(encoding="utf-8"))
    global segments_global
    # Reuse the already computed geometry held by task models by rebuilding once
    # for ALNS-created batches.
    origin, services, _, _ = load_inputs()
    dem, lat, lon, nodata = load_dem()
    segments_global = build_all_segments(origin, services, dem, lat, lon, nodata)
    cp_result = cp_sat_schedule(types, box_map, drones, battery_stock, tasks, cache)
    alns = alns_s002(types, box_map, drones, battery_stock, tasks, cache)
    alns_cp = cp_sat_schedule(types, box_map, drones, battery_stock, alns.pop("tasks"), alns.pop("cache"), time_limit=120)
    results = {
        "current_local_search": current["指标汇总"][0],
        "cp_sat": cp_result,
        "alns": alns,
        "alns_cp_sat": alns_cp,
        "elapsed_s": time.time() - started,
    }
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CP-SAT fixed:", json.dumps(results["cp_sat"]["objective"], ensure_ascii=False))
    print("ALNS heuristic:", results["alns"]["heuristic_objective"])
    print("ALNS+CP-SAT:", json.dumps(results["alns_cp_sat"]["objective"], ensure_ascii=False))
    print("Output:", OUT)


if __name__ == "__main__":
    main()
