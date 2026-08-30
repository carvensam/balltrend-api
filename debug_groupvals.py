import pandas as pd
import numpy as np
from itertools import combinations

# Simulate the issue
df = pd.DataFrame({
    'league': ['FRA1', 'FRA1', 'FRA2', 'FRA2'],
    'ah_result': ['upper_win', 'lower_win', 'upper_win', 'lower_win'],
})

grouped = df.groupby(['league'])
for group_vals, group in grouped:
    print(f"r=1, type={type(group_vals)}, val={group_vals!r}")

grouped2 = df.groupby(['league', 'ah_result'])
for group_vals, group in grouped2:
    print(f"r=2, type={type(group_vals)}, val={group_vals!r}")
