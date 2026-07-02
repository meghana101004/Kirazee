# delivery/utils.py
import math
from datetime import datetime
from typing import Optional


def haversine_distance_meters(lat1: Optional[float], lon1: Optional[float],
                              lat2: Optional[float], lon2: Optional[float]) -> Optional[float]:
    """Compute the great-circle distance between two points (meters).
    Returns None if any coordinate is missing or invalid.
    """
    try:
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return None
        R = 6371000.0  # meters
        phi1 = math.radians(float(lat1))
        phi2 = math.radians(float(lat2))
        dphi = math.radians(float(lat2) - float(lat1))
        dlambda = math.radians(float(lon2) - float(lon1))
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    except Exception:
        return None


def should_broadcast(prev_lat: Optional[float], prev_lng: Optional[float],
                     new_lat: Optional[float], new_lng: Optional[float],
                     prev_ts: Optional[datetime], new_ts: Optional[datetime],
                     min_move_meters: float = 15.0,
                     min_interval_seconds: float = 3.0) -> bool:
    """Decide whether to broadcast a new location update.

    - Broadcast if no previous location.
    - Broadcast if moved >= min_move_meters.
    - Otherwise broadcast if time since last update >= min_interval_seconds.
    """
    if new_lat is None or new_lng is None:
        return False

    if prev_lat is None or prev_lng is None:
        return True

    dist = haversine_distance_meters(prev_lat, prev_lng, new_lat, new_lng)
    if dist is None:
        return True

    if dist >= float(min_move_meters):
        return True

    if prev_ts is not None and new_ts is not None:
        try:
            elapsed = (new_ts - prev_ts).total_seconds()
            return elapsed >= float(min_interval_seconds)
        except Exception:
            return True

    return False
