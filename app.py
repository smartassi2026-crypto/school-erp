import os
import uuid
from datetime import date, datetime
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "smart-school-crm-secret")
CORS(app)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MEMORY_DB = {
    "departments": [],
    "classes": [],
    "sections": [],
    "subjects": [],
    "students": [],
    "teachers": [],
    "users": [],
    "attendance": [],
    "fees": [],
    "exams": [],
    "marks": [],
    "admit_cards": [],
    "certificates": [],
    "library_books": [],
    "library_transactions": [],
    "transport_routes": [],
    "transport_vehicles": [],
    "hostel_rooms": [],
    "hostel_assignments": [],
    "payroll": [],
    "leaves": [],
    "notices": [],
    "settings": [],
    "activity_logs": [],
    "old_data_uploads": [],
}

ROUTE_TABLES = {
    "departments": "departments",
    "classes": "classes",
    "sections": "sections",
    "subjects": "subjects",
    "students": "students",
    "teachers": "teachers",
    "users": "users",
    "attendance": "attendance",
    "fees": "fees",
    "exams": "exams",
    "marks": "marks",
    "admit-cards": "admit_cards",
    "certificates": "certificates",
    "library": "library_books",
    "transport": "transport_routes",
    "hostel": "hostel_rooms",
    "payroll": "payroll",
    "leaves": "leaves",
    "notices": "notices",
}

MOCK_USERS = [
    {"id": "u-admin", "email": "admin@smartschool.com", "password": "password123", "role": "Super Admin", "name": "Smart School Admin"},
    {"id": "u-teacher", "email": "teacher@smartschool.com", "password": "password123", "role": "Teacher", "name": "Demo Teacher"},
    {"id": "u-accountant", "email": "accountant@smartschool.com", "password": "password123", "role": "Accountant", "name": "Demo Accountant"},
    {"id": "u-staff", "email": "staff@smartschool.com", "password": "password123", "role": "Receptionist", "name": "Demo Staff"},
    {"id": "u-student", "email": "student@smartschool.com", "password": "password123", "role": "Student / Parent", "name": "Demo Student"},
]


def now_iso():
    return datetime.utcnow().isoformat()


def new_id():
    return str(uuid.uuid4())


def clean_payload(payload: dict) -> dict:
    blocked = {"id", "created_at"}
    return {k: v for k, v in payload.items() if k not in blocked}


def log_activity(message: str, actor: str = "system"):
    row = {"id": new_id(), "message": message, "actor": actor, "created_at": now_iso()}
    try:
        db_insert("activity_logs", row)
    except Exception:
        MEMORY_DB["activity_logs"].append(row)


def db_select(table: str):
    if supabase:
        result = supabase.table(table).select("*").order("created_at", desc=True).execute()
        return result.data or []
    return MEMORY_DB.get(table, [])


def db_insert(table: str, payload: dict):
    payload = payload.copy()
    payload.setdefault("id", new_id())
    payload.setdefault("created_at", now_iso())
    if supabase:
        result = supabase.table(table).insert(payload).execute()
        return (result.data or [payload])[0]
    MEMORY_DB.setdefault(table, []).append(payload)
    return payload


def db_update(table: str, row_id: str, payload: dict):
    payload = clean_payload(payload)
    if not payload:
        return db_get(table, row_id)
    if supabase:
        result = supabase.table(table).update(payload).eq("id", row_id).execute()
        data = result.data or []
        return data[0] if data else db_get(table, row_id)
    rows = MEMORY_DB.setdefault(table, [])
    for row in rows:
        if str(row.get("id")) == str(row_id):
            row.update(payload)
            return row
    raise KeyError("Record not found")


def db_delete(table: str, row_id: str):
    if supabase:
        supabase.table(table).delete().eq("id", row_id).execute()
        return True
    rows = MEMORY_DB.setdefault(table, [])
    before = len(rows)
    MEMORY_DB[table] = [r for r in rows if str(r.get("id")) != str(row_id)]
    return len(MEMORY_DB[table]) < before


def db_get(table: str, row_id: str):
    rows = db_select(table)
    for row in rows:
        if str(row.get("id")) == str(row_id):
            return row
    return None


def api_response(data=None, status=200, message="ok"):
    return jsonify({"status": message, "data": data}), status


def api_error(message, status=400):
    return jsonify({"status": "error", "error": str(message)}), status


def require_json(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method in ["POST", "PUT"] and not request.is_json:
            return api_error("JSON body required", 415)
        return fn(*args, **kwargs)
    return wrapper


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "service": "Smart School CRM", "time": now_iso()})


@app.route("/api/login", methods=["POST"])
@require_json
def login():
    payload = request.get_json() or {}
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    user = next((u for u in MOCK_USERS if u["email"] == email and u["password"] == password), None)

    if not user:
        all_users = db_select("users")
        user = next(
            (
                u for u in all_users
                if str(u.get("email", "")).lower() == email
                and str(u.get("password", u.get("password_pin", ""))) == password
            ),
            None,
        )

    if not user:
        return api_error("Invalid login credentials", 401)

    safe_user = {k: v for k, v in user.items() if k != "password"}
    token = f"mock-token-{safe_user.get('id', new_id())}"
    log_activity(f"{safe_user.get('email')} logged in", safe_user.get("email", "system"))
    return jsonify({"token": token, "user": safe_user})


@app.route("/api/dashboard/stats")
def dashboard_stats():
    students = db_select("students")
    teachers = db_select("teachers")
    attendance = db_select("attendance")
    fees = db_select("fees")
    exams = db_select("exams")
    logs = db_select("activity_logs")

    today_str = str(date.today())
    month_prefix = today_str[:7]

    today_attendance = len([a for a in attendance if str(a.get("date", "")).startswith(today_str)])
    monthly_collection = sum(float(f.get("paid") or 0) for f in fees if str(f.get("payment_date", f.get("created_at", ""))).startswith(month_prefix))
    pending_fees = sum(float(f.get("due") or 0) for f in fees)

    class_counts = {}
    for s in students:
        cls = str(s.get("class_id") or s.get("class_name") or "Unknown")
        class_counts[cls] = class_counts.get(cls, 0) + 1

    due_list = []
    for f in fees:
        if float(f.get("due") or 0) > 0:
            student = next((s for s in students if str(s.get("id")) == str(f.get("student_id"))), {})
            due_list.append({"name": student.get("name", "Student"), "due": f.get("due", 0)})

    data = {
        "total_students": len(students),
        "total_teachers": len(teachers),
        "today_attendance": today_attendance,
        "monthly_collection": monthly_collection,
        "pending_fees": pending_fees,
        "new_admissions": len([s for s in students if str(s.get("created_at", "")).startswith(month_prefix)]),
        "active_classes": len(class_counts),
        "upcoming_exams": len([e for e in exams if e.get("status", "Active") == "Active"]),
        "class_wise": [{"class": k, "count": v} for k, v in class_counts.items()],
        "attendance_chart": [today_attendance, max(len(students) - today_attendance, 0), 0, 0],
        "fee_collection_chart": [monthly_collection],
        "admission_trend": [len(students)],
        "recent_activities": [l.get("message", "Activity") for l in logs[:8]],
        "due_list": due_list[:10],
        "teachers": teachers[:10],
    }
    return api_response(data)


def register_crud(endpoint: str, table: str):
    list_url = f"/api/{endpoint}"
    item_url = f"/api/{endpoint}/<row_id>"

    def list_create(row_id=None, endpoint=endpoint, table=table):
        if request.method == "GET":
            return api_response(db_select(table))

        payload = request.get_json() or {}
        if table == "students":
            payload.setdefault("admission_no", "ADM-" + datetime.utcnow().strftime("%Y%m%d%H%M%S"))
            payload.setdefault("status", "Active")
        if table == "teachers":
            payload.setdefault("staff_id", "STF-" + datetime.utcnow().strftime("%Y%m%d%H%M%S"))
            payload.setdefault("status", "Active")
        if table == "fees":
            payload.setdefault("receipt_no", "REC-" + datetime.utcnow().strftime("%Y%m%d%H%M%S"))
            payload.setdefault("payment_date", str(date.today()))
        saved = db_insert(table, payload)
        log_activity(f"{table} record created")
        return api_response(saved, 201)

    def update_delete(row_id, endpoint=endpoint, table=table):
        if request.method == "PUT":
            payload = request.get_json() or {}
            updated = db_update(table, row_id, payload)
            log_activity(f"{table} record updated")
            return api_response(updated)

        deleted = db_delete(table, row_id)
        if not deleted:
            return api_error("Record not found", 404)
        log_activity(f"{table} record deleted")
        return api_response({"deleted": True})

    app.add_url_rule(list_url, f"{endpoint}_list_create", require_json(list_create), methods=["GET", "POST"])
    app.add_url_rule(item_url, f"{endpoint}_update_delete", require_json(update_delete), methods=["PUT", "DELETE"])


for endpoint_name, table_name in ROUTE_TABLES.items():
    register_crud(endpoint_name, table_name)


@app.route("/api/settings", methods=["GET", "PUT"])
@require_json
def settings():
    if request.method == "GET":
        rows = db_select("settings")
        if rows:
            return api_response(rows[0])
        default_settings = {
            "id": new_id(),
            "school_name": "Smart School CRM",
            "address": "",
            "phone": "",
            "email": "",
            "website": "",
            "session": "2026-27",
            "principal_name": "",
            "voice_enabled": True,
            "payment_gateway_enabled": False,
            "public_portal_enabled": True,
            "storage_limit_mb": 100,
            "created_at": now_iso(),
        }
        saved = db_insert("settings", default_settings)
        return api_response(saved)

    payload = request.get_json() or {}
    rows = db_select("settings")
    if rows:
        updated = db_update("settings", rows[0]["id"], payload)
    else:
        updated = db_insert("settings", payload)
    log_activity("Settings updated")
    return api_response(updated)


@app.route("/api/old-data-upload", methods=["POST"])
@require_json
def old_data_upload():
    payload = request.get_json() or {}
    data_type = payload.get("data_type", "Unknown")
    records = payload.get("records", [])

    if not isinstance(records, list):
        return api_error("records must be a list")

    map_type_to_table = {
        "Students": "students",
        "Teachers/staff": "teachers",
        "Attendance": "attendance",
        "Fees": "fees",
        "Exam/marks": "marks",
        "Library": "library_books",
        "Transport": "transport_routes",
        "Hostel": "hostel_rooms",
        "Payroll": "payroll",
        "Leaves": "leaves",
        "Certificates": "certificates",
        "Receipts": "fees",
    }

    target_table = map_type_to_table.get(data_type)
    count = 0
    if target_table:
        for record in records:
            if isinstance(record, dict):
                db_insert(target_table, record)
                count += 1

    history = db_insert("old_data_uploads", {
        "data_type": data_type,
        "record_count": count,
        "uploaded_by": payload.get("uploaded_by", "Admin"),
        "created_at": now_iso(),
    })
    log_activity(f"Old data imported: {data_type} ({count})")
    return api_response({"imported": count, "history": history}, 201)


@app.route("/api/public/student-login", methods=["POST"])
@require_json
def public_student_login():
    payload = request.get_json() or {}
    identity = str(payload.get("identity", "")).lower()
    pin = str(payload.get("pin", ""))
    students = db_select("students")
    student = next(
        (
            s for s in students
            if identity in " ".join([str(s.get("id", "")), str(s.get("admission_no", "")), str(s.get("mobile", "")), str(s.get("name", ""))]).lower()
            and str(s.get("password_pin", "")) == pin
        ),
        None,
    )
    if not student:
        return api_error("Invalid student credentials", 401)
    return api_response(student)


@app.errorhandler(404)
def not_found(_):
    return api_error("Route not found", 404)


@app.errorhandler(Exception)
def server_error(error):
    return api_error(str(error), 500)


if __name__ == "__main__":
    app.run(debug=True)
