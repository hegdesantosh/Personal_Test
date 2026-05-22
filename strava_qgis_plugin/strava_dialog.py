"""Main plugin dialog: credentials, OAuth connect, activity import."""

import time
import webbrowser
from typing import Optional

from qgis.PyQt.QtCore import QDate, QTimer, Qt
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from . import settings_store
from .layer_builder import add_to_project, build_layer
from .oauth_callback import OAuthCallbackServer
from .strava_client import StravaClient, StravaError


class StravaDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Strava — Import Activities")
        self.setMinimumWidth(520)

        self._callback_server: Optional[OAuthCallbackServer] = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_callback)
        self._poll_deadline = 0.0

        self._build_ui()
        self._load_settings()
        self._refresh_auth_label()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        creds_box = QGroupBox("Strava API credentials")
        creds_form = QFormLayout(creds_box)
        self.client_id_edit = QLineEdit()
        self.client_secret_edit = QLineEdit()
        self.client_secret_edit.setEchoMode(QLineEdit.Password)
        creds_form.addRow("Client ID:", self.client_id_edit)
        creds_form.addRow("Client secret:", self.client_secret_edit)
        hint = QLabel(
            'Create an API application at <a href="https://www.strava.com/settings/api">'
            "strava.com/settings/api</a>. Set the Authorization Callback Domain to "
            "<code>localhost</code>."
        )
        hint.setOpenExternalLinks(True)
        hint.setWordWrap(True)
        creds_form.addRow(hint)
        outer.addWidget(creds_box)

        auth_box = QGroupBox("Authorization")
        auth_layout = QVBoxLayout(auth_box)
        self.auth_status_label = QLabel()
        self.auth_status_label.setWordWrap(True)
        auth_layout.addWidget(self.auth_status_label)
        button_row = QHBoxLayout()
        self.connect_button = QPushButton("Connect to Strava…")
        self.connect_button.clicked.connect(self._start_oauth)
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self._disconnect)
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.disconnect_button)
        button_row.addStretch(1)
        auth_layout.addLayout(button_row)
        outer.addWidget(auth_box)

        filters_box = QGroupBox("Import filters")
        filters_form = QFormLayout(filters_box)
        today = QDate.currentDate()
        self.after_edit = QDateEdit(today.addMonths(-1))
        self.after_edit.setCalendarPopup(True)
        self.before_edit = QDateEdit(today)
        self.before_edit.setCalendarPopup(True)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 1000)
        self.limit_spin.setValue(30)
        filters_form.addRow("Activities after:", self.after_edit)
        filters_form.addRow("Activities before:", self.before_edit)
        filters_form.addRow("Max activities:", self.limit_spin)
        outer.addWidget(filters_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        self.buttons = QDialogButtonBox()
        self.import_button = self.buttons.addButton("Import activities", QDialogButtonBox.AcceptRole)
        self.buttons.addButton(QDialogButtonBox.Close)
        self.buttons.accepted.connect(self._import_activities)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

    # -------------------------------------------------------------- helpers

    def _load_settings(self) -> None:
        values = settings_store.load()
        self.client_id_edit.setText(values["client_id"])
        self.client_secret_edit.setText(values["client_secret"])

    def _build_client(self) -> StravaClient:
        values = settings_store.load()
        return StravaClient(
            client_id=self.client_id_edit.text().strip(),
            client_secret=self.client_secret_edit.text().strip(),
            access_token=values["access_token"],
            refresh_token=values["refresh_token"],
            expires_at=int(values["expires_at"] or 0),
        )

    def _persist_client(self, client: StravaClient) -> None:
        settings_store.save({
            "client_id": client.client_id,
            "client_secret": client.client_secret,
            "access_token": client.access_token,
            "refresh_token": client.refresh_token,
            "expires_at": str(client.expires_at),
        })

    def _refresh_auth_label(self) -> None:
        values = settings_store.load()
        if values["access_token"]:
            expires_at = int(values["expires_at"] or 0)
            if expires_at:
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(expires_at))
                self.auth_status_label.setText(f"Connected. Token expires at {when} (auto-refreshes).")
            else:
                self.auth_status_label.setText("Connected.")
            self.connect_button.setText("Re-authorize")
            self.disconnect_button.setEnabled(True)
        else:
            self.auth_status_label.setText("Not connected.")
            self.connect_button.setText("Connect to Strava…")
            self.disconnect_button.setEnabled(False)

    # ----------------------------------------------------------------- OAuth

    def _start_oauth(self) -> None:
        client_id = self.client_id_edit.text().strip()
        client_secret = self.client_secret_edit.text().strip()
        if not client_id or not client_secret:
            QMessageBox.warning(self, "Strava", "Enter your Client ID and Client secret first.")
            return

        # Persist creds so the callback handler can use them after the redirect.
        settings_store.save({"client_id": client_id, "client_secret": client_secret})

        try:
            self._callback_server = OAuthCallbackServer(port=0)
            self._callback_server.start()
        except OSError as exc:
            QMessageBox.critical(self, "Strava", f"Could not start local callback server: {exc}")
            return

        client = self._build_client()
        url = client.authorize_url(self._callback_server.redirect_uri)
        webbrowser.open(url)

        self.connect_button.setEnabled(False)
        self.auth_status_label.setText(
            "Waiting for Strava authorization in your browser… "
            "(this window will update automatically)"
        )
        self._poll_deadline = time.time() + 180  # 3 minutes
        self._poll_timer.start()

    def _poll_callback(self) -> None:
        if not self._callback_server:
            self._poll_timer.stop()
            return

        captured = self._callback_server.captured()
        if captured is None:
            if time.time() > self._poll_deadline:
                self._poll_timer.stop()
                self._stop_callback_server()
                self.connect_button.setEnabled(True)
                self.auth_status_label.setText("Authorization timed out. Try again.")
            return

        self._poll_timer.stop()
        self._stop_callback_server()
        self.connect_button.setEnabled(True)

        if "error" in captured or "code" not in captured:
            err = captured.get("error", "missing code")
            QMessageBox.warning(self, "Strava", f"Authorization failed: {err}")
            return

        code = captured["code"]
        client = self._build_client()
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            client.exchange_code(code)
        except StravaError as exc:
            QMessageBox.critical(self, "Strava", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()

        self._persist_client(client)
        self._refresh_auth_label()
        QMessageBox.information(self, "Strava", "Connected to Strava.")

    def _stop_callback_server(self) -> None:
        if self._callback_server:
            try:
                self._callback_server.stop()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
            self._callback_server = None

    def _disconnect(self) -> None:
        settings_store.clear_tokens()
        self._refresh_auth_label()

    # ----------------------------------------------------------------- import

    def _import_activities(self) -> None:
        client = self._build_client()
        if not client.access_token:
            QMessageBox.warning(self, "Strava", "Connect to Strava before importing.")
            return

        after = int(time.mktime(self.after_edit.date().toPyDate().timetuple()))
        before = int(time.mktime(self.before_edit.date().addDays(1).toPyDate().timetuple()))
        if before <= after:
            QMessageBox.warning(self, "Strava", "'Before' date must be after the 'after' date.")
            return

        self.progress.setVisible(True)
        self.import_button.setEnabled(False)
        QApplication.processEvents()

        try:
            activities = client.list_activities(
                after=after,
                before=before,
                max_activities=self.limit_spin.value(),
            )
            self._persist_client(client)
        except StravaError as exc:
            QMessageBox.critical(self, "Strava", str(exc))
            return
        finally:
            self.progress.setVisible(False)
            self.import_button.setEnabled(True)

        if not activities:
            QMessageBox.information(self, "Strava", "No activities found in the selected window.")
            return

        layer = build_layer(activities, layer_name=f"Strava ({len(activities)} activities)")
        add_to_project(layer)
        if layer.featureCount():
            self.iface.mapCanvas().setExtent(layer.extent())
            self.iface.mapCanvas().refresh()

        skipped = layer.customProperty("strava/skipped_no_track", 0)
        summary = f"Imported {layer.featureCount()} activity tracks."
        if skipped:
            summary += f" Skipped {skipped} activities without GPS data (e.g. indoor workouts)."
        QMessageBox.information(self, "Strava", summary)

    def closeEvent(self, event):  # noqa: N802 - Qt API
        self._poll_timer.stop()
        self._stop_callback_server()
        super().closeEvent(event)
