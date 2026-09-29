"""Configurable polygons used by camera analytics."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Zone:
    name: str
    coordinates: Tuple[Tuple[float, float], ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("zone name cannot be empty")
        if len(self.coordinates) < 3:
            raise ValueError("zone polygon must contain at least three points")
        points = []
        for point in self.coordinates:
            if len(point) != 2 or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(value)
                for value in point
            ):
                raise ValueError("zone points must contain finite numeric x and y coordinates")
            points.append((float(point[0]), float(point[1])))
        area_twice = sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
        if abs(area_twice) <= 1e-9:
            raise ValueError("zone polygon must enclose a non-zero area")
        object.__setattr__(self, "coordinates", tuple(points))


class ZoneSet:
    def __init__(self) -> None:
        self.zones: Dict[str, Zone] = {}

    def add_zone(self, zone: Zone) -> None:
        self.zones[zone.name] = zone

    def list_zones(self) -> List[str]:
        return list(self.zones)

    def contains(self, name: str, point: Tuple[float, float]) -> bool:
        return self.contains_zone(self.zones[name], point)

    @classmethod
    def contains_zone(cls, zone: Zone, point: Tuple[float, float]) -> bool:
        x, y = point
        inside = False
        previous_x, previous_y = zone.coordinates[-1]
        for current_x, current_y in zone.coordinates:
            if cls._on_segment(
                x, y, previous_x, previous_y, current_x, current_y
            ):
                return True
            if (current_y > y) != (previous_y > y):
                intersection_x = (
                    (previous_x - current_x) * (y - current_y)
                    / (previous_y - current_y)
                    + current_x
                )
                if x < intersection_x:
                    inside = not inside
            previous_x, previous_y = current_x, current_y
        return inside

    @staticmethod
    def _on_segment(
        x: float,
        y: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> bool:
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) > 1e-9:
            return False
        return (
            min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9
            and min(y1, y2) - 1e-9 <= y <= max(y1, y2) + 1e-9
        )
