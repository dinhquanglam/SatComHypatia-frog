#!/usr/bin/env python3

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def run_cmd(cmd, cwd):
    print("[run] (cwd={}) {}".format(cwd, " ".join(cmd)))
    subprocess.run(cmd, cwd=str(cwd), check=True)


def get_constellation_base_name(main_script):
    stem = Path(main_script).stem
    if stem.startswith("main_"):
        return stem[len("main_"):]
    return stem


def get_constellation_name(constellation_base_name, isls_selection, gs_selection, dynamic_state_algorithm):
    return "{}_{}_{}_{}".format(
        constellation_base_name,
        isls_selection,
        gs_selection,
        dynamic_state_algorithm
    )


def get_dynamic_state_dir(gen_data_dir, constellation_name, time_step_ms, duration_s):
    return gen_data_dir / constellation_name / "dynamic_state_{}ms_for_{}s".format(time_step_ms, duration_s)


def count_fstate_files(dynamic_state_dir):
    return len(list(dynamic_state_dir.glob("fstate_*.txt")))


def expected_time_steps(duration_s, time_step_ms):
    return int((duration_s * 1000) / time_step_ms)


def run_generation(cfg, sat_state_dir, duration_s, time_step_ms, algorithm):
    cmd = [
        "python3",
        cfg["main_script"],
        str(duration_s),
        str(time_step_ms),
        cfg["isls_selection"],
        cfg["ground_station_selection"],
        algorithm,
        str(cfg["num_threads"])
    ]
    run_cmd(cmd, sat_state_dir)


def ensure_dynamic_state(
        cfg,
        sat_state_dir,
        gen_data_dir,
        constellation_base_name,
        duration_s,
        time_step_ms,
        algorithm,
        reuse_existing
):
    constellation_name = get_constellation_name(
        constellation_base_name,
        cfg["isls_selection"],
        cfg["ground_station_selection"],
        algorithm
    )
    dynamic_state_dir = get_dynamic_state_dir(gen_data_dir, constellation_name, time_step_ms, duration_s)
    expected_files = expected_time_steps(duration_s, time_step_ms)

    if reuse_existing and dynamic_state_dir.is_dir() and count_fstate_files(dynamic_state_dir) == expected_files:
        print("[skip] reusing existing dynamic state {}".format(dynamic_state_dir))
        return constellation_name, dynamic_state_dir

    run_generation(cfg, sat_state_dir, duration_s, time_step_ms, algorithm)

    if not dynamic_state_dir.is_dir():
        raise RuntimeError("Dynamic state directory not found after generation: {}".format(dynamic_state_dir))
    if count_fstate_files(dynamic_state_dir) != expected_files:
        raise RuntimeError(
            "Unexpected number of fstate files in {} (got {}, expected {})".format(
                dynamic_state_dir,
                count_fstate_files(dynamic_state_dir),
                expected_files
            )
        )

    return constellation_name, dynamic_state_dir


def parse_args():
    parser = argparse.ArgumentParser(description="Run papier3 routing experiments")
    parser.add_argument(
        "--config",
        default="papier3/config/experiment_config.json",
        help="Path to experiment config JSON"
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip quick smoke verification for baseline/FROG/DA-FW"
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Skip dynamic-state generation and only run analysis/plot scripts"
    )
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Regenerate dynamic state even if expected files already exist"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    config_path = (repo_root / args.config).resolve()
    with open(config_path, "r") as f_in:
        cfg = json.load(f_in)

    sat_state_dir = (repo_root / cfg["satellite_networks_state_dir"]).resolve()
    gen_data_dir = sat_state_dir / "gen_data"
    results_dir = (repo_root / cfg["results_dir"]).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    constellation_base_name = get_constellation_base_name(cfg["main_script"])
    reuse_existing = bool(cfg.get("reuse_existing_dynamic_state", True)) and not args.force_regenerate

    smoke_outputs = []
    if not args.skip_smoke:
        print("[phase] smoke verification")
        for algorithm in cfg["smoke_verify_algorithms"]:
            constellation_name, dynamic_state_dir = ensure_dynamic_state(
                cfg,
                sat_state_dir,
                gen_data_dir,
                constellation_base_name,
                cfg["smoke_duration_s"],
                cfg["smoke_time_step_ms"],
                algorithm,
                reuse_existing=False
            )
            smoke_outputs.append({
                "algorithm": algorithm,
                "constellation_name": constellation_name,
                "dynamic_state_dir": str(dynamic_state_dir)
            })
        print("[done] smoke verification")

    experiment_outputs = []
    if not args.skip_generation:
        print("[phase] full dynamic-state generation")
        for algo_entry in cfg["algorithms"]:
            algorithm = algo_entry["dynamic_state_algorithm"]
            label = algo_entry["label"]
            constellation_name, dynamic_state_dir = ensure_dynamic_state(
                cfg,
                sat_state_dir,
                gen_data_dir,
                constellation_base_name,
                cfg["duration_s"],
                cfg["time_step_ms"],
                algorithm,
                reuse_existing=reuse_existing
            )
            experiment_outputs.append({
                "label": label,
                "algorithm": algorithm,
                "constellation_name": constellation_name,
                "dynamic_state_dir": str(dynamic_state_dir)
            })
        print("[done] full dynamic-state generation")
    else:
        for algo_entry in cfg["algorithms"]:
            algorithm = algo_entry["dynamic_state_algorithm"]
            label = algo_entry["label"]
            constellation_name = get_constellation_name(
                constellation_base_name,
                cfg["isls_selection"],
                cfg["ground_station_selection"],
                algorithm
            )
            dynamic_state_dir = get_dynamic_state_dir(
                gen_data_dir,
                constellation_name,
                cfg["time_step_ms"],
                cfg["duration_s"]
            )
            if not dynamic_state_dir.is_dir():
                raise RuntimeError("Missing dynamic-state directory (skip-generation set): {}".format(dynamic_state_dir))
            experiment_outputs.append({
                "label": label,
                "algorithm": algorithm,
                "constellation_name": constellation_name,
                "dynamic_state_dir": str(dynamic_state_dir)
            })

    print("[phase] compute summary metrics")
    run_cmd(
        [
            "python3",
            str((repo_root / "papier3/scripts/compute_summary.py").resolve()),
            "--config",
            str(config_path)
        ],
        repo_root
    )

    print("[phase] generate plots")
    run_cmd(
        [
            "python3",
            str((repo_root / "papier3/scripts/plot_results.py").resolve()),
            "--config",
            str(config_path)
        ],
        repo_root
    )

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config_path),
        "smoke_outputs": smoke_outputs,
        "experiment_outputs": experiment_outputs
    }
    manifest_path = results_dir / "run_manifest.json"
    with open(manifest_path, "w") as f_out:
        json.dump(manifest, f_out, indent=2)
    print("[done] wrote {}".format(manifest_path))


if __name__ == "__main__":
    main()
