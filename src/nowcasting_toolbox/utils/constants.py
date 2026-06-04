"""Named constants for the Nowcasting Toolbox.

Replaces magic numbers scattered throughout the codebase with
self-documenting named values.
"""

# Numerical stability
EPSILON = 1e-10
"""Small positive number to avoid division by zero or log(0)."""

VARIANCE_FLOOR = 1e-10
"""Minimum variance value; below this, variance is clamped to 1.0."""

MATRIX_JITTER = 1e-8
"""Jitter added to diagonal for numerical stability in matrix inversions."""

MATRIX_JITTER_LARGE = 1e-6
"""Larger jitter for ill-conditioned matrices."""

# Convergence thresholds
EM_CONVERGENCE_THRESHOLD = 1e-4
"""Default EM algorithm convergence threshold."""

BVAR_CONVERGENCE_THRESHOLD = 1e-5
"""Default BVAR optimizer convergence threshold."""

OPTIMIZER_CONVERGENCE_THRESHOLD = 1e-6
"""Default csminwel optimizer convergence threshold."""

# Kalman filter bounds
KALMAN_COVARIANCE_CLIP = 1e6
"""Maximum allowed value in Kalman covariance matrices (prevents overflow)."""

# Default model parameters
DEFAULT_DFM_FACTORS = 2
"""Default number of factors for DFM (r)."""

DEFAULT_DFM_LAGS = 4
"""Default number of lags for DFM factor VAR (p)."""

DEFAULT_BVAR_LAGS = 2
"""Default number of lags for BVAR."""

DEFAULT_GIBBS_DRAWS = 20
"""Default number of Gibbs sampler draws."""

DEFAULT_GIBBS_BURN_IN = 5
"""Default Gibbs sampler burn-in period."""

DEFAULT_SEED = 42
"""Default random seed for reproducibility."""

# AR(1) defaults
DEFAULT_AR1_PERSISTENCE = 0.5
"""Default AR(1) persistence coefficient for initialization."""

# COVID period
COVID_START_YEAR = 2020
COVID_START_MONTH = 2
COVID_END_YEAR = 2020
COVID_END_MONTH = 9
"""Period to NaN-block for COVID correction (Feb-Sep 2020)."""
