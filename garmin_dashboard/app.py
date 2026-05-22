import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

_garmin_clients = {}


def get_client(session_id):
    return _garmin_clients.get(session_id)


def store_client(session_id, client):
    _garmin_clients[session_id] = client


def remove_client(session_id):
    _garmin_clients.pop(session_id, None)


@app.route("/")
def index():
    if "session_id" in session and get_client(session["session_id"]):
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    try:
        client = Garmin(email=email, password=password)
        client.login()
        session_id = os.urandom(16).hex()
        store_client(session_id, client)
        session["session_id"] = session_id
        return jsonify({"success": True})
    except GarminConnectAuthenticationError as e:
        logger.error("Authentication failed: %s", e)
        return jsonify({"error": "Invalid credentials. Please check your email and password."}), 401
    except GarminConnectConnectionError as e:
        logger.error("Connection error: %s", e)
        return jsonify({"error": "Could not connect to Garmin Connect. Please try again."}), 503
    except Exception as e:
        logger.error("Login error: %s", e)
        return jsonify({"error": f"Login failed: {str(e)}"}), 500


@app.route("/logout")
def logout():
    session_id = session.pop("session_id", None)
    if session_id:
        remove_client(session_id)
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    if "session_id" not in session or not get_client(session["session_id"]):
        return redirect(url_for("index"))
    return render_template("dashboard.html")


@app.route("/api/profile")
def api_profile():
    client = get_client(session.get("session_id"))
    if not client:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        profile = client.get_full_name()
        stats = client.get_user_summary(datetime.today().strftime("%Y-%m-%d"))
        return jsonify({"name": profile, "stats": stats})
    except Exception as e:
        logger.error("Profile error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/activities")
def api_activities():
    client = get_client(session.get("session_id"))
    if not client:
        return jsonify({"error": "Not authenticated"}), 401

    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    activity_type = request.args.get("type", "")

    try:
        activities = client.get_activities(offset, limit)
        result = []
        for act in activities:
            atype = act.get("activityType", {}).get("typeKey", "unknown")
            if activity_type and activity_type != "all" and atype != activity_type:
                continue

            start_lat = act.get("startLatitude")
            start_lon = act.get("startLongitude")

            result.append({
                "id": act.get("activityId"),
                "name": act.get("activityName", "Unknown Activity"),
                "type": atype,
                "typeDisplay": act.get("activityType", {}).get("typeKey", "unknown").replace("_", " ").title(),
                "startTime": act.get("startTimeLocal", ""),
                "distance": act.get("distance", 0),
                "duration": act.get("duration", 0),
                "elevationGain": act.get("elevationGain", 0),
                "averageHR": act.get("averageHR"),
                "maxHR": act.get("maxHR"),
                "averageSpeed": act.get("averageSpeed", 0),
                "calories": act.get("calories", 0),
                "startLat": start_lat,
                "startLon": start_lon,
                "hasGPS": start_lat is not None and start_lon is not None,
            })

        return jsonify({"activities": result, "total": len(result)})
    except Exception as e:
        logger.error("Activities error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/activity/<int:activity_id>/gps")
def api_activity_gps(activity_id):
    client = get_client(session.get("session_id"))
    if not client:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        gpx_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.GPX)
        if not gpx_data:
            return jsonify({"error": "No GPS data available"}), 404

        import xml.etree.ElementTree as ET
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}

        root = ET.fromstring(gpx_data)
        coordinates = []

        for trkpt in root.findall(".//gpx:trkpt", ns):
            lat = float(trkpt.get("lat", 0))
            lon = float(trkpt.get("lon", 0))
            ele_el = trkpt.find("gpx:ele", ns)
            ele = float(ele_el.text) if ele_el is not None else None
            time_el = trkpt.find("gpx:time", ns)
            time = time_el.text if time_el is not None else None

            hr = None
            hr_el = trkpt.find(".//gpx:hr", ns)
            if hr_el is None:
                hr_el = trkpt.find(".//{http://www.garmin.com/xmlschemas/TrackPointExtension/v1}hr")
            if hr_el is not None:
                try:
                    hr = int(hr_el.text)
                except (ValueError, TypeError):
                    pass

            if lat != 0 or lon != 0:
                coordinates.append({
                    "lat": lat,
                    "lon": lon,
                    "ele": ele,
                    "time": time,
                    "hr": hr,
                })

        if not coordinates:
            return jsonify({"error": "No coordinates found in GPS data"}), 404

        return jsonify({"coordinates": coordinates, "count": len(coordinates)})
    except Exception as e:
        logger.error("GPS data error for activity %s: %s", activity_id, e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats/summary")
def api_stats_summary():
    client = get_client(session.get("session_id"))
    if not client:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        activities = client.get_activities(0, 100)

        total_distance = sum(a.get("distance", 0) or 0 for a in activities)
        total_duration = sum(a.get("duration", 0) or 0 for a in activities)
        total_calories = sum(a.get("calories", 0) or 0 for a in activities)
        total_elevation = sum(a.get("elevationGain", 0) or 0 for a in activities)

        type_counts = {}
        for act in activities:
            atype = act.get("activityType", {}).get("typeKey", "unknown")
            type_counts[atype] = type_counts.get(atype, 0) + 1

        return jsonify({
            "totalActivities": len(activities),
            "totalDistanceKm": round(total_distance / 1000, 2),
            "totalDurationHrs": round(total_duration / 3600, 2),
            "totalCalories": int(total_calories),
            "totalElevationM": round(total_elevation, 0),
            "activityTypes": type_counts,
        })
    except Exception as e:
        logger.error("Stats error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/activity/<int:activity_id>/details")
def api_activity_details(activity_id):
    client = get_client(session.get("session_id"))
    if not client:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        details = client.get_activity(activity_id)
        return jsonify(details)
    except Exception as e:
        logger.error("Activity details error: %s", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
