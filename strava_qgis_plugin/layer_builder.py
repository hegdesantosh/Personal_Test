"""Convert Strava activity JSON into a QGIS memory vector layer."""

from typing import Dict, Iterable, List, Tuple

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsLineString,
    QgsLineSymbol,
    QgsPoint,
    QgsProject,
    QgsRendererCategory,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

from .polyline_codec import decode

FIELDS: List[Tuple[str, QVariant.Type]] = [
    ("id", QVariant.LongLong),
    ("name", QVariant.String),
    ("type", QVariant.String),
    ("sport_type", QVariant.String),
    ("start_date", QVariant.String),
    ("distance_m", QVariant.Double),
    ("moving_time_s", QVariant.Int),
    ("elapsed_time_s", QVariant.Int),
    ("total_elevation_gain_m", QVariant.Double),
    ("average_speed_mps", QVariant.Double),
    ("max_speed_mps", QVariant.Double),
    ("average_heartrate", QVariant.Double),
    ("max_heartrate", QVariant.Double),
    ("kudos_count", QVariant.Int),
    ("strava_url", QVariant.String),
]

# Distinct, readable colors per activity type. Anything not listed falls back to grey.
TYPE_COLORS = {
    "Ride": "#fc4c02",            # Strava orange
    "VirtualRide": "#ff8c42",
    "EBikeRide": "#ffb04c",
    "Run": "#2b7cff",
    "TrailRun": "#005ce6",
    "VirtualRun": "#7fbfff",
    "Walk": "#33cc33",
    "Hike": "#1f8a1f",
    "Swim": "#00b3a4",
    "Workout": "#a04cff",
}


def _polyline_for(activity: Dict) -> str:
    track = (activity.get("map") or {})
    return track.get("polyline") or track.get("summary_polyline") or ""


def build_layer(activities: Iterable[Dict], layer_name: str = "Strava Activities") -> QgsVectorLayer:
    layer = QgsVectorLayer(f"LineString?crs=EPSG:4326", layer_name, "memory")
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(name, t) for name, t in FIELDS])
    layer.updateFields()

    features: List[QgsFeature] = []
    skipped = 0
    for activity in activities:
        encoded = _polyline_for(activity)
        if not encoded:
            skipped += 1
            continue
        coords = decode(encoded)
        if len(coords) < 2:
            skipped += 1
            continue

        line = QgsLineString([QgsPoint(lon, lat) for lon, lat in coords])
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry(line))
        feature.setAttributes([
            activity.get("id"),
            activity.get("name"),
            activity.get("type"),
            activity.get("sport_type"),
            activity.get("start_date"),
            activity.get("distance"),
            activity.get("moving_time"),
            activity.get("elapsed_time"),
            activity.get("total_elevation_gain"),
            activity.get("average_speed"),
            activity.get("max_speed"),
            activity.get("average_heartrate"),
            activity.get("max_heartrate"),
            activity.get("kudos_count"),
            f"https://www.strava.com/activities/{activity.get('id')}",
        ])
        features.append(feature)

    provider.addFeatures(features)
    layer.updateExtents()
    _apply_style(layer)
    layer.setCustomProperty("strava/skipped_no_track", skipped)
    return layer


def _apply_style(layer: QgsVectorLayer) -> None:
    categories = []
    for activity_type, color in TYPE_COLORS.items():
        symbol = QgsLineSymbol.createSimple({"color": color, "width": "0.8"})
        categories.append(QgsRendererCategory(activity_type, symbol, activity_type))
    fallback = QgsLineSymbol.createSimple({"color": "#888888", "width": "0.6"})
    categories.append(QgsRendererCategory("", fallback, "Other"))
    layer.setRenderer(QgsCategorizedSymbolRenderer("type", categories))


def add_to_project(layer: QgsVectorLayer) -> None:
    QgsProject.instance().addMapLayer(layer)
