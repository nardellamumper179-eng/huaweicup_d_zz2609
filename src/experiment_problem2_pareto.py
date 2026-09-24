from __future__ import annotations

import itertools
import json
import random
import time
from pathlib import Path

from deap import base, creator, tools

import experiment_problem2_methods as exp
from solve_problem1 import OUTPUT_DIR, load_dem, load_inputs
from solve_problem2_multistop import RANDOM_SEED, build_all_segments, default_orders, evaluate_task_model, schedule_plan, search_orders


OUT = OUTPUT_DIR / "问题二候选组批与多目标实验.json"


def partitions_k(items, k):
    n = len(items)
    for labels in itertools.product(range(k), repeat=n):
        if labels[0] != 0 or set(labels) != set(range(k)):
            continue
        canonical = []
        mapping = {}
        next_label = 0
        valid = True
        for x in labels:
            if x not in mapping:
                mapping[x] = next_label
                next_label += 1
            canonical.append(mapping[x])
        if tuple(canonical) != labels:
            continue
        groups = [[] for _ in range(k)]
        for item, label in zip(items, labels):
            groups[label].append(item)
        yield exp.canonical_partition(groups)


def normalize_labels(labels):
    mapping = {}
    nxt = 0
    out = []
    for x in labels:
        if x not in mapping:
            mapping[x] = nxt
            nxt += 1
        out.append(mapping[x])
    return out


def main():
    started = time.time()
    types, box_map, drones, battery_stock, base_tasks, base_cache = exp.build_problem()
    origin, services, _, _ = load_inputs()
    dem, lat, lon, nodata = load_dem()
    exp.segments_global = build_all_segments(origin, services, dem, lat, lon, nodata)
    fixed = [t for t in base_tasks if all(stop != "S002" for stop, _ in t["停靠"])]
    ids = sorted(box_map[box_map["服务区编号"] == "S002"].index.astype(str))
    model_cache = {}
    eval_cache = {}

    def models(group):
        key = tuple(sorted(group))
        if key not in model_cache:
            task = exp.task_from_ids("S002", key, "TMP")
            model_cache[key] = {
                str(g): tm for g, typ in types.iterrows()
                if (tm := evaluate_task_model(task, str(g), typ, exp.segments_global, box_map)) is not None
            }
        return model_cache[key]

    def build(partition):
        extra = [exp.task_from_ids("S002", group, f"P2-{i:02d}") for i, group in enumerate(partition, 1)]
        if any(not models(group) for group in partition):
            return None, None
        tasks = fixed + extra
        cache = {t["任务编号"]: (base_cache[t["任务编号"]] if t in fixed else models(t["停靠"][0][1])) for t in tasks}
        return tasks, cache

    def quick_eval(partition):
        partition = exp.canonical_partition(partition)
        if partition in eval_cache:
            return eval_cache[partition]
        tasks, cache = build(partition)
        if tasks is None:
            result = (99, 1e9, 1e12, 1e9, 1e9, 99)
        else:
            vals = [schedule_plan(tasks, cache, drones, battery_stock, box_map, order, detail=False)[0] for order in default_orders(tasks, box_map)]
            result = min(vals)
        eval_cache[partition] = result
        return result

    screened = {}
    refined = {}
    cp_results = {}
    for k in (2, 3):
        candidates = [(quick_eval(p), p) for p in partitions_k(ids, k)]
        candidates.sort(key=lambda x: x[0])
        screened[str(k)] = [{"objective": x[0], "partition": x[1]} for x in candidates[:12]]
        best = None
        rng = random.Random(RANDOM_SEED + k)
        for _, p in candidates[:12]:
            tasks, cache = build(p)
            searched, zero, count = search_orders(tasks, cache, drones, battery_stock, box_map, default_orders(tasks, box_map), 900, rng)
            contender = zero or searched
            entry = (contender[0], p, contender[1], tasks, cache, count)
            if best is None or entry[0] < best[0]:
                best = entry
        refined[str(k)] = {"objective": best[0], "partition": best[1], "order_count": best[5]}
        cp_results[str(k)] = exp.cp_sat_schedule(types, box_map, drones, battery_stock, best[3], best[4], time_limit=90)

    if not hasattr(creator, "FitnessP2"):
        creator.create("FitnessP2", base.Fitness, weights=(-1.0, -1.0, -1.0, -1.0))
        creator.create("IndividualP2", list, fitness=creator.FitnessP2)
    toolbox = base.Toolbox()
    rng = random.Random(RANDOM_SEED + 99)
    toolbox.register("individual", tools.initIterate, creator.IndividualP2, lambda: normalize_labels([rng.randrange(4) for _ in ids]))
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    def evaluate_ind(ind):
        labels = normalize_labels(ind)
        groups = [[] for _ in range(max(labels) + 1)]
        for bid, label in zip(ids, labels): groups[label].append(bid)
        if not 2 <= len(groups) <= 4:
            return 1e12, 1e9, 1e9, 99
        obj = quick_eval(groups)
        if obj[0] > 0:
            return 1e12 + obj[1], obj[3], obj[4], obj[5]
        return obj[2], obj[3], obj[4], obj[5]

    def mutate(ind):
        for i in range(len(ind)):
            if rng.random() < 0.18:
                ind[i] = rng.randrange(4)
        ind[:] = normalize_labels(ind)
        return (ind,)

    toolbox.register("evaluate", evaluate_ind)
    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", mutate)
    toolbox.register("select", tools.selNSGA2)
    pop = toolbox.population(n=48)
    for ind in pop: ind.fitness.values = toolbox.evaluate(ind)
    pop = toolbox.select(pop, len(pop))
    for _ in range(35):
        offspring = tools.selTournamentDCD(pop, len(pop))
        offspring = [toolbox.clone(ind) for ind in offspring]
        for a, b in zip(offspring[::2], offspring[1::2]):
            if rng.random() < 0.8:
                toolbox.mate(a, b); del a.fitness.values; del b.fitness.values
        for ind in offspring:
            if rng.random() < 0.35:
                toolbox.mutate(ind); del ind.fitness.values
        for ind in offspring:
            if not ind.fitness.valid: ind.fitness.values = toolbox.evaluate(ind)
        pop = toolbox.select(pop + offspring, 48)
    front = tools.sortNondominated(pop, len(pop), first_front_only=True)[0]
    pareto = []
    seen = set()
    for ind in front:
        labels = normalize_labels(ind); groups = [[] for _ in range(max(labels) + 1)]
        for bid, label in zip(ids, labels): groups[label].append(bid)
        p = exp.canonical_partition(groups)
        if p in seen: continue
        seen.add(p)
        pareto.append({"partition": p, "metrics": ind.fitness.values, "lexicographic": quick_eval(p)})
    pareto.sort(key=lambda x: x["metrics"])

    result = {
        "screened": screened,
        "refined": refined,
        "candidate_generation_cp_sat": {k: v["objective"] for k, v in cp_results.items()},
        "candidate_generation_cp_sat_detail": cp_results,
        "nsga2_pareto": pareto,
        "evaluated_partitions": len(eval_cache),
        "elapsed_s": time.time() - started,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Refined", json.dumps(refined, ensure_ascii=False))
    print("CP", json.dumps(result["candidate_generation_cp_sat"], ensure_ascii=False))
    print("Pareto", json.dumps(pareto[:10], ensure_ascii=False))
    print("Evaluated", len(eval_cache), "elapsed", result["elapsed_s"])
    print("Output", OUT)


if __name__ == "__main__":
    main()
