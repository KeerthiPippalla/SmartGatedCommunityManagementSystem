import firebase_admin
from firebase_admin import credentials, db
import time

import os
from dotenv import load_dotenv

load_dotenv()

cred = credentials.Certificate(os.getenv("FIREBASE_KEY_PATH"))
firebase_admin.initialize_app(cred, {
    "databaseURL": os.getenv("FIREBASE_DB_URL")
})



from datetime import datetime
from firebase_admin import db

def add_visitor_to_villa(villa_id, visitor_id, visitor_name):
    ref = db.reference(f"villas/{villa_id}/visitors/{visitor_id}")

    data = {
        "visitor_id": visitor_id,
        "name": visitor_name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_allowed": None,
        "total_entries": 0
    }

    ref.set(data)



def log_visit(visitor_id, villa_id, status):
    # 🔹 Fetch visitor name
    visitor_ref = db.reference(f"villas/{villa_id}/visitors/{visitor_id}")
    visitor_data = visitor_ref.get()

    if visitor_data and "name" in visitor_data:
        visitor_name = visitor_data["name"]
    else:
        visitor_name = "UNKNOWN"

    entry_id = f"entry_{int(time.time() * 1000)}"

    log_data = {
        "type":"visitor",

        "visitor_id": visitor_id,
        "visitor_name": visitor_name,
        "villa_id": villa_id,
        "status": status,
        "time": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    db.reference(f"logs/{entry_id}").set(log_data)

    ref = db.reference(f"villas/{villa_id}/visitors/{visitor_id}")
    data = ref.get() or {}

    total = data.get("total_entries", 0) + 1

    ref.update({
        "last_allowed": log_data["time"],
        "total_entries": total
    })

def get_villa_vehicles(villa_id):
    ref = db.reference(f"villas/{villa_id}/vehicles")
    return ref.get() or {}

def add_vehicle_to_villa(villa_id, vehicle_no, owner_name):
    vehicle_no = vehicle_no.upper()
    ref = db.reference(f"villas/{villa_id}/vehicles/{vehicle_no}")
    ref.set({
        "vehicle_no": vehicle_no,
        "owner_name": owner_name,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    })


def init_global_parking_slots():
    ref = db.reference("parking_slots")
    data = ref.get()

    if not data:
        slots = {}
        for i in range(1, 11):
            slots[f"SLOT_{i}"] = {
                "occupied": False,
                "vehicle_no": None,
                "villa_id": None
            }
        ref.set(slots)


def assign_global_parking_slot(vehicle_no, villa_id):
    slots_ref = db.reference("parking_slots")
    slots = slots_ref.get() or {}

    for slot_id, data in slots.items():
        if not data.get("occupied"):
            slots_ref.child(slot_id).update({
                "occupied": True,
                "vehicle_no": vehicle_no,
                "villa_id": villa_id
            })
            return slot_id

    return None


def free_global_parking_slot(vehicle_no):
    slots_ref = db.reference("parking_slots")
    slots = slots_ref.get() or {}

    for slot_id, data in slots.items():
        if data.get("vehicle_no") == vehicle_no:
            slots_ref.child(slot_id).update({
                "occupied": False,
                "vehicle_no": None,
                "villa_id": None
            })
            return slot_id

    return None


def log_vehicle_visit(vehicle_no, owner_name, villa_id, status):
    entry_id = f"vehicle_{int(time.time() * 1000)}"

    log_data = {
        "type":"vehicle",
        "vehicle_no": vehicle_no,
        "owner_name": owner_name,
        "villa_id": villa_id,
        "status": status,   # ENTRY / EXIT
        "time": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    db.reference(f"logs/{entry_id}").set(log_data)
