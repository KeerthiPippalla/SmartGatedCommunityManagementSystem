from flask import Flask, request, jsonify, render_template
import os, time
import numpy as np
from firebase_admin import db

from recognize_visitor import recognize_visitor
from register_visitor import register_new_visitor
from firebase_helper import (
    add_visitor_to_villa,
    log_visit,
    get_villa_vehicles,
    add_vehicle_to_villa,
    init_global_parking_slots,
    assign_global_parking_slot,
    free_global_parking_slot,
    log_vehicle_visit
)
from recognize_vehicle import recognize_vehicle

app = Flask(__name__)
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


PAGE_ROUTES = {
    "/": "index.html",
    "/index": "index.html",
    "/signup": "signup.html",
    "/guard": "guard.html",
    "/resident": "resident.html",
    "/admin": "admin.html",
    "/amenity_booking": "amenitybooking.html",
    "/verifyvisitor": "verifyvisitor.html",
    "/verifyvehicle": "verifyvehicle.html",
    "/verifiedvisitor": "verifiedvisitors.html",
    "/verifiedvehicle": "verifiedvehicle.html",
    "/manage_residents": "manageresidents.html",
    "/logs": "logs.html",
}


def register_static_pages(app):
    for route, template in PAGE_ROUTES.items():

        def handler(template_name=template):
            return render_template(template_name)

        app.add_url_rule(route, endpoint=route, view_func=handler)


register_static_pages(app)

@app.route("/send_message", methods=["POST"])
def send_message():
    data = request.get_json()

    sender = data.get("sender")
    role = data.get("role")
    text = data.get("text")

    if not sender or not text:
        return jsonify({"status": "error", "message": "Missing sender or text"})

    msg_id = f"MSG_{int(time.time()*1000)}"

    db.reference(f"community_messages/{msg_id}").set({
        "sender": sender,
        "role": role,
        "text": text,
        "time": int(time.time())
    })

    return jsonify({"status": "ok"})
@app.route("/get_messages")
def get_messages():
    ref = db.reference("community_messages")
    data = ref.get() or {}

    messages = []
    for msg_id, m in data.items():
        messages.append({
            "id": msg_id,
            "sender": m.get("sender"),
            "role": m.get("role"),
            "text": m.get("text"),
            "time": m.get("time")
        })

    messages.sort(key=lambda x: x["time"])
    return jsonify({"messages": messages})
@app.route("/community_communication")
def community_communication():
    return render_template("community_communication.html")
@app.route("/get_visitor_logs")
def get_visitor_logs():
    ref = db.reference("logs")
    logs_data = ref.get() or {}

    logs_list = []

    for entry_id, data in logs_data.items():
        if entry_id.startswith("entry_") or data.get("visitor_id"):
            logs_list.append({
                "entry_id": entry_id,
                "visitor_id": data.get("visitor_id"),
                "visitor_name": data.get("visitor_name"),
                "villa_id": data.get("villa_id"),
                "status": data.get("status"),
                "time": data.get("time")
            })

    logs_list.sort(key=lambda x: x["time"], reverse=True)
    return jsonify({"logs": logs_list})
@app.route("/get_vehicle_logs")
def get_vehicle_logs():
    ref = db.reference("logs")
    logs_data = ref.get() or {}

    logs_list = []

    for entry_id, data in logs_data.items():
        if entry_id.startswith("vehicle_") or data.get("vehicle_no"):
            logs_list.append({
                "entry_id": entry_id,
                "vehicle_no": data.get("vehicle_no"),
                "owner_name": data.get("owner_name"),
                "villa_id": data.get("villa_id"),
                "status": data.get("status"),
                "time": data.get("time")
            })

    logs_list.sort(key=lambda x: x["time"], reverse=True)
    return jsonify({"logs": logs_list})
@app.route("/notifications")
def notifications_page():
    return render_template("notifications.html")
@app.route("/manage_parking")
def manage_parking():
    return render_template("manageparking.html")

# ---------------- VISITOR RECOGNITION ----------------

@app.route("/recognize_visitor", methods=["POST"])
def recognize():
    villa_id = request.form["villa_id"].lower()
    img = request.files["image"]

    ext = os.path.splitext(img.filename)[1]
    temp_name = f"TEMP_{int(time.time())}{ext}"
    img_path = os.path.join(UPLOAD_FOLDER, temp_name)
    img.save(img_path)

    result = recognize_visitor(img_path, villa_id)

    # recognized
    if result.get("status") == "allowed":
        log_visit(
            visitor_id=result["visitor_id"],
            villa_id=villa_id,
            status="Allowed - Recognized Visitor"
        )
        os.remove(img_path)
        return jsonify(result)

    # unknown → just return status
    os.remove(img_path)
    return jsonify({
        "status": "unknown",
        "message": "Unknown visitor. Ask name and post notification."
    })

# ---------------- CREATE NOTIFICATION ----------------

@app.route("/create_notification", methods=["POST"])
def create_notification():
    villa_id = request.form["villa_id"].lower()
    visitor_name = request.form["visitor_name"]
    img = request.files["image"]

    notif_id = f"NOTIF_{int(time.time())}"
    filename = f"{notif_id}.jpg"
    img_path = os.path.join(UPLOAD_FOLDER, filename)
    img.save(img_path)

    db.reference(f"notifications/{villa_id}/{notif_id}").set({
        "name": visitor_name,
        "image": filename,
        "status": "pending",
        "time": int(time.time())
    })

    return jsonify({
        "status": "ok",
        "notification_id": notif_id
    })

# ---------------- GET NOTIFICATIONS ----------------

@app.route("/get_notifications")
def get_notifications():
    villa_id = request.args.get("villa_id", "").lower()
    ref = db.reference(f"notifications/{villa_id}")
    data = ref.get() or {}

    notifications = []
    for notif_id, n in data.items():
        notifications.append({
            "notification_id": notif_id,
            "name": n.get("name"),
            "image": n.get("image"),
            "status": n.get("status"),
            "time": n.get("time")
        })

    notifications.sort(key=lambda x: x["time"], reverse=True)
    return jsonify({"notifications": notifications})

# ---------------- HANDLE NOTIFICATION (RESIDENT) ----------------

@app.route("/handle_notification", methods=["POST"])
def handle_notification():
    data = request.get_json()
    villa_id = data["villa_id"].lower()
    notif_id = data["notification_id"]
    decision = data["decision"]

    notif_ref = db.reference(f"notifications/{villa_id}/{notif_id}")
    notif_data = notif_ref.get()

    if not notif_data:
        return jsonify({"status": "error", "message": "Notification not found"})

    if decision == "reject":
        notif_ref.update({"status": "rejected"})
        return jsonify({"status": "rejected"})

    notif_ref.update({"status": "approved"})
    return jsonify({"status": "approved"})

# ---------------- CHECK NOTIFICATION STATUS (GUARD POLL) ----------------

@app.route("/check_notification_status")
def check_notification_status():
    villa_id = request.args.get("villa_id").lower()
    notif_id = request.args.get("notif_id")

    ref = db.reference(f"notifications/{villa_id}/{notif_id}")
    data = ref.get()

    if not data:
        return jsonify({"status": "deleted"})

    return jsonify({"status": data.get("status")})

# ---------------- FINAL REGISTER VISITOR (GUARD) ----------------

@app.route("/final_register_visitor", methods=["POST"])
def final_register_visitor():
    villa_id = request.form["villa_id"].lower()
    notif_id = request.form["notif_id"]
    images = request.files.getlist("images")

    notif_ref = db.reference(f"notifications/{villa_id}/{notif_id}")
    notif = notif_ref.get()

    if not notif or notif["status"] != "approved":
        return jsonify({"status": "error", "message": "Not approved yet"})

    visitor_id = "VIS_" + str(int(time.time()))
    success, msg = register_new_visitor(villa_id, images, visitor_id)
    if not success:
        return jsonify({"status": "error", "message": msg})

    add_visitor_to_villa(villa_id, visitor_id, notif["name"])

    log_visit(
        visitor_id=visitor_id,
        villa_id=villa_id,
        status="Allowed - Approved Visitor Registered"
    )

    try:
        display_image = images[0]   # take first uploaded image
        save_path = os.path.join(UPLOAD_FOLDER, f"{visitor_id}.jpg")

        # reset pointer just in case
        display_image.stream.seek(0)

        display_image.save(save_path)
        print("Saved visitor display image at:", save_path)

    except Exception as e:
        print("Error saving visitor display image:", e)

    notif_ref.delete()

    notif_img_path = os.path.join(UPLOAD_FOLDER, notif["image"])
    if os.path.exists(notif_img_path):
        os.remove(notif_img_path)

    return jsonify({"status": "success"})
    

# ---------------- VERIFIED VISITORS ----------------

@app.route("/get_verified_visitors")
def get_verified_visitors():
    villa_id = request.args.get("villa_id", "").lower()
    if not villa_id:
        return jsonify({"visitors": []})

    ref = db.reference(f"villas/{villa_id}/visitors")
    visitors_data = ref.get()

    visitors_list = []
    if visitors_data:
        for visitor_id, data in visitors_data.items():
            visitors_list.append({
                "visitor_id": visitor_id,
                "name": data.get("name", ""),
                "last_allowed": data.get("last_allowed"),
                "total_entries": data.get("total_entries", 0)
            })

    return jsonify({"visitors": visitors_list})
@app.route("/get_verified_vehicles")
def get_verified_vehicles():
    villa_id = request.args.get("villa_id", "").lower()

    if not villa_id:
        return jsonify({"vehicles": []})

    ref = db.reference(f"villas/{villa_id}/vehicles")
    vehicles_data = ref.get() or {}

    vehicles_list = []

    for vehicle_no, data in vehicles_data.items():
        vehicles_list.append({
            "vehicle_no": data.get("vehicle_no", vehicle_no),
            "owner_name": data.get("owner_name", ""),
            "created_at": data.get("created_at", "")
        })

    return jsonify({"vehicles": vehicles_list})
@app.route("/delete_vehicle", methods=["POST"])
def delete_vehicle():
    data = request.get_json()
    villa_id = data.get("villa_id", "").lower()
    vehicle_no = data.get("vehicle_no")

    if not villa_id or not vehicle_no:
        return jsonify({"status": "error", "message": "Missing parameters"})

    ref = db.reference(f"villas/{villa_id}/vehicles/{vehicle_no}")
    if not ref.get():
        return jsonify({"status": "error", "message": "Vehicle not found"})

    ref.delete()

    return jsonify({"status": "success"})
@app.route("/delete_visitor", methods=["POST"])
def delete_visitor():
    try:
        data = request.get_json()
        villa_id = data.get("villa_id")
        visitor_id = data.get("visitor_id")

        if not villa_id or not visitor_id:
            return jsonify({"status": "error", "message": "Missing data"}), 400

        ref = db.reference(f"villas/{villa_id}/visitors/{visitor_id}")

        if not ref.get():
            return jsonify({"status": "error", "message": "Visitor not found"}), 404

        ref.delete()

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
@app.route("/admin_amenity_usage")
def admin_amenity_usage():
    return render_template("admin_amenity_usage.html")

# ---------------- VEHICLE ENTRY / EXIT ----------------

@app.route("/verify_vehicle_entry_exit", methods=["POST"])
def verify_vehicle_entry_exit():
    try:
        villa_id = request.form.get("villa_id", "").lower()
        mode = request.form.get("mode", "").upper()
        owner_name = request.form.get("owner_name", "").strip()
        img = request.files.get("image")

        if not villa_id or not mode or not img:
            return jsonify({"status": "error", "message": "Missing parameters"})

        ext = os.path.splitext(img.filename)[1]
        temp_name = f"VEH_{int(time.time())}{ext}"
        img_path = os.path.join(UPLOAD_FOLDER, temp_name)
        img.save(img_path)

        init_global_parking_slots()
        vehicle_no = recognize_vehicle(img_path)

        if os.path.exists(img_path):
            os.remove(img_path)

        if not vehicle_no:
            return jsonify({"status": "error", "message": "Could not detect vehicle number"})

        vehicle_no = vehicle_no.upper()
        vehicles = get_villa_vehicles(villa_id)
        vehicle_data = vehicles.get(vehicle_no)

        if mode == "ENTRY":
            slots_data = db.reference("parking_slots").get() or {}
            for s in slots_data.values():
                if s.get("vehicle_no") == vehicle_no:
                    return jsonify({"status": "error", "message": f"{vehicle_no} already parked"})

            if not vehicle_data:
                if not owner_name:
                    return jsonify({"status": "new_vehicle", "vehicle_no": vehicle_no})
                add_vehicle_to_villa(villa_id, vehicle_no, owner_name)
                vehicle_data = {"owner_name": owner_name}

            slot = assign_global_parking_slot(vehicle_no, villa_id)
            if slot is None:
                return jsonify({"status": "full", "message": "Parking Full"})

            log_vehicle_visit(vehicle_no, vehicle_data["owner_name"], villa_id, "ENTRY")

            return jsonify({
                "status": "allowed",
                "vehicle_no": vehicle_no,
                "owner_name": vehicle_data["owner_name"],
                "slot": slot,
                "message": f"PLEASE ALLOW THE VEHICLE {vehicle_no} TO PARK AT {slot}"
            })

        elif mode == "EXIT":

            if not vehicle_data:
                return jsonify({"status": "error", "message": "Unknown vehicle"})

            slot = free_global_parking_slot(vehicle_no)

            if slot is None:
                return jsonify({
                    "status": "error",
                    "message": f"NO ACTIVE ENTRY FOUND FOR {vehicle_no}"
                })

            log_vehicle_visit(vehicle_no, vehicle_data["owner_name"], villa_id, "EXIT")

            return jsonify({
                "status": "exit_ok",
                "vehicle_no": vehicle_no,
                "owner_name": vehicle_data["owner_name"],
                "freed_slot": slot,
                "message": f"EXIT ALLOWED FOR {vehicle_no}"
            })


        else:
            return jsonify({"status": "error", "message": "Invalid mode"})

    except Exception as e:
        print("Vehicle error:", e)
        return jsonify({"status": "error", "message": str(e)})
@app.route("/create_vehicle_notification", methods=["POST"])
def create_vehicle_notification():
    villa_id = request.form["villa_id"].lower()
    vehicle_no = request.form["vehicle_no"]
    owner_name = request.form["owner_name"]

    notif_id = f"VEH_NOTIF_{int(time.time())}"

    db.reference(f"vehicle_notifications/{villa_id}/{notif_id}").set({
        "vehicle_no": vehicle_no,
        "owner_name": owner_name,
        "status": "pending",
        "time": int(time.time())
    })

    return jsonify({
        "status": "ok",
        "notification_id": notif_id
    })
@app.route("/get_vehicle_notifications")
def get_vehicle_notifications():
    villa_id = request.args.get("villa_id", "").lower()

    ref = db.reference(f"vehicle_notifications/{villa_id}")
    data = ref.get() or {}

    notifs = []
    for nid, n in data.items():
        notifs.append({
            "notification_id": nid,
            "vehicle_no": n.get("vehicle_no"),
            "owner_name": n.get("owner_name"),
            "status": n.get("status"),
            "time": n.get("time")
        })

    notifs.sort(key=lambda x: x["time"], reverse=True)
    return jsonify({"notifications": notifs})
@app.route("/handle_vehicle_notification", methods=["POST"])
def handle_vehicle_notification():
    data = request.get_json()

    villa_id = data["villa_id"].lower()
    notif_id = data["notification_id"]
    decision = data["decision"]

    ref = db.reference(f"vehicle_notifications/{villa_id}/{notif_id}")
    notif = ref.get()

    if not notif:
        return jsonify({"status": "error", "message": "Notification not found"})

    if decision == "reject":
        ref.update({"status": "rejected"})
        return jsonify({"status": "rejected"})

    ref.update({"status": "approved"})
    return jsonify({"status": "approved"})
@app.route("/check_vehicle_notification_status")
def check_vehicle_notification_status():
    villa_id = request.args.get("villa_id").lower()
    notif_id = request.args.get("notif_id")

    ref = db.reference(f"vehicle_notifications/{villa_id}/{notif_id}")
    data = ref.get()

    if not data:
        return jsonify({"status": "deleted"})

    return jsonify({"status": data.get("status")})
@app.route("/final_register_vehicle", methods=["POST"])
def final_register_vehicle():
    villa_id = request.form["villa_id"].lower()
    notif_id = request.form["notif_id"]

    ref = db.reference(f"vehicle_notifications/{villa_id}/{notif_id}")
    notif = ref.get()

    if not notif or notif["status"] != "approved":
        return jsonify({"status": "error", "message": "Not approved yet"})

    vehicle_no = notif["vehicle_no"]
    owner_name = notif["owner_name"]

    # register in villa
    add_vehicle_to_villa(villa_id, vehicle_no, owner_name)

    # assign slot
    slot = assign_global_parking_slot(vehicle_no, villa_id)
    if slot is None:
        return jsonify({"status": "full", "message": "Parking Full"})

    # log entry
    log_vehicle_visit(vehicle_no, owner_name, villa_id, "ENTRY")

    # cleanup
    ref.delete()

    return jsonify({
        "status": "allowed",
        "vehicle_no": vehicle_no,
        "slot": slot,
        "message": f"PLEASE ALLOW THE VEHICLE {vehicle_no} TO PARK AT {slot}"
    })
# -------- GET CLUBHOUSE CALENDAR --------
@app.route("/get_clubhouse_calendar")
def get_clubhouse_calendar():
    villa_id = request.args.get("villa_id")
    ref = db.reference("amenities/clubhouse")
    data = ref.get() or {}
    return jsonify(data)


# -------- BOOK CLUBHOUSE --------
@app.route("/book_clubhouse", methods=["POST"])
def book_clubhouse():
    data = request.get_json()
    villa_id = data["villa_id"]
    date = data["date"]

    ref = db.reference(f"amenities/clubhouse/{date}")
    if ref.get():
        return jsonify({"status": "error", "message": "Date already booked"})

    ref.set({
        "status": "booked",
        "villa_id": villa_id,
        "booked_at": int(time.time())
    })

    return jsonify({"status": "ok", "message": f"Clubhouse booked for {date}"})


# -------- GET POOL / GYM SLOTS --------
@app.route("/get_pool_gym_slots")
def get_pool_gym_slots():
    amenity = request.args.get("amenity").lower()  # pool / gym
    date = request.args.get("date")

    ref = db.reference(f"amenities/{amenity}/{date}")
    data = ref.get() or {}

    return jsonify(data)


# -------- BOOK POOL / GYM SLOT --------
@app.route("/book_pool_gym", methods=["POST"])
def book_pool_gym():
    data = request.get_json()
    villa_id = data["villa_id"]
    amenity = data["amenity"].lower()
    date = data["date"]
    slot = data["slot"]

    ref = db.reference(f"amenities/{amenity}/{date}/{slot}")
    slot_data = ref.get() or {"count": 0, "villas": {}}

    if slot_data["count"] >= 10:
        return jsonify({"status": "error", "message": "Slot fully booked"})

    if villa_id in slot_data["villas"]:
        return jsonify({"status": "error", "message": "You already booked this slot"})

    slot_data["count"] += 1
    slot_data["villas"][villa_id] = True

    ref.set(slot_data)

    return jsonify({
        "status": "ok",
        "message": f"{amenity.upper()} booked for {date} slot {slot}"
    })
@app.route("/get_residents")
def get_residents():
    ref = db.reference("users/residents")
    users_data = ref.get() or {}

    residents = []

    for username, data in users_data.items():
        residents.append({
            "username": username
        })

    residents.sort(key=lambda x: x["username"])
    return jsonify({"residents": residents})
@app.route("/delete_resident", methods=["POST"])
def delete_resident():
    data = request.get_json()
    username = data.get("username")

    if not username:
        return jsonify({"status": "error", "message": "Username missing"})

    ref = db.reference(f"users/residents/{username}")
    user = ref.get()

    if not user:
        return jsonify({"status": "error", "message": "Resident not found"})

    # delete resident
    ref.delete()

    # cleanup
    db.reference(f"villas/{username}").delete()
    db.reference(f"notifications/{username}").delete()
    db.reference(f"vehicle_notifications/{username}").delete()

    clubhouse_ref = db.reference("amenities/clubhouse")
    matches = clubhouse_ref.order_by_child("villa_id").equal_to(username).get()

    if matches:
        for key in matches:
            clubhouse_ref.child(key).delete()

    return jsonify({"status": "success"})


if __name__ == "__main__":
    app.run(debug=True)