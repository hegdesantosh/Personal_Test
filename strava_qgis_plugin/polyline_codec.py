"""Decoder for Google's Encoded Polyline Algorithm Format.

Strava returns activity tracks as a base64-like encoded polyline string in
`map.summary_polyline` and `map.polyline`. This module decodes those strings
into a list of (lon, lat) tuples suitable for QgsLineString construction.

Reference:
https://developers.google.com/maps/documentation/utilities/polylinealgorithm
"""

from typing import List, Tuple


def decode(encoded: str, precision: int = 5) -> List[Tuple[float, float]]:
    if not encoded:
        return []

    factor = 10 ** precision
    coordinates: List[Tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0
    length = len(encoded)

    while index < length:
        result = 1
        shift = 0
        while True:
            b = ord(encoded[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1F:
                break
        lat += (~(result >> 1)) if (result & 1) else (result >> 1)

        result = 1
        shift = 0
        while True:
            b = ord(encoded[index]) - 63 - 1
            index += 1
            result += b << shift
            shift += 5
            if b < 0x1F:
                break
        lng += (~(result >> 1)) if (result & 1) else (result >> 1)

        coordinates.append((lng / factor, lat / factor))

    return coordinates
