# -*- coding: utf-8 -*-

"""Date module
"""

import datetime as _datetime

from ..env.poleandtimes import get_timescales
from .node import Node

__all__ = ['Date']


class _Scale(Node):

    HEAD = None
    """Define the top Node of the tree. This one will be used as reference to search for the path
    linking two Nodes together
    """

    def __repr__(self):  # pragma: no cover
        return "<Scale '%s'>" % self.name

    def __str__(self):
        return self.name

    @classmethod
    def get(cls, name):
        return cls.HEAD[name]

    def _scale_ut1_minus_utc(self, mjd):
        ut1_utc, tai_utc = get_timescales(mjd)
        return ut1_utc

    def _scale_tai_minus_utc(self, mjd):
        ut1_utc, tai_utc = get_timescales(mjd)
        return tai_utc

    def _scale_tt_minus_tai(self, mjd):
        return 32.184

    def _scale_tai_minus_gps(self, mjd):
        return 19.

    def offset(self, mjd, new_scale):
        """Compute the offset necessary in order to convert from one time-scale to another

        Args:
            mjd (float):
            new_scale (str): Name of the desired scale
        Return:
            float: offset to apply in seconds
        """

        delta = 0
        for one, two in self.HEAD.steps(self.name, new_scale):
            one = one.name.lower()
            two = two.name.lower()
            # find the operation
            oper = "_scale_{}_minus_{}".format(two, one)
            # find the reverse operation
            roper = "_scale_{}_minus_{}".format(one, two)
            if hasattr(self, oper):
                delta += getattr(self, oper)(mjd)
            elif hasattr(self, roper):
                delta -= getattr(self, roper)(mjd)
            else:  # pragma: no cover
                raise ValueError("Unknown convertion {} => {}".format(one, two))

        return delta


UT1 = _Scale('UT1')
GPS = _Scale('GPS')
UTC = _Scale('UTC', [UT1])
TAI = _Scale('TAI', [UTC, GPS])
TT = _Scale('TT', [TAI])
_Scale.HEAD = TT


class Date:
    """Date object

    All computations and in-memory saving are made in
    `MJD <https://en.wikipedia.org/wiki/Julian_day>`__.

    In the current implementation, the Date object does not handle the
    leap second.

    Examples:

        .. code-block:: python

            Date(2016, 11, 17, 19, 16, 40)
            Date(2016, 11, 17, 19, 16, 40, scale="TAI")
            Date(57709.804455)  # MJD
            Date(57709, 69540.752649)
            Date(datetime(2016, 11, 17, 19, 16, 40))  # builtin datetime object
            Date.now()
    """

    __slots__ = ["_d", "_s", "_offset", "scale", "_cache"]

    MJD_T0 = _datetime.datetime(1858, 11, 17)
    """Origin of MJD"""
    JD_MJD = 2400000.5
    """Offset between JD and MJD"""
    REF_SCALE = 'TAI'
    """Scale used internlly"""

    def __init__(self, *args, **kwargs):

        scale = kwargs.pop('scale', 'UTC')

        if type(scale) is str:
            scale = _Scale.get(scale.upper())

        if len(args) == 1:
            arg = args[0]
            if isinstance(arg, _datetime.datetime):
                # Python datetime.datetime object
                d, s = self._convert_dt(arg)
            elif isinstance(arg, self.__class__):
                # Date object
                d = arg.d
                s = arg.s
                scale = arg.scale
            elif isinstance(arg, (float, int)):
                # Modified Julian Day
                if isinstance(arg, int):
                    d = arg
                    s = 0.
                else:
                    d = int(arg)
                    s = (arg - d) * 86400
            else:
                raise TypeError("Unknown argument")
        elif len(args) == 2 and (isinstance(args[0], int) and isinstance(args[1], (int, float))):
            # Julian day and seconds in the day
            d, s = args
        elif len(args) in range(3, 8) and list(map(type, args)) == [int] * len(args):
            # Same constructor as datetime.datetime
            # (year, month, day hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
            dt = _datetime.datetime(*args, **kwargs)
            d, s = self._convert_dt(dt)
        else:
            raise ValueError("Unknown arguments")

        # Retrieve the offset for the current date
        offset = scale.offset(d + s / 86400., self.REF_SCALE)

        d += int((s + offset) // 86400)
        s = (s + offset) % 86400.

        # As Date acts like an immutable object, we can't set its attributes normally
        # like when we do ``self._d = _d``. Furthermore, those attribute represent the date with
        # respect to REF_SCALE
        super().__setattr__('_d', d)
        super().__setattr__('_s', s)
        super().__setattr__('_offset', offset)
        super().__setattr__('scale', scale)
        super().__setattr__('_cache', {})

    def __setattr__(self, *args):  # pragma: no cover
        raise TypeError("Can not modify attributes of immutable object")

    def __delattr__(self, *args):  # pragma: no cover
        raise TypeError("Can not modify attributes of immutable object")

    def __add__(self, other):
        if isinstance(other, _datetime.timedelta):
            days, sec = divmod(other.total_seconds() + self.s, 86400)
        else:
            raise TypeError("Unknown operation with {} type".format(type(other)))

        return self.__class__(self.d + int(days), sec, scale=self.scale)

    def __sub__(self, other):
        if isinstance(other, _datetime.timedelta):
            other = _datetime.timedelta(seconds=-other.total_seconds())
        elif isinstance(other, _datetime.datetime):
            return self.datetime - other
        elif isinstance(other, self.__class__):
            return self._to_ref.datetime - other._to_ref.datetime
        else:
            raise TypeError("Unknown operation with {} type".format(type(other)))

        return self.__add__(other)

    def __gt__(self, other):
        return self._mjd > other._mjd

    def __ge__(self, other):
        return self._mjd >= other._mjd

    def __lt__(self, other):
        return self._mjd < other._mjd

    def __le__(self, other):
        return self._mjd <= other._mjd

    def __eq__(self, other):
        return self._mjd == other._mjd

    def __repr__(self):  # pragma: no cover
        return "<{} '{}'>".format(self.__class__.__name__, self)

    def __str__(self):  # pragma: no cover
        if 'str' not in self._cache.keys():
            self._cache['str'] = "{} {}".format(self.datetime.isoformat(), self.scale)
        return self._cache['str']

    def __format__(self, fmt):  # pragma: no cover
        if fmt:
            return self.datetime.__format__(fmt)
        else:
            return str(self)

    @classmethod
    def _convert_dt(cls, dt):
        if dt.tzinfo is None:
            delta = dt - cls.MJD_T0
        else:
            tz = dt.utcoffset()
            delta = dt.replace(tzinfo=None) - cls.MJD_T0 - tz

        return delta.days, delta.seconds + delta.microseconds * 1e-6

    def _convert_to_scale(self):
        """Convert the inner value (defined with respect to REF_SCALE) into the given scale
        of the object
        """
        d = self._d
        s = (self._s - self._offset) % 86400.
        d -= int((s + self._offset) // 86400)
        return d, s

    @property
    def d(self):
        return self._convert_to_scale()[0]

    @property
    def s(self):
        return self._convert_to_scale()[1]

    @property
    def datetime(self):
        """Transform the Date object into a ``datetime.datetime`` object

        The resulting object is a timezone-naive instance with the same scale
        as the originating Date object.
        """

        if 'dt' not in self._cache.keys():
            self._cache['dt'] = self.MJD_T0 + _datetime.timedelta(days=self.d, seconds=self.s)
        return self._cache['dt']

    @classmethod
    def strptime(cls, data, format, scale='UTC'):  # pragma: no cover
        """Convert a string representation of a date to a Date object
        """
        return Date(_datetime.datetime.strptime(data, format), scale=scale)

    @classmethod
    def now(cls, scale="UTC"):
        """
        Args:
            scale (str)
        Return:
            Date: Current time in the choosen scale
        """
        return cls(_datetime.datetime.utcnow()).change_scale(scale)

    def change_scale(self, new_scale):
        offset = self.scale.offset(self.mjd, new_scale)
        result = self.datetime + _datetime.timedelta(seconds=offset)

        return Date(result, scale=new_scale)

    @property
    def julian_century(self):
        """Compute the julian_century of the Date object relatively to its
        scale

        Return:
            float
        """
        return (self.jd - 2451545.0) / 36525.

    @property
    def jd(self):
        """Compute the Julian Date, which is the number of days from the
        January 1, 4712 B.C., 12:00.

        Return:
            float
        """
        return self.mjd + self.JD_MJD

    @property
    def _mjd(self):
        """
        Return:
            float: Date in terms of MJD in the REF_SCALE timescale
        """
        return self._d + self._s / 86400.

    @property
    def mjd(self):
        """Date in terms of MJD

        Return:
            float
        """
        return self.d + self.s / 86400.

    @property
    def _to_ref(self):
        """Convert to the reference time-scale

        Return:
            Date:
        """
        return self.change_scale(self.REF_SCALE)

    @classmethod
    def range(cls, start, stop, step, inclusive=False):
        """Generator of a date range

        Args:
            start (Date):
            stop (Date or datetime.timedelta)!
            step (timedelta):
        Keyword Args:
            inclusive (bool): If ``False``, the stopping date is not included.
                This is the same behaviour as the builtin :py:func:`range`.
        Yield:
            Date:
        """

        def sign(x):
            """Inner function for determining the sign of a float
            """
            return (-1, 1)[x >= 0]

        if not step:
            raise ValueError("Null step")

        # Convert stop from timedelta to Date object
        if isinstance(stop, _datetime.timedelta):
            stop = start + stop

        if sign((stop - start).total_seconds()) != sign(step.total_seconds()):
            raise ValueError("start/stop order not coherent with step")

        date = start

        if step.total_seconds() > 0:
            oper = "__le__" if inclusive else "__lt__"
        else:
            oper = "__ge__" if inclusive else "__gt__"

        while getattr(date, oper)(stop):
            yield date
            date += step
