from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from student_success.modeling import train
from student_success.schema import canonicalize, load_config


rng = np.random.default_rng(42)
n = 500
attendance = rng.beta(7, 2, n)
due = rng.integers(6, 15, n)
submitted = np.minimum(due, rng.binomial(due, np.clip(attendance, .1, .98)))
assessment = np.clip(35 + 55 * attendance + rng.normal(0, 10, n), 0, 100)
change = rng.normal(0, 9, n)
days = np.clip(rng.gamma(2, 4, n) + (1 - attendance) * 14, 0, 45)
contacts = rng.poisson(1 + (1 - attendance) * 2)
credits = np.clip(attendance + rng.normal(0, .12, n), 0, 1)
logit = -3.0 + 3.4 * (1 - attendance) + 2.2 * (1 - submitted / due) + 1.5 * (1 - assessment / 100) + .06 * days - .03 * change
probability = 1 / (1 + np.exp(-logit))
outcome = rng.binomial(1, probability)
demo = pd.DataFrame({
    "Student ID": [f"D{value:04d}" for value in range(1, n + 1)],
    "Attendance %": attendance * 100,
    "Assignments Due": due,
    "Assignments Submitted": submitted,
    "Average Mark": assessment,
    "Score Change": change,
    "Days Since Login": days,
    "Support Contacts": contacts,
    "Credits Completed %": credits * 100,
    "Historical Outcome": outcome,
})
root = Path(__file__).resolve().parents[1]
data_path = root / "data" / "demo_students.csv"
data_path.parent.mkdir(parents=True, exist_ok=True)
demo.to_csv(data_path, index=False)
config = load_config(root / "config" / "institutions" / "example.json")
validated = canonicalize(demo, config, training=True)
print(train(validated.frame, root / "models"))

