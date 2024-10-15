import numpy as np
import scipy.signal  # type: ignore
from numpy.typing import NDArray


def moore(array: NDArray[np.bool_], diagonals: bool = True) -> NDArray[np.int8]:
    if diagonals:
        mask = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.int8)
    else:
        mask = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=np.int8)
    return scipy.signal.convolve(array, mask, mode="same", method="direct")


def bitmask(array: NDArray[np.int8], diagonals=False) -> NDArray[np.int16 | np.int8]:
    mask: NDArray[np.int8 | np.int16]
    if diagonals:
        mask = np.array([[32, 64, 128], [16, 0, 8], [1, 2, 4]], dtype=np.int16).T
    else:
        mask = np.array([[0, 8, 0], [4, 0, 2], [0, 1, 0]], dtype=np.int8).T
    grid = np.zeros(array.shape, dtype=mask.dtype)
    for k in np.unique(array):
        bmk = scipy.signal.convolve((array == k), mask, mode="same", method="direct")
        grid[array == k] = bmk[array == k]
    return grid
