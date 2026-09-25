from __future__ import annotations

import json
from collections import defaultdict

from solve_problem1 import OUTPUT_DIR, load_dem, load_inputs
from solve_problem3_joint import verify_communications


DIRECT = OUTPUT_DIR / "问题三固定网关直连覆盖分析.json"
JOINT = OUTPUT_DIR / "问题三运输与中继联合调度最终结果.json"
OUT = OUTPUT_DIR / "问题三中继链路损耗敏感性.json"
EXTRA_LOSS_DB = (0.0, 0.1, 0.25, 0.5, 1.0)


def main():
    direct = json.loads(DIRECT.read_text(encoding="utf-8"))
    joint = json.loads(JOINT.read_text(encoding="utf-8"))
    origin, _, _, _ = load_inputs()
    dem, lat, lon, nodata = load_dem()
    position = (origin["经度"], origin["纬度"], origin["海拔"])
    rows, _ = verify_communications(
        direct, joint["中继架次"], position, dem, lat, lon, nodata
    )
    by_region = defaultdict(list)
    for row in rows:
        by_region[row["服务区域"]].append(row)
    regions = []
    for region, samples in by_region.items():
        margins = [x["双段最小裕量_dB"] for x in samples]
        regions.append({
            "服务区域": region,
            "直连缺口样本数": len(samples),
            "最小双段裕量_dB": min(margins),
            "附加损耗情景": [
                {
                    "额外损耗_dB": loss,
                    "失去中继覆盖样本数": sum(margin < loss for margin in margins),
                }
                for loss in EXTRA_LOSS_DB
            ],
        })
    result = {
        "数据来源": [DIRECT.name, JOINT.name],
        "情景定义": "只对现有直连缺口样本的中继接入与回传链路同时增加相同传播损耗；直连缺口集合、飞行路线、中继位置与时序保持不变。",
        "适用边界": "这是固定缺口样本的链路预算敏感性，不代表DEM高程、定位误差或直连链路同时恶化后的全过程鲁棒验证。",
        "区域结果": regions,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in regions:
        print(row["服务区域"], "最小裕量", round(row["最小双段裕量_dB"], 6),
              "失去覆盖样本", [(x["额外损耗_dB"], x["失去中继覆盖样本数"])
                         for x in row["附加损耗情景"]])
    print("Output:", OUT)


if __name__ == "__main__":
    main()
