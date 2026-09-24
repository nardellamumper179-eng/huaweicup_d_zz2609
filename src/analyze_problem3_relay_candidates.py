from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from solve_problem1 import OUTPUT_DIR, load_dem, load_inputs, nearest_indices
from solve_problem3_coverage import ACCESS_LIMIT_DB, BACKHAUL_LIMIT_DB, TerrainLink


COVERAGE = OUTPUT_DIR / "问题三固定网关直连覆盖分析.json"
OUT = OUTPUT_DIR / "问题三中继候选点覆盖分析.json"


def main():
    direct = json.loads(COVERAGE.read_text(encoding="utf-8"))
    origin, services, _, _ = load_inputs()
    dem, lat_grid, lon_grid, nodata = load_dem()
    terrain = TerrainLink(dem, lat_grid, lon_grid, nodata)
    gateway = (origin["经度"], origin["纬度"], origin["海拔"] + 20.0)

    def ground_at(lon, lat):
        r = nearest_indices(lat_grid, np.array([lat]))[0]
        c = nearest_indices(lon_grid, np.array([lon]))[0]
        value = float(dem[r, c])
        if not math.isfinite(value) or value == nodata:
            return None
        return value

    service_points = {str(r["服务区编号"]): (float(r["经度"]), float(r["纬度"])) for _, r in services.iterrows()}
    candidates = []
    used = set()

    def add(name, lon, lat, height=300.0):
        ground = ground_at(lon, lat)
        if ground is None:
            return
        key = (round(lon, 6), round(lat, 6), round(height, 1))
        if key in used:
            return
        used.add(key)
        candidates.append({"候选点": name, "经度": lon, "纬度": lat, "地面高程_m": ground, "离地高度_m": height, "悬停海拔_m": ground + height})

    add("O01-H300", origin["经度"], origin["纬度"], 300)
    affected = sorted({x["服务区编号"] for x in direct["通信缺口"]})
    for sid in affected:
        lon, lat = service_points[sid]
        add(f"{sid}-H300", lon, lat, 300)
        add(f"O01-{sid}-MID-H300", (origin["经度"] + lon) / 2, (origin["纬度"] + lat) / 2, 300)
    lons = [origin["经度"]] + [service_points[x][0] for x in affected]
    lats = [origin["纬度"]] + [service_points[x][1] for x in affected]
    for i, lon in enumerate(np.linspace(min(lons), max(lons), 7)):
        for j, lat in enumerate(np.linspace(min(lats), max(lats), 7)):
            add(f"GRID-{i+1}-{j+1}-H300", float(lon), float(lat), 300)

    sample_lookup = {}
    for x in direct["逐秒样本"]:
        if not x["直连可用"]:
            sample_lookup[(x["架次编号"], round(x["时刻_s"], 6))] = x
    gaps = direct["通信缺口"]
    gap_samples = {}
    for gap in gaps:
        rows = [v for (trip, tm), v in sample_lookup.items() if trip == gap["架次编号"] and gap["缺口开始_s"] <= tm < gap["缺口结束_s"]]
        selected = [x for idx, x in enumerate(rows) if idx % 5 == 0]
        if rows and rows[-1] not in selected:
            selected.append(rows[-1])
        gap_samples[gap["缺口编号"]] = selected

    matrix = []
    for ci, cand in enumerate(candidates, 1):
        pos = (cand["经度"], cand["纬度"], cand["悬停海拔_m"])
        backhaul = terrain.status(pos, gateway, BACKHAUL_LIMIT_DB)
        covered, ratios = [], {}
        for gap in gaps:
            rows = gap_samples[gap["缺口编号"]]
            ok = 0
            margins = []
            for row in rows:
                transport = (row["经度"], row["纬度"], row["飞行海拔_m"])
                status = terrain.status(transport, pos, ACCESS_LIMIT_DB)
                available = backhaul["可用"] and status["可用"]
                ok += int(available)
                margins.append(min(backhaul["链路裕量_dB"], status["链路裕量_dB"]))
            ratio = ok / len(rows) if rows else 1.0
            ratios[gap["缺口编号"]] = {"覆盖比例": ratio, "最小双段裕量_dB": min(margins) if margins else None}
            if ratio >= 1 - 1e-12:
                covered.append(gap["缺口编号"])
        matrix.append({
            **cand, "回传可用": backhaul["可用"], "回传遮挡": backhaul["遮挡"], "回传裕量_dB": backhaul["链路裕量_dB"],
            "完整覆盖缺口数": len(covered), "完整覆盖缺口": covered, "逐缺口结果": ratios,
        })
        if ci % 10 == 0:
            print(f"evaluated {ci}/{len(candidates)}")

    matrix.sort(key=lambda x: (-x["完整覆盖缺口数"], -x["回传裕量_dB"]))
    result = {
        "候选点数": len(matrix), "缺口数": len(gaps), "粗筛采样间隔_s": 5,
        "最佳候选": matrix[:20], "全部候选": matrix,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(pd.DataFrame([{k: x[k] for k in ["候选点", "经度", "纬度", "悬停海拔_m", "回传可用", "回传裕量_dB", "完整覆盖缺口数"]} for x in matrix[:20]]).to_string(index=False))
    print("Output:", OUT)


if __name__ == "__main__":
    main()
