"""Small, dependency-free GeoJSON predicates used after bbox filtering."""
from rest_framework.exceptions import ValidationError


def validate_geometry(value):
    if isinstance(value, str):
        import json
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("geometry must be valid GeoJSON JSON.") from exc
    if not isinstance(value, dict) or value.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValidationError("geometry must be a Polygon or MultiPolygon.")
    coordinates = value.get("coordinates")
    if not coordinates:
        raise ValidationError("geometry coordinates are required.")
    try:
        points = list(_points(value))
    except (TypeError, ValueError):
        raise ValidationError("geometry coordinates are invalid.")
    if len(points) < 3 or any(len(point) < 2 for point in points):
        raise ValidationError("geometry coordinates are invalid.")
    return value


def _rings(geometry):
    return geometry["coordinates"] if geometry["type"] == "Polygon" else [ring for polygon in geometry["coordinates"] for ring in polygon]


def _points(geometry):
    if geometry.get("type") == "Point":
        yield geometry["coordinates"]
        return
    for ring in _rings(geometry):
        for point in ring:
            yield point


def _bbox(geometry):
    points = list(_points(geometry))
    return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]


def _point_in_ring(point, ring):
    inside = False
    x, y = point
    for i, a in enumerate(ring):
        b = ring[(i + 1) % len(ring)]
        if ((a[1] > y) != (b[1] > y)) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


def _contains(geometry, point):
    if geometry.get("type") == "Point":
        return geometry["coordinates"][:2] == point[:2]
    return any(_point_in_ring(point, ring) for ring in _rings(geometry))


def _segments(ring):
    return zip(ring, ring[1:] + ring[:1])


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersects(a, b, c, d):
    return (_orientation(a, b, c) * _orientation(a, b, d) <= 0 and _orientation(c, d, a) * _orientation(c, d, b) <= 0)


def geometries_relation(candidate, query, relation):
    cb, qb = _bbox(candidate), _bbox(query)
    bbox_intersects = cb[0] <= qb[2] and cb[2] >= qb[0] and cb[1] <= qb[3] and cb[3] >= qb[1]
    if not bbox_intersects:
        return False
    candidate_points, query_points = list(_points(candidate)), list(_points(query))
    if candidate.get("type") == "Point":
        inside = _contains(query, candidate_points[0])
        return inside if relation in {"within", "intersects"} else False
    candidate_in_query = all(_contains(query, point) for point in candidate_points)
    query_in_candidate = all(_contains(candidate, point) for point in query_points)
    edge_intersects = any(_intersects(a, b, c, d) for cr in _rings(candidate) for a, b in _segments(cr) for qr in _rings(query) for c, d in _segments(qr))
    if relation == "within":
        return candidate_in_query
    if relation == "contains":
        return query_in_candidate
    return edge_intersects or candidate_in_query or query_in_candidate
