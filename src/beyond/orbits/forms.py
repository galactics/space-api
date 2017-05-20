#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This module declares the different meanings that the Orbit 6 components can take
and their conversions
"""

from numpy import cos, arccos, sin, arcsin, arctan2, sqrt, arccosh, sinh

import numpy as np

from ..utils.node import Node


class Form(Node):
    """Base class for form classes
    """

    _case = False

    def __init__(self, name, param_names, subcoord=None):
        super().__init__(name, subcoord)
        self.param_names = param_names

    def __str__(self):  # pragma: no cover
        return self.name


class FormTransform:
    """Class handling the conversions between the differents forms availables
    """

    TLE = Form("TLE", ["i", "Ω", "e", "ω", "M", "n"])
    KEPL_M = Form("Keplerian_M", ["a", "e", "i", "Ω", "ω", "M"], [TLE])
    KEPL = Form("Keplerian", ["a", "e", "i", "Ω", "ω", "ν"], [KEPL_M])
    SPHE = Form("Spherical", ["r", "θ", "φ", "r_dot", "θ_dot", "φ_dot"])
    CART = Form("Cartesian", ["x", "y", "z", "vx", "vy", "vz"], [KEPL, SPHE])

    _tree = CART

    def __init__(self, orbit):
        self.orbit = orbit

    def transform(self, new_form):
        """Gives the result of the transformation without inplace modifications

        Args:
            new_form (str or Form):
        Returns:
            Coord
        """

        if isinstance(new_form, Form):
            new_form = new_form.name

        coord = self.orbit.copy()
        if new_form != self.orbit.form.name:
            for a, b in self._tree.steps(self.orbit.form.name, new_form):
                a = a.name.lower()
                b = b.name.lower()
                coord = getattr(self, "_{}_to_{}".format(a, b))(coord, self.orbit.frame.center)

        return coord

    @classmethod
    def _cartesian_to_keplerian(cls, coord, center):
        """Convertion from cartesian (position and velocity) to keplerian

        The keplerian form is

            a : semi-major axis
            e : excentricity
            i : inclination
            Ω : right-ascencion of ascending node
            ω : Arguement of perigee
            ν : True anomaly
        """

        r, v = coord[:3], coord[3:]
        h = np.cross(r, v)                      # angular momentum vector
        h_norm = np.linalg.norm(h)
        r_norm = np.linalg.norm(r)
        v_norm = np.linalg.norm(v)

        K = v_norm ** 2 / 2 - center.µ / r_norm      # specific energy
        a = - center.µ / (2 * K)                     # semi-major axis
        e = sqrt(1 - h_norm ** 2 / (a * center.µ))   # eccentricity
        p = a * (1 - e ** 2)
        i = arccos(h[2] / h_norm)               # inclination
        Ω = arctan2(h[0], -h[1]) % (2 * np.pi)  # right ascencion of the ascending node

        ω_ν = arctan2(r[2] / sin(i), r[0] * cos(Ω) + r[1] * sin(Ω))
        ν = arctan2(sqrt(p / center.µ) * np.dot(v, r), p - r_norm)
        ω = (ω_ν - ν) % (2 * np.pi)             # argument of the perigee

        return np.array([a, e, i, Ω, ω, ν], dtype=float)

    @classmethod
    def _keplerian_to_cartesian(cls, coord, center):

        a, e, i, Ω, ω, ν = coord

        p = a * (1 - e ** 2)
        r = p / (1 + e * cos(ν))
        h = sqrt(center.µ * p)
        x = r * (cos(Ω) * cos(ω + ν) - sin(Ω) * sin(ω + ν) * cos(i))
        y = r * (sin(Ω) * cos(ω + ν) + cos(Ω) * sin(ω + ν) * cos(i))
        z = r * sin(i) * sin(ω + ν)
        vx = x * h * e / (r * p) * sin(ν) - h / r * (cos(Ω) * sin(ω + ν) + sin(Ω) * cos(ω + ν) * cos(i))
        vy = y * h * e / (r * p) * sin(ν) - h / r * (sin(Ω) * sin(ω + ν) - cos(Ω) * cos(ω + ν) * cos(i))
        vz = z * h * e / (r * p) * sin(ν) + h / r * sin(i) * cos(ω + ν)

        return np.array([x, y, z, vx, vy, vz], dtype=float)

    @classmethod
    def _keplerian_to_keplerian_m(cls, coord, center):
        """Conversion from Keplerian to Mean Keplerian

        The difference is the use of Mean anomaly instead of True anomaly
        """

        a, e, i, Ω, ω, ν = coord
        if e < 1:
            # Elliptic case
            E = arccos((e + cos(ν)) / (1 + e * cos(ν)))  # Eccentric anomaly
            M = E - e * sin(E)  # Mean anomaly
        else:
            # Hyperbolic case
            H = arccosh((e + cos(ν)) / (1 + e * cos(ν)))
            M = e * sinh(H) - H

        return np.array([a, e, i, Ω, ω, M], dtype=float)

    @classmethod
    def _keplerian_m_to_keplerian(cls, coord, center):
        """Conversion from Mean Keplerian to True Keplerian
        """
        a, e, i, Ω, ω, M = coord
        E = cls._m_to_e(e, M)
        ν = arccos((cos(E) - e) / (1 - e * cos(E)))

        return np.array([a, e, i, Ω, ω, ν], dtype=float)

    @classmethod
    def _m_to_e(cls, e, M):
        """Conversion from Mean Anomaly to Excentric anomaly

        Procedures for solving Kepler's Equation, A. W. Odell and  R. H. Gooding,
        Celestial Mechanics 38 (1986) 307-334
        """

        k1 = 3 * np.pi + 2
        k2 = np.pi - 1
        k3 = 6 * np.pi - 1
        A = 3 * k2 ** 2 / k1
        B = k3 ** 2 / (6 * k1)

        m1 = float(M)
        if abs(m1) < 1 / 6:
            E = m1 + e * (6 * m1) ** (1 / 3) - m1
        elif m1 < 0:
            w = np.pi + m1
            E = m1 + e * (A * w / (B - w) - np.pi - m1)
        else:
            w = np.pi - m1
            E = m1 + e * (np.pi - A * w / (B - w) - m1)

        e1 = 1 - e
        risk_disabler = (e1 + E ** 2 / 6) >= 0.1

        for i in range(2):
            fdd = e * sin(E)
            fddd = e * cos(E)

            if risk_disabler:
                f = (E - fdd) - m1
                fd = 1 - fddd
            else:
                f = cls._e_e_sin_e(e, E) - m1
                s = sin(E / 2)
                fd = e1 + 2 * e * s ** 2
            dee = f * fd / (0.5 * f * fdd - fd ** 2)

            w = fd + 0.5 * dee * (fdd + dee * fddd / 3)
            fd += dee * (fdd + 0.5 * dee * fddd)
            E -= (f - dee * (fd - w)) / fd

        E += M - m1

        return E

    @classmethod
    def _e_e_sin_e(cls, e, E):
        x = (1 - e) * sin(E)
        term = float(E)
        d = 0
        x0 = np.nan
        while x != x0:
            d += 2
            term *= - E ** 2 / (d * (d + 1))
            x0 = x
            x = x - term
        return x

    @classmethod
    def _tle_to_keplerian_m(cls, coord, center):
        """Convertion from the TLE standard format to the Mean Keplerian

        see :py:class:`Tle` for more information.
        """
        i, Ω, e, ω, M, n = coord
        a = (center.µ / n ** 2) ** (1 / 3)

        return np.array([a, e, i, Ω, ω, M], dtype=float)

    @classmethod
    def _keplerian_m_to_tle(cls, coord, center):
        """Mean Keplerian to TLE format conversion
        """
        a, e, i, Ω, ω, M = coord
        n = sqrt(center.µ / a ** 3)

        return np.array([i, Ω, e, ω, M, n], dtype=float)

    @classmethod
    def _cartesian_to_spherical(cls, coord, center):
        """Cartesian to Spherical conversion

        .. warning:: The spherical form is equatorial, not zenithal
        """
        x, y, z, vx, vy, vz = coord
        r = np.linalg.norm(coord[:3])
        phi = arcsin(z / r)
        theta = arctan2(y, x)

        # Not very sure about this
        r_dot = (x * vx + y * vy + z * vz) / r
        phi_dot = (vz * (x ** 2 + y ** 2) - z * (x * vx + y * vy)) / (r ** 2 * sqrt(x ** 2 + y ** 2))
        theta_dot = (x * vy - y * vx) / (x ** 2 + y ** 2)

        return np.array([r, theta, phi, r_dot, theta_dot, phi_dot], dtype=float)

    @classmethod
    def _spherical_to_cartesian(cls, coord, center):
        """Spherical to cartesian conversion
        """
        r, theta, phi, r_dot, theta_dot, phi_dot = coord
        x = r * cos(phi) * cos(theta)
        y = r * cos(phi) * sin(theta)
        z = r * sin(phi)

        # Not very sure about that either
        vx = r_dot * x / r - y * theta_dot - z * phi_dot * cos(theta)
        vy = r_dot * y / r + x * theta_dot - z * phi_dot * sin(theta)
        vz = r_dot * z / r + r * phi_dot * cos(phi)

        return np.array([x, y, z, vx, vy, vz], dtype=float)