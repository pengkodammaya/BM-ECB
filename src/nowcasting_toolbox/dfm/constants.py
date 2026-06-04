"""Shared constants for the Dynamic Factor Model."""

import numpy as np

# Mariano-Murasawa quarterly constraint matrix
# Maps quarterly GDP to monthly factors: QoQ = 2*f1 - f2, etc.
R_MAT = np.array([
    [2, -1,  0,  0,  0],
    [3,  0, -1,  0,  0],
    [2,  0,  0, -1,  0],
    [1,  0,  0,  0, -1],
], dtype=float)
