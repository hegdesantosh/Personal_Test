def classFactory(iface):
    from .strava_plugin import StravaPlugin
    return StravaPlugin(iface)
