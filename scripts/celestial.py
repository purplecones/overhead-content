"""The arithmetic the app's body admission runs, ported so validate.py can
reach the same verdict.

Shipped app builds reject a whole package when any body record fails
admission, so a record that passes here but fails there removes every
contributed body for every user. Each function names the Swift it mirrors in
the Overhead app repository (ios/Overhead/Celestial/). Only finiteness and
range outcomes matter here, never the positions themselves, but the formulas
are copied term for term so the overflow and range edges agree.

Every function returns None when the app would admit, or a short reason.
"""

from __future__ import annotations

import math

J2000_JD = 2451545.0                   # CatalogueLimits.j2000JD
JD_AT_UNIX_EPOCH = 2_440_587.5         # CatalogueLimits.julianDayAtUnixEpoch
SECONDS_PER_DAY = 86_400.0             # CatalogueLimits.secondsPerDay
J2000_UNIX = 946_728_000.0             # CelestialFrame.j2000
AU = 149_597_870_700.0                 # CelestialFrame.astronomicalUnit
OBLIQUITY_J2000 = 23.439291 * math.pi / 180  # CelestialFrame.obliquityJ2000
SUN_GM = 1.327_124_400_18e20           # CelestialTree.makeSunAnchor
EARTH_GM = 3.986_004_418e14            # GlobeMath.gravitationalParameter (Earth anchor)
EARTH_RADIUS = 6_378_137.0             # GlobeMath.earthRadius
# CelestialOrbitAdapter.legacyEarth / .legacyMoon semi-major axis and eccentricity.
LEGACY_EARTH_ORBIT = (1.00000018 * AU, 0.01673163)
LEGACY_MOON_ORBIT = (60.2666 * EARTH_RADIUS, 0.054900)
# CelestialTree.framingReach * framingMargin with BodyCamera.fieldOfView = 45 degrees:
# the root's distance limit is the outermost reach times this and must stay finite.
FRAMING_FACTOR = 1 / (math.tan(45.0 * math.pi / 180 / 2) * (390.0 / 844.0)) * 1.1


def _finite(*values: float) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def _cos(x: float) -> float:
    # Swift's cos(inf) is NaN; Python raises. Keep Swift's behaviour.
    return math.cos(x) if math.isfinite(x) else math.nan


def _sin(x: float) -> float:
    return math.sin(x) if math.isfinite(x) else math.nan


def unix_seconds(jd: float) -> float:
    """CelestialCatalogue.validityRange's date(_:)."""
    return (jd - JD_AT_UNIX_EPOCH) * SECONDS_PER_DAY


def validity_problem(start_jd: float, end_jd: float) -> str | None:
    """CelestialCatalogue.validityRange: finite, ordered, and convertible."""
    if not _finite(start_jd, end_jd) or not start_jd < end_jd:
        return "validity endpoints must be finite with validityStartJD before validityEndJD"
    if not _finite(unix_seconds(start_jd), unix_seconds(end_jd)):
        return "validity endpoints are too far from the present to convert to dates"
    return None


def _days_since_j2000(seconds: float) -> float:
    """CelestialFrame.daysSinceJ2000."""
    return (seconds - J2000_UNIX) / 86_400


def _rotate_x(v, angle):
    c, s = _cos(angle), _sin(angle)
    return (v[0], v[1] * c - v[2] * s, v[1] * s + v[2] * c)


def _rotate_z(v, angle):
    c, s = _cos(angle), _sin(angle)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2])


def _root_from_equatorial(v):
    return (v[0], v[2], -v[1])


def _equatorial_from_root(v):
    return (v[0], -v[2], v[1])


def _root_from_ecliptic_j2000(v):
    return _root_from_equatorial(_rotate_x(v, OBLIQUITY_J2000))


def _ecliptic_j2000_from_root(v):
    return _rotate_x(_equatorial_from_root(v), -OBLIQUITY_J2000)


def _precess(seconds: float, v):
    """CelestialFrame.precession(at:) applied to one vector: the matrix is built
    from the images of the unit axes, so applying the same map to v is the
    same product up to rounding."""
    t = _days_since_j2000(seconds) / 36_525
    p = (5_028.796195 * t + 1.1054348 * t * t) / 3_600 * math.pi / 180
    epsilon = (23.439291 - 0.0130042 * t) * math.pi / 180

    def image(axis):
        return _root_from_equatorial(_rotate_x(_rotate_z(_ecliptic_j2000_from_root(axis), p), epsilon))

    columns = [image((1.0, 0.0, 0.0)), image((0.0, 1.0, 0.0)), image((0.0, 0.0, 1.0))]
    return tuple(columns[0][i] * v[0] + columns[1][i] * v[1] + columns[2][i] * v[2] for i in range(3))


def _wrapped_signed_angle(radians: float) -> float:
    """KeplerSolver.wrappedSignedAngle (truncatingRemainder is fmod)."""
    two_pi = 2 * math.pi
    wrapped = math.fmod(radians, two_pi) if math.isfinite(radians) else math.nan
    if wrapped > math.pi:
        wrapped -= two_pi
    if wrapped < -math.pi:
        wrapped += two_pi
    return wrapped


def _solve(mean_anomaly: float, e: float) -> float | None:
    """KeplerSolver.solve: None where Swift throws."""
    if not _finite(mean_anomaly, e) or not 0 <= e < 1:
        return None
    mean = _wrapped_signed_angle(mean_anomaly)
    if not math.isfinite(mean):
        return None
    if e == 0:
        return mean
    low, high = mean - e, mean + e
    eccentric = min(high, max(low, mean + e * math.sin(mean)))
    for _ in range(64):
        residual = eccentric - e * math.sin(eccentric) - mean
        if abs(residual) <= 1e-12:
            return eccentric
        if residual > 0:
            high = eccentric
        else:
            low = eccentric
        derivative = 1 - e * math.cos(eccentric)
        newton = eccentric - residual / derivative if derivative != 0 else math.nan
        eccentric = newton if (low < newton < high and math.isfinite(newton)) else 0.5 * (low + high)
    residual = eccentric - e * math.sin(eccentric) - mean
    return eccentric if abs(residual) <= 1e-12 else None


ELEMENT_FIELDS = ("semiMajorAxisAU", "eccentricity", "inclinationDeg", "meanLongitudeDeg",
                  "longitudeOfPerihelionDeg", "longitudeOfAscendingNodeDeg", "rateSemiMajorAxis",
                  "rateEccentricity", "rateInclination", "rateMeanLongitude", "ratePerihelion", "rateNode")


def kepler_elements_problem(elements: dict) -> str | None:
    """GenericKeplerOrbit.init: every field finite, a > 0, 0 <= e < 1."""
    values = [elements.get(f) for f in ELEMENT_FIELDS]
    if not _finite(*values):
        return "every orbit element must be a finite number"
    if not elements["semiMajorAxisAU"] > 0:
        return "orbit.elements.semiMajorAxisAU must be greater than 0"
    if not 0 <= elements["eccentricity"] < 1:
        return "orbit.elements.eccentricity must be at least 0 and below 1 (the app draws ellipses only)"
    return None


def kepler_position_problem(elements: dict, jd: float) -> str | None:
    """KeplerSolver.heliocentricPosition(elements:date:), as
    CelestialCatalogue.validateOrbit calls it at each validity endpoint:
    the elements advanced by their rates must still be an ellipse, and the
    position must be finite."""
    seconds = unix_seconds(jd)
    centuries = _days_since_j2000(seconds) / 36_525
    if not math.isfinite(centuries):
        return "the orbit cannot be evaluated at a validity endpoint"
    a = elements["semiMajorAxisAU"] + elements["rateSemiMajorAxis"] * centuries
    e = elements["eccentricity"] + elements["rateEccentricity"] * centuries
    inclination = elements["inclinationDeg"] + elements["rateInclination"] * centuries
    mean_longitude = elements["meanLongitudeDeg"] + elements["rateMeanLongitude"] * centuries
    perihelion = elements["longitudeOfPerihelionDeg"] + elements["ratePerihelion"] * centuries
    node = elements["longitudeOfAscendingNodeDeg"] + elements["rateNode"] * centuries
    if not (_finite(a, e, inclination, mean_longitude, perihelion, node) and a > 0 and 0 <= e < 1):
        return ("at a validity endpoint the elements advanced by their rates are no longer an ellipse "
                "(semi-major axis must stay above 0 and eccentricity in 0 to below 1); narrow the validity window")
    mean_anomaly = (mean_longitude - perihelion) * math.pi / 180
    eccentric = _solve(mean_anomaly, e)
    if eccentric is None:
        return "Kepler's equation does not converge at a validity endpoint"
    argument = (perihelion - node) * math.pi / 180
    node_r = node * math.pi / 180
    incl = inclination * math.pi / 180
    semi_major = a * AU
    x = semi_major * (math.cos(eccentric) - e)
    y = semi_major * math.sqrt(max(0.0, 1 - e * e)) * math.sin(eccentric)
    cp, sp = _cos(argument), _sin(argument)
    cn, sn = _cos(node_r), _sin(node_r)
    ci, si = _cos(incl), _sin(incl)
    ecliptic = ((cp * cn - sp * sn * ci) * x + (-sp * cn - cp * sn * ci) * y,
                (cp * sn + sp * cn * ci) * x + (-sp * sn + cp * cn * ci) * y,
                sp * si * x + cp * si * y)
    position = _root_from_ecliptic_j2000(ecliptic)
    if not _finite(*position) or not _finite(*_precess(seconds, position)):
        return "the orbit position overflows at a validity endpoint"
    return None


def iau_coefficients_problem(coefficients: dict) -> str | None:
    """IAURotation.init: every coefficient finite, poleDeclination in -90...90."""
    names = ("poleRightAscension", "poleDeclination", "primeMeridian", "poleRateRA", "poleRateDec", "rotationRate")
    if not _finite(*(coefficients.get(n) for n in names)):
        return "every rotation coefficient must be a finite number"
    if not -90 <= coefficients["poleDeclination"] <= 90:
        return "rotation.coefficients.poleDeclination must be within -90 to 90"
    return None


def iau_endpoint_problem(coefficients: dict, jd: float) -> str | None:
    """CelestialCatalogue.validateRotation: IAURotation.orientation(at:) and
    spinAngle(at:) must be finite at each validity endpoint."""
    seconds = unix_seconds(jd)
    days = _days_since_j2000(seconds)
    centuries = days / 36_525
    ra = coefficients["poleRightAscension"] + coefficients["poleRateRA"] * centuries
    dec = coefficients["poleDeclination"] + coefficients["poleRateDec"] * centuries
    meridian = coefficients["primeMeridian"] + coefficients["rotationRate"] * days
    ra_r, dec_r, pm_r = ra * math.pi / 180, dec * math.pi / 180, meridian * math.pi / 180
    north = (_cos(dec_r) * _cos(ra_r), _cos(dec_r) * _sin(ra_r), _sin(dec_r))
    probe = _precess(seconds, north)
    if not (_finite(ra_r, dec_r, pm_r, *north, *probe)):
        return "the rotation overflows at a validity endpoint; narrow the validity window or check the rates"
    return None


def tree_step(parent_gm: float, parent_reach: float, a_m: float, e: float, gm: float) -> tuple[str | None, float]:
    """CelestialTree.init for one body: its Hill radius, period and reach
    must be finite and positive. Returns (problem, reach)."""
    periapsis = a_m * (1 - e)
    hill = periapsis * (gm / (3 * parent_gm)) ** (1 / 3)
    cube = a_m * a_m * a_m
    period = 2 * math.pi * math.sqrt(cube / parent_gm) if math.isfinite(cube) else math.inf
    reach = parent_reach + a_m * (1 + e)
    if not (_finite(hill, period, reach) and hill > 0 and period > 0 and reach > 0
            and math.isfinite(reach * FRAMING_FACTOR)):
        return "the orbit is too large for the app's scene (Hill radius, period or reach overflows)", reach
    return None, reach
