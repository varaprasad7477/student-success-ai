from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from student_success.modeling import train
from student_success.schema import canonicalize, load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default="models")
    args = parser.parse_args()
    config = load_config(args.config)
    source = pd.read_csv(args.data)
    validated = canonicalize(source, config, training=True)
    report = train(
        validated.frame, Path(args.output), audit_fields=config.get("audit_fields", []),
        feature_names=config.get("model_fields"),
    )
    print(report)


if __name__ == "__main__":
    main()

