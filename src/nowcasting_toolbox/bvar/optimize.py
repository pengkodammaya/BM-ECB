"""Chris Sims' csminwel optimizer — Python port.

Original MATLAB code: BVAR_csminwel.m, BVAR_csminit.m, BVAR_bfgsi.m
Used in Cimadomo et al. (2022) for BVAR hyperparameter optimization.

csminwel is a quasi-Newton optimizer using BFGS updates with:
- Numerical gradient (central differences)
- Line search with backtracking
- Periodic Hessian reset
- Robust convergence criteria
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]


def csminwel(
    func: Callable[[FloatArray], float],
    x0: FloatArray,
    H0: Optional[FloatArray] = None,
    grad_func: Optional[Callable[[FloatArray], FloatArray]] = None,
    crit: float = 1e-6,
    nit: int = 200,
    verbose: bool = False,
    h_pert: float = 1e-6,
) -> tuple[FloatArray, float, FloatArray, FloatArray, int]:
    """Minimize a scalar function using the csminwel algorithm.

    Parameters
    ----------
    func : callable
        Function f(x) -> float to minimize.
    x0 : (K,) array
        Initial parameter vector.
    H0 : (K, K) array, optional
        Initial inverse Hessian. Defaults to identity.
    grad_func : callable, optional
        Analytical gradient g(x) -> (K,) array.
        If None, numerical gradient is used.
    crit : float
        Convergence criterion on gradient norm.
    nit : int
        Maximum number of iterations.
    verbose : bool
        Print progress.

    Returns
    -------
    xh : (K,) array — optimal parameters
    fh : float — function value at optimum
    gh : (K,) array — gradient at optimum
    H : (K, K) array — final inverse Hessian
    itct : int — number of iterations used
    """
    K = len(x0)
    if H0 is None:
        H0 = np.eye(K)

    if grad_func is None:
        grad_func = _make_numgrad(func, h_pert)

    # ---------- Initialization ----------
    x = x0.copy().astype(float)
    f = func(x)
    g = grad_func(x)

    if verbose:
        logger.info("csminwel: init f=%.6f, |g|=%.6f", f, np.linalg.norm(g))

    H = H0.copy()
    itct = 0
    retcode = 0  # 0=converged, 1=no cov, 2=max iter

    # Line search parameters
    max_alpha_iters = 10
    alpha_scale = 1.0
    alpha = 1.0

    for itct in range(nit):
        # ---------- Check gradient ----------
        gnorm = np.linalg.norm(g, np.inf)
        if gnorm < crit:
            retcode = 0
            if verbose:
                logger.info("csminwel: converged (|g|_inf=%.6f < %.0e) at iter %d", gnorm, crit, itct)
            break

        # ---------- Search direction ----------
        d = -H @ g

        # Check that direction is descent direction
        if np.dot(g, d) >= 0:
            # Hessian not positive definite — reset
            H = np.eye(K)
            d = -g / (gnorm + 1e-12)

        # ---------- Line search ----------
        alpha, f_new, x_new, g_new, ls_success = _linesearch(
            func, grad_func, x, f, g, d, alpha, max_alpha_iters
        )

        if not ls_success:
            retcode = 1
            break

        # ---------- BFGS update ----------
        s = x_new - x
        y = g_new - g
        sy = np.dot(s, y)

        if sy > 0:
            Hy = H @ y
            H = H + ((sy + y @ Hy) / (sy * sy)) * np.outer(s, s)
            H = H - (np.outer(Hy, s) + np.outer(s, Hy)) / sy

        # ---------- Update ----------
        x = x_new
        f = f_new
        g = g_new

        # Reset alpha for next iteration
        alpha = min(alpha * 2, 1.0)

        # Periodic Hessian reset
        if itct > 0 and itct % 20 == 0:
            H = np.eye(K)

        if verbose and itct % 20 == 0:
            logger.info("csminwel: iter=%d f=%.6f |g|=%.6f", itct, f, np.linalg.norm(g))

    else:
        retcode = 2

    return x, f, g, H, itct + 1


# ---------------------------------------------------------------------------
# Numerical gradient
# ---------------------------------------------------------------------------


def _make_numgrad(
    func: Callable[[FloatArray], float],
    h: float = 1e-6,
) -> Callable[[FloatArray], FloatArray]:
    """Return a central-difference numerical gradient function."""

    def numgrad(x: FloatArray) -> FloatArray:
        K = len(x)
        g = np.zeros(K)
        f0 = func(x)
        for i in range(K):
            x_plus = x.copy()
            x_plus[i] += h
            x_minus = x.copy()
            x_minus[i] -= h
            g[i] = (func(x_plus) - func(x_minus)) / (2 * h)
        return g

    return numgrad


# ---------------------------------------------------------------------------
# Line search with backtracking
# ---------------------------------------------------------------------------


def _linesearch(
    func: Callable[[FloatArray], float],
    grad_func: Callable[[FloatArray], FloatArray],
    x: FloatArray,
    f: float,
    g: FloatArray,
    d: FloatArray,
    alpha: float,
    max_iters: int = 10,
) -> tuple[float, float, FloatArray, FloatArray, bool]:
    """Backtracking line search satisfying Armijo condition.

    Returns (alpha, f_new, x_new, g_new, success).
    """
    c1 = 1e-4  # Armijo constant
    rho = 0.5  # Backtracking factor

    dg0 = np.dot(g, d)

    for _ in range(max_iters):
        x_new = x + alpha * d
        f_new = func(x_new)

        # Armijo condition
        if f_new <= f + c1 * alpha * dg0:
            g_new = grad_func(x_new)
            return alpha, f_new, x_new, g_new, True

        alpha *= rho

    # Last attempt with tiny alpha
    x_new = x + alpha * d
    f_new = func(x_new)
    g_new = grad_func(x_new)
    return alpha, f_new, x_new, g_new, False
