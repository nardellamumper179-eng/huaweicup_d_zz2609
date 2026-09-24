from __future__ import annotations

import json
import math

import numpy as np

from solve_problem1 import OUTPUT_DIR, haversine_m, load_dem, load_inputs, nearest_indices
from solve_problem3_coverage import ACCESS_LIMIT_DB, BACKHAUL_LIMIT_DB, TerrainLink


DIRECT = OUTPUT_DIR / "问题三固定网关直连覆盖分析.json"
OUT = OUTPUT_DIR / "问题三中继候选点加密搜索.json"


def main():
    data = json.loads(DIRECT.read_text(encoding="utf-8"))
    origin, _, _, _ = load_inputs()
    dem, lat_grid, lon_grid, nodata = load_dem()
    terrain = TerrainLink(dem, lat_grid, lon_grid, nodata)
    gateway = (origin["经度"], origin["纬度"], origin["海拔"] + 20.0)
    required = {"Q2-01-G01", "Q2-02-G01", "Q2-09-G01", "Q2-09-G02", "Q2-09-G03", "Q2-11-G01", "Q2-12-G01"}
    gaps = {x["缺口编号"]: x for x in data["通信缺口"] if x["缺口编号"] in required}
    sample_lookup = {}
    for x in data["逐秒样本"]:
        if not x["直连可用"] and x["架次编号"] in {g["架次编号"] for g in gaps.values()}:
            sample_lookup.setdefault(x["架次编号"], []).append(x)
    samples = {}
    for gid, gap in gaps.items():
        rows = [x for x in sample_lookup[gap["架次编号"]] if gap["缺口开始_s"] <= x["时刻_s"] < gap["缺口结束_s"]]
        samples[gid] = rows[::8] + ([rows[-1]] if rows and rows[-1] not in rows[::8] else [])

    def ground(lon, lat):
        rr = nearest_indices(lat_grid, np.array([lat]))[0]; cc = nearest_indices(lon_grid, np.array([lon]))[0]
        return float(dem[rr, cc])

    feasible = []
    lon_values = np.linspace(109.205, 109.225, 17)
    lat_values = np.linspace(23.032, 23.048, 17)
    for lon in lon_values:
        for lat in lat_values:
            z_ground = ground(float(lon), float(lat))
            for h in (220.0, 260.0, 300.0):
                pos = (float(lon), float(lat), z_ground + h)
                back = terrain.status(pos, gateway, BACKHAUL_LIMIT_DB)
                if not back["可用"]:
                    continue
                all_ok = True; min_margin = back["链路裕量_dB"]
                for gid in required:
                    for row in samples[gid]:
                        tr = (row["经度"], row["纬度"], row["飞行海拔_m"])
                        st = terrain.status(tr, pos, ACCESS_LIMIT_DB)
                        min_margin = min(min_margin, st["链路裕量_dB"])
                        if not st["可用"]:
                            all_ok = False; break
                    if not all_ok: break
                if all_ok:
                    feasible.append({
                        "候选点": f"REF-{lon:.6f}-{lat:.6f}-H{int(h)}", "经度": float(lon), "纬度": float(lat),
                        "地面高程_m": z_ground, "离地高度_m": h, "悬停海拔_m": z_ground + h,
                        "距O01_m": haversine_m(origin["经度"], origin["纬度"], float(lon), float(lat)),
                        "最小双段裕量_dB": min_margin, "回传裕量_dB": back["链路裕量_dB"],
                    })
    feasible.sort(key=lambda x: (x["距O01_m"], -x["最小双段裕量_dB"]))
    OUT.write_text(json.dumps({"要求覆盖": sorted(required), "可行点数": len(feasible), "可行候选": feasible}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(feasible[:15], ensure_ascii=False, indent=2))
    print("Output:", OUT)


if __name__ == "__main__":
    main()
