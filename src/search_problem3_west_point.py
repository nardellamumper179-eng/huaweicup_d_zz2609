from __future__ import annotations

import json

import numpy as np

from plan_problem3_relay import route_metrics
from solve_problem1 import OUTPUT_DIR, load_dem, load_inputs, nearest_indices
from solve_problem3_coverage import ACCESS_LIMIT_DB, BACKHAUL_LIMIT_DB, TerrainLink


DIRECT = OUTPUT_DIR / "问题三固定网关直连覆盖分析.json"
OUT = OUTPUT_DIR / "问题三西部中继点局部搜索.json"
BASE_LON = 109.2118354
BASE_LAT = 23.01896405
WEST_TRIPS = {"Q2-15", "Q2-16", "Q2-17", "Q2-20"}


def main():
    direct = json.loads(DIRECT.read_text(encoding="utf-8"))
    origin_data, _, _, _ = load_inputs()
    origin = (origin_data["经度"], origin_data["纬度"], origin_data["海拔"])
    gateway = (origin[0], origin[1], origin[2] + 20.0)
    dem, lat, lon, nodata = load_dem()
    terrain = TerrainLink(dem, lat, lon, nodata)
    all_rows = [r for r in direct["逐秒样本"] if r["架次编号"] in WEST_TRIPS and not r["直连可用"]]
    screen_rows = all_rows[::10] + [all_rows[-1]]
    candidates = []

    def screen(x, y):
            rr = nearest_indices(lat, np.array([y]))[0]
            cc = nearest_indices(lon, np.array([x]))[0]
            ground = float(dem[rr, cc])
            if not np.isfinite(ground) or ground == nodata:
                return
            relay = (x, y, ground + 300.0)
            back = terrain.status(relay, gateway, BACKHAUL_LIMIT_DB)
            if not back["可用"]:
                return
            margins = []
            for row in screen_rows:
                transport = (row["经度"], row["纬度"], row["飞行海拔_m"])
                margins.append(terrain.status(transport, relay, ACCESS_LIMIT_DB)["链路裕量_dB"])
            candidates.append({
                "候选点": f"WEST-{x:.6f}-{y:.6f}-H300", "经度": x, "纬度": y,
                "地面高程_m": ground, "离地高度_m": 300.0, "悬停海拔_m": relay[2],
                "初筛最小双段裕量_dB": min(min(margins), back["链路裕量_dB"]),
                "回传裕量_dB": back["链路裕量_dB"],
            })

    for dx in np.arange(-0.006, 0.0061, 0.001):
        for dy in np.arange(-0.006, 0.0061, 0.001):
            screen(BASE_LON + float(dx), BASE_LAT + float(dy))

    candidates.sort(key=lambda x: -x["初筛最小双段裕量_dB"])
    anchors = candidates[:3]
    seen = {(round(x["经度"], 7), round(x["纬度"], 7)) for x in candidates}
    for anchor in anchors:
        for dx in np.arange(-0.0015, 0.001501, 0.00025):
            for dy in np.arange(-0.0015, 0.001501, 0.00025):
                x, y = anchor["经度"] + float(dx), anchor["纬度"] + float(dy)
                key = (round(x, 7), round(y, 7))
                if key not in seen:
                    seen.add(key)
                    screen(x, y)

    candidates.sort(key=lambda x: -x["初筛最小双段裕量_dB"])
    final = []
    for point in candidates[:20]:
        relay = (point["经度"], point["纬度"], point["悬停海拔_m"])
        margins = []
        for row in all_rows:
            transport = (row["经度"], row["纬度"], row["飞行海拔_m"])
            margins.append(terrain.status(transport, relay, ACCESS_LIMIT_DB)["链路裕量_dB"])
        minimum = min(min(margins), point["回传裕量_dB"])
        final.append({
            **point, "逐秒最小双段裕量_dB": minimum,
            "不满足采样数": sum(v < 0 for v in margins),
            **route_metrics(origin, relay, dem, lat, lon, nodata),
        })
    final.sort(key=lambda x: (-x["逐秒最小双段裕量_dB"], x["去程时间_s"]))
    OUT.write_text(json.dumps({"候选总数": len(candidates), "复核候选": final}, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in final[:10]:
        print(row["候选点"], round(row["逐秒最小双段裕量_dB"], 4), round(row["去程时间_s"], 1))
    print("Output:", OUT)


if __name__ == "__main__":
    main()
