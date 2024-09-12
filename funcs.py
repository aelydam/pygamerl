import numpy as np
import scipy.signal  # type: ignore


def moore(array: np.ndarray, diagonals: bool = True) -> np.ndarray:
    if diagonals:
        mask = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.int8)
    else:
        mask = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=np.int8)
    return scipy.signal.convolve(array, mask, mode="same", method="direct")
