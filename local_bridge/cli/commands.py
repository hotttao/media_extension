"""CLI commands: serve, inspect. Migrated from server.py main()."""
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from local_bridge.domain.models import build_jobs, load_case_file
from local_bridge.infrastructure.persistence import JobStore
from local_bridge.main import create_app


def run_server(host: str, port: int, task_arguments: list[str], output_root: Path, log_level: str = "info") -> None:
    import logging
    case_paths = [Path(item).resolve() for item in task_arguments]
    jobs = build_jobs(case_paths, output_root.resolve())
    store = JobStore(jobs=jobs, output_root=output_root.resolve())
    output_root.mkdir(parents=True, exist_ok=True)

    # Setup logging
    log_path = Path("runs/bridge.log")
    log_path.parent.mkdir(exist_ok=True)
    level = log_level.upper()
    logger = logging.getLogger("local_bridge")
    logger.setLevel(level)
    logger.handlers.clear()
    fmt = logging.Formatter("[%(name)s] %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    logging.getLogger().setLevel(level)

    app = create_app(store)
    uvicorn.run(app, host=host, port=port)


def inspect_case(task_argument: str) -> None:
    import json
    case_path = Path(task_argument).resolve()
    prompt, assets = load_case_file(case_path)
    payload = {
        "caseFile": str(case_path),
        "prompt": prompt,
        "assets": [
            {
                "label": asset["label"],
                "name": asset["name"],
                "path": str(asset["path"]),
                "mimeType": asset["mimeType"],
            }
            for asset in assets
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="local_bridge serve/inspect CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start the local task server.")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--task", action="append", default=[], help="Path to a Markdown task file.")
    serve_parser.add_argument("--output-root", default="runs", help="Directory for generated outputs.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a Markdown task file.")
    inspect_parser.add_argument("task", help="Path to a Markdown task file.")

    serve_parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    args = parser.parse_args()

    if args.command == "serve":
        run_server(
            host=args.host,
            port=args.port,
            task_arguments=args.task,
            output_root=Path(args.output_root),
            log_level=args.log_level,
        )
    elif args.command == "inspect":
        inspect_case(args.task)
    else:
        raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
