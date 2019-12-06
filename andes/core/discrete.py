import numpy as np
from typing import Optional  # NOQA


class Discrete(object):

    def __init__(self, name=None, tex_name=None):
        self.name = name
        self.tex_name = tex_name
        self.owner = None

    def check_var(self):
        pass

    def check_eq(self):
        pass

    def set_var(self):
        pass

    def set_eq(self):
        pass

    def get_names(self):
        pass

    def get_values(self):
        pass

    @property
    def class_name(self):
        return self.__class__.__name__


class Limiter(Discrete):
    """
    Base limiter class

    This class compares values and sets limit values

    Parameters
    ----------
    u : VarBase
        Input Variable instance
    lower : ParamBase
        Parameter instance for the lower limit
    upper : ParamBase
        Parameter instance for the upper limit

    Attributes
    ----------
    zl : array-like
        Flags of elements violating the lower limit;
        A array of zeros and/or ones.
    zi : array-like
        Flags for within the limits
    zu : array-like
        Flags for violating the upper limit

    Notes
    -----
    One common pitfall is to confuse the output and input variables. The correct variable for input `u` should
    be the variable *before* the limiter. The output variable is not involved in limiter classes; they are
    handled in the equation associated with the output variable.
    """

    def __init__(self, u, lower, upper, enable=True):
        super().__init__()
        self.u = u
        self.lower = lower
        self.upper = upper
        self.enable = enable
        self.zu = 0
        self.zl = 0
        self.zi = 1

    def check_var(self):
        """
        Evaluate `self.zu` and `self.zl`

        Returns
        -------

        """
        if not self.enable:
            return
        self.zu = np.greater_equal(self.u.v, self.upper.v)
        self.zl = np.less_equal(self.u.v, self.lower.v)
        self.zi = np.logical_not(np.logical_or(self.zu, self.zl))

        self.zu = self.zu.astype(np.float64)
        self.zl = self.zl.astype(np.float64)
        self.zi = self.zi.astype(np.float64)

    def get_names(self):
        """
        Available symbols from this class

        Returns
        -------

        """
        return [self.name + '_zl', self.name + '_zi', self.name + '_zu']

    def get_values(self):
        return [self.zl, self.zi, self.zu]


class Comparer(Limiter):
    """
    A value comparer. This class is an alias of Limiter.

    .. deprecated:: soon
        The `Comparer` class will be deprecated as it is identical to Limiter because Limiter no longer sets the
        variable value. Now, A Limiter is essentially a comparer.
    """
    pass


class SortedLimiter(Limiter):
    """
    A comparer with the top value selection

    """

    def __init__(self, u, lower, upper, enable=True,
                 n_select: Optional[int] = None,
                 **kwargs):

        super().__init__(u, lower, upper, enable=enable, **kwargs)
        self.n_select = int(n_select) if n_select else 0

    def check_var(self):
        if not self.enable:
            return
        super().check_var()

        if self.n_select is not None and self.n_select > 0:
            asc = np.argsort(self.u.v - self.lower.v)   # ascending order
            desc = np.argsort(self.upper.v - self.u.v)

            lowest_n = asc[:self.n_select]
            highest_n = desc[:self.n_select]

            reset_in = np.ones(self.u.v.shape)
            reset_in[lowest_n] = 0
            reset_in[highest_n] = 0
            reset_out = 1 - reset_in

            self.zi = np.logical_or(reset_in, self.zi).astype(np.float64)
            self.zl = np.logical_and(reset_out, self.zl).astype(np.float64)
            self.zu = np.logical_and(reset_out, self.zu).astype(np.float64)


class HardLimiter(Limiter):
    """
    Hard limiter on an algebraic variable. This class is an alias of `Limiter`.
    """
    pass


class WindupLimiter(Limiter):
    def __init__(self, u, lower, upper, enable=True):
        super().__init__(u, lower, upper, enable=enable)

    def set_eq(self):
        self.u.e = self.u.e * self.zi


class AntiWindupLimiter(WindupLimiter):
    """
    Anti-windup limiter.

    The anti-windup limiter prevents the wind-up effect of a differential variable. The derivative of the
    differential variable is reset if it continues to increase in the same direction after exceeding the limits.
    During the derivative return, the limiter will be inactive ::

      if x > xmax and x dot > 0: x = xmax and x dot = 0
      if x < xmin and x dot < 0: x = xmin and x dot = 0

    This class takes one more optional parameter for specifying the equation.

    Parameters
    ----------
    state : State, ExtState
        A State (or ExtState) whose equation value will be checked and, when condition satisfies, will be reset
        by the anti-windup-limiter.
    """

    def __init__(self, u, lower, upper, enable=True, state=None):
        super().__init__(u, lower, upper, enable=enable)
        self.state = state if state else u

    def check_var(self):
        """
        This function is empty. Defers `check_var` to `check_eq`.
        """
        pass

    def check_eq(self):
        super().check_var()
        self.zu = np.logical_and(self.zu, np.greater_equal(self.state.e, 0)).astype(np.float64)
        self.zl = np.logical_and(self.zl, np.less_equal(self.state.e, 0)).astype(np.float64)
        self.zi = np.logical_not(
            np.logical_or(self.zu.astype(np.bool),
                          self.zl.astype(np.bool))).astype(np.float64)

    def set_eq(self):
        self.state.e = self.state.e * self.zi


class Selector(Discrete):
    """
    Selection of variables using the provided reduce function.

    The reduce function should take the given number of arguments. An example function is `np.maximum.reduce`
    which can be used to select the maximum.

    Names are in `s0`, `s1`, ... and `sn`

    Examples
    --------
    Example 1: select the largest value between `v0` and `v1` and put it into vmax.

    After the definitions of `v0` and `v1`, define the algebraic variable `vmax` for the largest value,
    and a selector `vs` ::

        self.vmax = Algeb(v_init='maximum(v0, v1) - vmax',
                          tex_name='v_{max}',
                          e_str='vs_s0 * v0 + vs_s1 * v1 - vmax')

        self.vs = Selector(self.v0, self.v1, fun=np.maximum.reduce)

    The initial value of `vmax` is calculated by ``maximum(v0, v1)``, which is the element-wise maximum in SymPy
    and will be generated into ``np.maximum(v0, v1)``. The equation of `vmax` is to select the values based on
    `vs_s0` and `vs_s1`.

    Notes
    -----
    A common pitfall is the 0-based indexing in the Selector flags. Note that exported flags start from 0. Namely,
    `s0` corresponds to the first variable provided for the Selector constructor.

    See Also
    --------
    numpy.ufunc.reduce : NumPy reduce function
    """
    def __init__(self, *args, fun, tex_name=None):
        super().__init__(tex_name=tex_name)
        self.input_vars = args
        self.fun = fun
        self.n = len(args)
        self._s = [0] * self.n
        self._inputs = None
        self._outputs = None

    def get_names(self):
        return [f'{self.name}_s' + str(i) for i in range(len(self.input_vars))]

    def get_values(self):
        return self._s

    def check_var(self):
        """
        Set the i-th variable's flags to 1 if the return of the reduce function equals the i-th input
        """
        self._inputs = [self.input_vars[i].v for i in range(self.n)]
        self._outputs = self.fun(self._inputs)
        for i in range(self.n):
            self._s[i] = np.equal(self._inputs[i], self._outputs).astype(int)


class DeadBand(Limiter):
    """
    Deadband with the direction of return.

    Parameters
    ----------
    u
        The pre-deadband input variable
    center : NumParam
        Neutral value of the output
    lower : NumParam
        Lower bound
    upper : NumParam
        Upper bpund
    enable : bool
        Enabled if True; Disabled and works as a pass-through if False.

    Notes
    -----

    Input changes within a deadband will incur no output changes. This component computes and exports five flags.

    Three flags computed from the current input:
     - zl: True if the input is below the lower threshold
     - zi: True if the input is within the deadband
     - zu: True if is above the lower threshold

    Two flags indicating the direction of return:
     - zur: True if the input is/has been within the deadband and was returned from the upper threshold
     - zlr: True if the input is/has been within the deadband and was returned from the lower threshold

    Initial condition:

    All five flags are initialized to zero. All flags are updated during `check_var` when enabled. If the
    deadband component is not enabled, all of them will remain zero.

    Examples
    --------

    Exported deadband flags need to be used in the algebraic equation corresponding to the post-deadband variable.
    Assume the pre-deadband input variable is `var_in` and the post-deadband variable is `var_out`. First, define a
    deadband instance `db` in the model using ::

        self.db = DeadBand(u=self.var_in, center=self.dbc, lower=self.dbl, upper=self.dbu)

    To implement a no-memory deadband whose output returns to center when the input is within the band,
    the equation for `var` can be written as ::

        var_out.e_str = 'var_in * (1 - db_zi) + (dbc * db_zi) - var_out'

    To implement a deadband whose output is pegged at the nearest deadband bounds, the equation for `var` can be
    provided as ::

        var_out.e_str = 'var_in * (1 - db_zi) + dbl * db_zlr + dbu * db_zur - var_out'

    """
    def __init__(self, u, center, lower, upper, enable=True):
        """

        """
        super().__init__(u, lower, upper, enable=enable)
        self.center = center
        # default state if enable is False
        self.zi = 0.
        self.zl = 0.
        self.zu = 0.
        self.zur = 0.
        self.zlr = 0.

    def check_var(self):
        """
        Updates five flags: zi, zu, zl; zur, and zlr based on the following rules

        zu:
          1 if u > upper; 0 otherwise.

        zl:
          1 if u < lower; 0 otherwise.
        zi:
          not(zu or zl);

        zur:
         - set to 1 when (previous zu + present zi == 2)
         - hold when (previous zi == zi)
         - clear otherwise

        zlr:
         - set to 1 when (previous zl + present zi == 2)
         - hold when (previous zi == zi)
         - clear otherwise
        """
        if not self.enable:
            return
        zu = np.greater(self.u.v, self.upper.v)
        zl = np.less(self.u.v, self.lower.v)
        zi = np.logical_not(np.logical_or(zu, zl))

        # square return dead band
        self.zur = np.equal(self.zu + zi, 2) + self.zur * np.equal(zi, self.zi)
        self.zlr = np.equal(self.zl + zi, 2) + self.zlr * np.equal(zi, self.zi)

        self.zu = zu.astype(np.float64)
        self.zl = zl.astype(np.float64)
        self.zi = zi.astype(np.float64)

    def get_names(self):
        """
        Export names

        Returns
        -------
        list:
            Five exported names in the order of `zl`, `zi`, `zu`, `zur`, and `zlr`
        """
        return [self.name + '_zl', self.name + '_zi', self.name + '_zu',
                self.name + '_zur', self.name + '_zlr']

    def get_values(self):
        """
        Export values

        Returns
        -------
        list:
            Five exported variables in the same order of names
        """
        return [self.zl, self.zi, self.zu, self.zur, self.zlr]


class NonLinearGain(Discrete):
    """
    Non-linear gain function
    """
    pass