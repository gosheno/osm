#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import re
import statistics
import subprocess
import threading
import time
from typing import Any
from urllib import error, request


PUBLIC_NOMINATIM_HOST = "nominatim.openstreetmap.org"
DEFAULT_CONTAINERS = (
    "osm_route_backend",
    "osm_route_db",
    "osm_nominatim",
    "osm_route_osrm",
)
NO_PROXY_OPENER = request.build_opener(request.ProxyHandler({}))


@dataclass(frozen=True)
class RequestResult:
    timestamp: str
    address: str
    latency_ms: float
    http_status: int | None
    geocoding_status: str | None
    source: str | None
    provider: str | None
    from_cache: bool | None
    ok: bool
    error: str | None


@dataclass(frozen=True)
class SystemSample:
    timestamp: str
    cpu_percent: float | None
    memory_percent: float | None
    memory_used_bytes: int | None
    memory_available_bytes: int | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_addresses(path: Path) -> list[str]:
    addresses = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not addresses:
        raise SystemExit(f"No addresses found in {path}")
    return addresses


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout_s: float,
) -> tuple[int | None, dict[str, Any] | None, str | None]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with NO_PROXY_OPENER.open(req, timeout=timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body else None
            return response.status, parsed, None
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = None
        return exc.code, parsed, body or str(exc)
    except Exception as exc:
        return None, None, str(exc)


def get_json(
    url: str,
    timeout_s: float,
) -> tuple[int | None, dict[str, Any] | None, str | None]:
    try:
        with NO_PROXY_OPENER.open(url, timeout=timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body else None
            return response.status, parsed, None
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = None
        return exc.code, parsed, body or str(exc)
    except Exception as exc:
        return None, None, str(exc)


def resolve_nominatim_health(base_url: str, timeout_s: float) -> dict[str, Any]:
    status, payload, err = get_json(
        f"{base_url.rstrip('/')}/api/health/nominatim",
        timeout_s=timeout_s,
    )
    if isinstance(payload, dict):
        if "detail" in payload and isinstance(payload["detail"], dict):
            result = payload["detail"]
        else:
            result = payload
        result["http_status"] = status
        return result
    return {"http_status": status, "error": err}


def guard_public_force_refresh(args: argparse.Namespace) -> dict[str, Any]:
    health = resolve_nominatim_health(args.base_url, args.request_timeout)
    provider_url = str(health.get("url") or "")

    if not args.force_refresh:
        return health

    if args.allow_public_geocoder:
        return health

    if not provider_url:
        raise SystemExit(
            "Refusing force-refresh load test: cannot verify /api/health/nominatim. "
            "Run with --allow-public-geocoder only if this is intentional."
        )

    if PUBLIC_NOMINATIM_HOST in provider_url:
        raise SystemExit(
            "Refusing force-refresh load test against public Nominatim. "
            "Point NOMINATIM_BASE_URL to local http://nominatim:8080 or pass "
            "--allow-public-geocoder for a tiny manual check."
        )

    if health.get("status") != "ok":
        raise SystemExit(
            "Refusing force-refresh load test: local Nominatim health is not ok. "
            f"Health payload: {json.dumps(health, ensure_ascii=False)}"
        )

    return health


def request_worker(
    *,
    args: argparse.Namespace,
    addresses: list[str],
    endpoint_url: str,
    work_queue: queue.Queue[int],
    results: list[RequestResult],
    results_lock: threading.Lock,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        try:
            request_no = work_queue.get_nowait()
        except queue.Empty:
            return

        address = addresses[request_no % len(addresses)]
        payload: dict[str, Any] = {
            "address": address,
            "force_refresh": args.force_refresh,
        }
        if not args.use_backend_default_city:
            payload["default_city"] = args.default_city

        started_at = time.perf_counter()
        status, body, err = post_json(endpoint_url, payload, args.request_timeout)
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

        geocoding_status = body.get("geocoding_status") if isinstance(body, dict) else None
        source = body.get("source") if isinstance(body, dict) else None
        provider = body.get("geocoding_provider") if isinstance(body, dict) else None
        from_cache = body.get("from_cache") if isinstance(body, dict) else None
        app_error = body.get("error") if isinstance(body, dict) else None
        ok = status == 200 and err is None and geocoding_status != "error"

        with results_lock:
            results.append(
                RequestResult(
                    timestamp=utc_now(),
                    address=address,
                    latency_ms=latency_ms,
                    http_status=status,
                    geocoding_status=geocoding_status,
                    source=source,
                    provider=provider,
                    from_cache=from_cache,
                    ok=ok,
                    error=err or app_error,
                )
            )

        work_queue.task_done()


def collect_system_sample() -> SystemSample:
    try:
        import psutil  # type: ignore
    except Exception:
        return SystemSample(
            timestamp=utc_now(),
            cpu_percent=None,
            memory_percent=None,
            memory_used_bytes=None,
            memory_available_bytes=None,
        )

    memory = psutil.virtual_memory()
    return SystemSample(
        timestamp=utc_now(),
        cpu_percent=float(psutil.cpu_percent(interval=0.1)),
        memory_percent=float(memory.percent),
        memory_used_bytes=int(memory.used),
        memory_available_bytes=int(memory.available),
    )


def parse_percent(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip().rstrip("%"))
    except ValueError:
        return None


def parse_size_bytes(value: str | None) -> int | None:
    if not value:
        return None

    match = re.match(r"^\s*([0-9.]+)\s*([A-Za-z]+)\s*$", value)
    if not match:
        return None

    amount = float(match.group(1))
    unit = match.group(2)
    units = {
        "B": 1,
        "kB": 1000,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
    }
    multiplier = units.get(unit)
    return int(amount * multiplier) if multiplier else None


def parse_usage_pair(value: str | None) -> tuple[int | None, int | None]:
    if not value or "/" not in value:
        return None, None
    left, right = value.split("/", 1)
    return parse_size_bytes(left.strip()), parse_size_bytes(right.strip())


def docker_stats(container_names: set[str]) -> list[dict[str, Any]]:
    try:
        completed = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except Exception as exc:
        return [{"timestamp": utc_now(), "error": str(exc)}]

    if completed.returncode != 0:
        return [{"timestamp": utc_now(), "error": completed.stderr.strip()}]

    rows: list[dict[str, Any]] = []
    sampled_at = utc_now()
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue

        name = raw.get("Name")
        if container_names and name not in container_names:
            continue

        mem_used, mem_limit = parse_usage_pair(raw.get("MemUsage"))
        net_in, net_out = parse_usage_pair(raw.get("NetIO"))
        block_in, block_out = parse_usage_pair(raw.get("BlockIO"))
        rows.append(
            {
                "timestamp": sampled_at,
                "name": name,
                "id": raw.get("ID"),
                "cpu_percent": parse_percent(raw.get("CPUPerc")),
                "memory_percent": parse_percent(raw.get("MemPerc")),
                "memory_used_bytes": mem_used,
                "memory_limit_bytes": mem_limit,
                "net_in_bytes": net_in,
                "net_out_bytes": net_out,
                "block_in_bytes": block_in,
                "block_out_bytes": block_out,
                "pids": int(raw["PIDs"]) if str(raw.get("PIDs", "")).isdigit() else None,
                "raw": raw,
            }
        )
    return rows


def sample_worker(
    *,
    args: argparse.Namespace,
    docker_samples: list[dict[str, Any]],
    system_samples: list[SystemSample],
    samples_lock: threading.Lock,
    stop_event: threading.Event,
) -> None:
    container_names = set(args.docker_containers)
    while not stop_event.is_set():
        system_sample = collect_system_sample()
        docker_sample = docker_stats(container_names)
        with samples_lock:
            system_samples.append(system_sample)
            docker_samples.extend(docker_sample)
        stop_event.wait(args.sample_interval)


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return round(ordered[index], 2)


def summarize(
    *,
    results: list[RequestResult],
    system_samples: list[SystemSample],
    docker_samples: list[dict[str, Any]],
    elapsed_s: float,
) -> dict[str, Any]:
    latencies = [item.latency_ms for item in results]
    ok_count = sum(1 for item in results if item.ok)
    http_statuses = Counter(str(item.http_status) for item in results)
    geocoding_statuses = Counter(str(item.geocoding_status) for item in results)
    providers = Counter(str(item.provider) for item in results)
    sources = Counter(str(item.source) for item in results)
    cache_counts = Counter(str(item.from_cache) for item in results)

    cpu_values = [
        item.cpu_percent for item in system_samples if item.cpu_percent is not None
    ]
    memory_values = [
        item.memory_percent for item in system_samples if item.memory_percent is not None
    ]

    docker_by_name: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "samples": 0,
            "max_cpu_percent": None,
            "avg_cpu_percent": None,
            "max_memory_percent": None,
            "max_memory_used_bytes": None,
        }
    )
    docker_cpu_lists: dict[str, list[float]] = defaultdict(list)
    for sample in docker_samples:
        name = sample.get("name")
        if not name:
            continue
        row = docker_by_name[name]
        row["samples"] += 1
        cpu = sample.get("cpu_percent")
        mem_pct = sample.get("memory_percent")
        mem_bytes = sample.get("memory_used_bytes")
        if cpu is not None:
            docker_cpu_lists[name].append(float(cpu))
            row["max_cpu_percent"] = max(row["max_cpu_percent"] or 0.0, float(cpu))
        if mem_pct is not None:
            row["max_memory_percent"] = max(row["max_memory_percent"] or 0.0, float(mem_pct))
        if mem_bytes is not None:
            row["max_memory_used_bytes"] = max(row["max_memory_used_bytes"] or 0, int(mem_bytes))

    for name, values in docker_cpu_lists.items():
        docker_by_name[name]["avg_cpu_percent"] = round(statistics.fmean(values), 2)

    return {
        "requests_total": len(results),
        "requests_ok": ok_count,
        "requests_failed": len(results) - ok_count,
        "elapsed_s": round(elapsed_s, 2),
        "requests_per_second": round(len(results) / elapsed_s, 2) if elapsed_s > 0 else None,
        "latency_ms": {
            "min": round(min(latencies), 2) if latencies else None,
            "avg": round(statistics.fmean(latencies), 2) if latencies else None,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "max": round(max(latencies), 2) if latencies else None,
        },
        "http_statuses": dict(http_statuses),
        "geocoding_statuses": dict(geocoding_statuses),
        "providers": dict(providers),
        "sources": dict(sources),
        "from_cache": dict(cache_counts),
        "system": {
            "samples": len(system_samples),
            "avg_cpu_percent": round(statistics.fmean(cpu_values), 2) if cpu_values else None,
            "max_cpu_percent": round(max(cpu_values), 2) if cpu_values else None,
            "avg_memory_percent": round(statistics.fmean(memory_values), 2) if memory_values else None,
            "max_memory_percent": round(max(memory_values), 2) if memory_values else None,
        },
        "docker": dict(docker_by_name),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load test backend geocoding and capture Docker/system metrics.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--addresses-file",
        type=Path,
        default=Path("scripts/data/nominatim_test_addresses.txt"),
    )
    parser.add_argument(
        "--address",
        action="append",
        dest="addresses",
        default=None,
        help="Address to test. Can be passed multiple times; overrides --addresses-file.",
    )
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--request-timeout", type=float, default=20.0)
    parser.add_argument("--sample-interval", type=float, default=2.0)
    parser.add_argument("--report-dir", type=Path, default=Path("reports/load"))
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--allow-public-geocoder", action="store_true")
    parser.add_argument("--use-backend-default-city", action="store_true")
    parser.add_argument("--default-city", default=None)
    parser.add_argument(
        "--docker-containers",
        nargs="*",
        default=list(DEFAULT_CONTAINERS),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    addresses = args.addresses or read_addresses(args.addresses_file)
    provider_health = guard_public_force_refresh(args)

    endpoint_url = f"{args.base_url.rstrip('/')}/api/addresses/geocode"
    args.report_dir.mkdir(parents=True, exist_ok=True)

    started_at = time.perf_counter()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    work_queue: queue.Queue[int] = queue.Queue()
    for request_no in range(args.requests):
        work_queue.put(request_no)

    results: list[RequestResult] = []
    docker_samples: list[dict[str, Any]] = []
    system_samples: list[SystemSample] = []
    results_lock = threading.Lock()
    samples_lock = threading.Lock()
    stop_event = threading.Event()

    sampler = threading.Thread(
        target=sample_worker,
        kwargs={
            "args": args,
            "docker_samples": docker_samples,
            "system_samples": system_samples,
            "samples_lock": samples_lock,
            "stop_event": stop_event,
        },
        daemon=True,
    )
    sampler.start()

    workers = [
        threading.Thread(
            target=request_worker,
            kwargs={
                "args": args,
                "addresses": addresses,
                "endpoint_url": endpoint_url,
                "work_queue": work_queue,
                "results": results,
                "results_lock": results_lock,
                "stop_event": stop_event,
            },
            daemon=True,
        )
        for _worker_id in range(args.concurrency)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    stop_event.set()
    sampler.join(timeout=args.sample_interval + 1)

    with samples_lock:
        if not system_samples:
            system_samples.append(collect_system_sample())
        if not docker_samples:
            docker_samples.extend(docker_stats(set(args.docker_containers)))

    elapsed_s = time.perf_counter() - started_at
    summary = summarize(
        results=results,
        system_samples=system_samples,
        docker_samples=docker_samples,
        elapsed_s=elapsed_s,
    )

    report = {
        "run_id": run_id,
        "started_at": utc_now(),
        "config": {
            "base_url": args.base_url,
            "addresses_file": str(args.addresses_file),
            "requests": args.requests,
            "concurrency": args.concurrency,
            "force_refresh": args.force_refresh,
            "default_city": args.default_city,
            "use_backend_default_city": args.use_backend_default_city,
            "docker_containers": args.docker_containers,
        },
        "provider_health": provider_health,
        "summary": summary,
        "system_samples": [asdict(item) for item in system_samples],
        "docker_samples": docker_samples,
    }

    summary_path = args.report_dir / f"geocoding-load-{run_id}.json"
    requests_path = args.report_dir / f"geocoding-load-requests-{run_id}.csv"
    docker_path = args.report_dir / f"geocoding-load-docker-{run_id}.csv"

    summary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(
        requests_path,
        [asdict(item) for item in results],
        [
            "timestamp",
            "address",
            "latency_ms",
            "http_status",
            "geocoding_status",
            "source",
            "provider",
            "from_cache",
            "ok",
            "error",
        ],
    )
    write_csv(
        docker_path,
        docker_samples,
        [
            "timestamp",
            "name",
            "id",
            "cpu_percent",
            "memory_percent",
            "memory_used_bytes",
            "memory_limit_bytes",
            "net_in_bytes",
            "net_out_bytes",
            "block_in_bytes",
            "block_out_bytes",
            "pids",
            "error",
        ],
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Summary: {summary_path}")
    print(f"Requests CSV: {requests_path}")
    print(f"Docker CSV: {docker_path}")


if __name__ == "__main__":
    main()
