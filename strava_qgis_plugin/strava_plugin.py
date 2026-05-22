"""Plugin entry point. QGIS calls initGui() on load and unload() on disable."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .strava_dialog import StravaDialog

PLUGIN_NAME = "Strava Activities"
MENU_NAME = "&Strava"


class StravaPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self) -> None:  # noqa: N802 - QGIS API
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        self.action = QAction(QIcon(icon_path), PLUGIN_NAME, self.iface.mainWindow())
        self.action.setToolTip("Import Strava activities as a vector layer")
        self.action.triggered.connect(self._open_dialog)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToWebMenu(MENU_NAME, self.action)

    def unload(self) -> None:
        if self.action is not None:
            self.iface.removePluginWebMenu(MENU_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None
        if self.dialog is not None:
            self.dialog.close()
            self.dialog = None

    def _open_dialog(self) -> None:
        if self.dialog is None:
            self.dialog = StravaDialog(self.iface, parent=self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
