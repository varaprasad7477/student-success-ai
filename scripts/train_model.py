from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from student_success.modeling import train, train_temporal
from student_success.schema import canonicalize, load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="models")
    parser.add_argument(
        "--time-column",
        help="Source CSV timestamp column; enables chronological train/validation/test evaluation.",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    source = pd.read_csv(args.data)
    validated = canonicalize(source, config, training=True)
    if args.time_column:
        if args.time_column not in source:
            parser.error(f"--time-column '{args.time_column}' is not present in the input CSV.")
        report = train_temporal(
            validated.frame,
            source[args.time_column],
            Path(args.output),
            audit_fields=config.get("audit_fields", []),
            feature_names=config.get("model_fields"),
        )
    else:
        report = train(
            validated.frame, Path(args.output), audit_fields=config.get("audit_fields", []),
            feature_names=config.get("model_fields"),
        )
    print(report)


if __name__ == "__main__":
    main()
