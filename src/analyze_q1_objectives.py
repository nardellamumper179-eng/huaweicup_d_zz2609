from functools import lru_cache

import numpy as np

import solve_problem1 as q1


def analyze_service(service_boxes, route, drones, reserve=0.20):
    records = service_boxes.reset_index(drop=True)
    n = len(records)
    size = 1 << n
    masses = np.zeros(size)
    volumes = np.zeros(size)
    counts = np.zeros(size, dtype=int)
    for mask in range(1, size):
        bit = mask & -mask
        idx = bit.bit_length() - 1
        prev = mask ^ bit
        masses[mask] = masses[prev] + float(records.loc[idx, "单箱质量（kg）"])
        volumes[mask] = volumes[prev] + float(records.loc[idx, "单箱体积（m³）"])
        counts[mask] = counts[prev] + 1

    choices = {}
    for mask in range(1, size):
        values = []
        for drone_id, drone in drones.iterrows():
            if masses[mask] > drone["最大载重"] + 1e-9:
                continue
            if volumes[mask] > drone["最大体积"] + 1e-9:
                continue
            energy = q1.round_trip_energy(drone, route, masses[mask])
            if energy <= (1 - reserve) * drone["可用能量"] + 1e-9:
                duration = q1.operation_time(drone, route, int(counts[mask]))
                values.append((str(drone_id), float(energy), float(duration)))
        if values:
            choices[mask] = values

    def scalar_dp(metric):
        @lru_cache(None)
        def solve(mask):
            if mask == 0:
                return (0.0, 0, 0.0, 0.0)
            first = mask & -mask
            sub = mask
            best = None
            while sub:
                if sub & first and sub in choices:
                    rest = solve(mask ^ sub)
                    for _, energy, duration in choices[sub]:
                        candidate = (
                            (energy if metric == "energy" else duration) + rest[0],
                            rest[1] + 1,
                            rest[2] + energy,
                            rest[3] + duration,
                        )
                        if best is None or candidate < best:
                            best = candidate
                sub = (sub - 1) & mask
            return best
        return solve(size - 1)

    lex, _ = q1.best_partition(records, route, drones, reserve)
    energy_opt = scalar_dp("energy")
    time_opt = scalar_dp("time")
    return {
        "lex_trips": lex[0],
        "lex_energy": lex[1],
        "lex_time": lex[2],
        "energy_opt_trips": energy_opt[1],
        "energy_min": energy_opt[2],
        "energy_opt_time": energy_opt[3],
        "time_opt_trips": time_opt[1],
        "time_opt_energy": time_opt[2],
        "time_min": time_opt[3],
    }


def main():
    origin, services, drones, boxes = q1.load_inputs()
    dem, lat_grid, lon_grid, nodata = q1.load_dem()
    routes = q1.build_route_geometry(origin, services, dem, lat_grid, lon_grid, nodata)
    rows = []
    for service_id, group in boxes.groupby("服务区编号", sort=True):
        row = {"service": service_id}
        row.update(analyze_service(group, routes.loc[service_id], drones))
        rows.append(row)
    for row in rows:
        print(row)
    print("TOTAL_LEX", sum(r["lex_trips"] for r in rows), sum(r["lex_energy"] for r in rows), sum(r["lex_time"] for r in rows))
    print("TOTAL_ENERGY_INDEPENDENT", sum(r["energy_opt_trips"] for r in rows), sum(r["energy_min"] for r in rows), sum(r["energy_opt_time"] for r in rows))
    print("TOTAL_TIME_INDEPENDENT", sum(r["time_opt_trips"] for r in rows), sum(r["time_opt_energy"] for r in rows), sum(r["time_min"] for r in rows))


if __name__ == "__main__":
    main()
