"""Create natural or balanced upload-ready samples from prepared UCI dataset 697."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rows", type=int, default=500)
    parser.add_argument("--balanced", action="store_true", help="Use equal dropout and non-dropout classes for comparison only.")
    args = parser.parse_args()

    source = pd.read_csv(args.input)
    if args.rows < 2 or args.rows > len(source):
        raise ValueError(f"Choose between 2 and {len(source)} rows.")
    if args.balanced:
        per_outcome = args.rows // 2
        groups = []
        for outcome, group in source.groupby("confirmed_dropout"):
            if len(group) < per_outcome:
                raise ValueError(f"Outcome {outcome} has only {len(group)} rows; cannot sample {per_outcome}.")
            groups.append(group.sample(per_outcome, random_state=2026 + int(outcome)))
        sample = pd.concat(groups, ignore_index=True).sample(frac=1, random_state=2026).reset_index(drop=True)
    else:
        sample = source.sample(args.rows, random_state=2026).reset_index(drop=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(args.output, index=False)
    print({"rows": len(sample), "dropout_rate": float(sample["confirmed_dropout"].mean()), "balanced": args.balanced, "output": str(args.output)})


if __name__ == "__main__":
    main()
