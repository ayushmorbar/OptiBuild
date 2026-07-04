"""MCDM Ranking operations using the TOPSIS method with weighted-sum fallback."""

import numpy as np
from pymcdm.methods import TOPSIS


def topsis_rank(
    matrix: list[list[float]], weights: list[float], directions: list[str]
) -> tuple[int, list[float]]:
    """Rank candidates using the TOPSIS method or a weighted-sum fallback.

    - matrix: list of list of floats, shape (alternatives, criteria)
    - weights: list of floats, length criteria
    - directions: list of strings ("maximize" or "minimize"), length criteria
    """
    if len(matrix) == 0:
        raise ValueError("Cannot rank an empty candidate matrix.")
    if len(matrix) == 1:
        return 0, [1.0]

    arr_matrix = np.array(matrix, dtype=float)
    arr_weights = np.array(weights, dtype=float)

    # Normalize weights so they sum to 1.0
    w_sum = arr_weights.sum()
    if w_sum > 0:
        arr_weights = arr_weights / w_sum
    else:
        arr_weights = np.ones_like(arr_weights) / len(arr_weights)

    types = np.array([1 if d == "maximize" else -1 for d in directions], dtype=int)

    try:
        topsis = TOPSIS()
        scores = topsis(arr_matrix, arr_weights, types)
        if np.isnan(scores).any():
            raise ValueError("TOPSIS scores contain NaN values.")
        best_idx = int(scores.argmax())
        return best_idx, scores.tolist()
    except Exception:
        # Fallback to weighted sum over min-max-normalized columns
        # if TOPSIS fails or yields NaN due to constant criteria.
        _num_alts, num_crit = arr_matrix.shape
        norm_matrix = np.zeros_like(arr_matrix)

        for j in range(num_crit):
            col = arr_matrix[:, j]
            c_min = col.min()
            c_max = col.max()
            if c_max == c_min:
                norm_col = np.full_like(col, 0.5)
            else:
                norm_col = (col - c_min) / (c_max - c_min)

            if types[j] == -1:  # minimize
                norm_col = 1.0 - norm_col

            norm_matrix[:, j] = norm_col

        scores = (norm_matrix * arr_weights).sum(axis=1)
        best_idx = int(scores.argmax())
        return best_idx, scores.tolist()
