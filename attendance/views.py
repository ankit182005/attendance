# attendance/views.py
# FINAL VERSION — Refresh-safe attendance, correct logout-on-close,
# admin delete/flush, CSV auto-save, timezone-safe.

import csv
import os
import json
import copy
import logging
import threading
from uuid import uuid4
from pathlib import Path
from datetime import datetime, timedelta

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import TokenAuthentication, get_authorization_header

logger = logging.getLogger("attendance")

# -------------------------------------------------------------
# GLOBALS
# -------------------------------------------------------------

STORE_LOCK = threading.RLock()
ATTENDANCE_STORE = {}  # user_id → {"sessions": []}

# NOTE: This server-side grace should match the client-side CLOSE_GRACE_MS.
# You asked for a 1 second client grace — keep them aligned.
REFRESH_GRACE_MS = 1000  # 1 second


CSV_HEADER = [
    "Username", "Full Name",
    "Session Start", "Session End",
    "Status", "Duration",
    "Break Count", "Break Details"
]

# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------


def _get_user_store(user):
    uid = str(user.id)
    with STORE_LOCK:
        if uid not in ATTENDANCE_STORE:
            ATTENDANCE_STORE[uid] = {"sessions": []}
        return ATTENDANCE_STORE[uid]


def _current_active_session(user):
    store = _get_user_store(user)
    for s in reversed(store["sessions"]):
        if s.get("is_active", False):
            return s
    return None


def _last_session(user):
    store = _get_user_store(user)
    if not store["sessions"]:
        return None
    return store["sessions"][-1]


def _duration_text(start, end):
    if not start:
        return "—"
    end = end or timezone.now()
    minutes = int((end - start).total_seconds() // 60)
    h = minutes // 60
    m = minutes % 60
    return f"{h}h {m}m"


# -------------------------------------------------------------
# AUTHENTICATION helper for beacon logout
# -------------------------------------------------------------


def _authenticate_any(request, body):
    """Accept JWT, DRF Token, or body.token."""
    # A: If already authenticated by DRF
    if hasattr(request, "user") and request.user.is_authenticated:
        return request.user, "request.user"

    # Body token?
    token_value = None

    # Authorization header
    auth = get_authorization_header(request).decode("utf-8") or ""
    if auth.startswith("Bearer "):
        token_value = auth.split(" ", 1)[1].strip()

    # body.token fallback
    if not token_value:
        token_value = body.get("token")

    if not token_value:
        return None, "none"

    # Try JWT first
    try:
        jwt = JWTAuthentication()
        validated = jwt.get_validated_token(token_value)
        user = jwt.get_user(validated)
        return user, "jwt_token"
    except Exception:
        pass

    # Try DRF Token model
    try:
        tok = TokenAuthentication()
        # authenticate_credentials expects the token string (not bytes)
        user, _ = tok.authenticate_credentials(token_value)
        return user, "drf_token"
    except Exception:
        pass

    return None, "none"


# -------------------------------------------------------------
# START ATTENDANCE
# -------------------------------------------------------------


class StartAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        logger.info("StartAttendance user_id=%s", user.id)

        active = _current_active_session(user)
        if active:
            return JsonResponse({
                "detail": "Already active",
                "attendance": {
                    "id": active["id"],
                    "start_time": active["start_time"].isoformat(),
                    "is_active": True
                }
            })

        # refresh-safe restore:
        last = _last_session(user)
        if last and last.get("ended_by_refresh"):
            # Restore
            last["is_active"] = True
            last["end_time"] = None
            last["ended_by_refresh"] = False
            return JsonResponse({
                "detail": "Restored session after refresh",
                "attendance": {
                    "id": last["id"],
                    "start_time": last["start_time"].isoformat(),
                    "is_active": True
                }
            })

        sess = {
            "id": str(uuid4()),
            "start_time": timezone.now(),
            "end_time": None,
            "is_active": True,
            "breaks": [],
            "last_update": timezone.now(),
            "ended_by_refresh": False,
        }

        with STORE_LOCK:
            store = _get_user_store(user)
            store["sessions"].append(sess)

        return JsonResponse({
            "detail": "Attendance started",
            "attendance": {
                "id": sess["id"],
                "start_time": sess["start_time"].isoformat(),
                "is_active": True
            }
        }, status=201)


# -------------------------------------------------------------
# TOGGLE BREAK
# -------------------------------------------------------------


class ToggleBreakView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        att = _current_active_session(user)
        if not att:
            return JsonResponse({"detail": "Start attendance first"}, status=400)

        now = timezone.now()
        with STORE_LOCK:
            # end active break?
            for b in reversed(att["breaks"]):
                if b.get("end_time") is None:
                    b["end_time"] = now
                    return JsonResponse({
                        "detail": "Break ended",
                        "break": {
                            "start_time": b["start_time"].isoformat(),
                            "end_time": b["end_time"].isoformat(),
                        }
                    })

            # start new break
            nb = {"start_time": now, "end_time": None}
            att["breaks"].append(nb)
            return JsonResponse({
                "detail": "Break started",
                "break": {"start_time": nb["start_time"].isoformat(), "end_time": None}
            }, status=201)


# -------------------------------------------------------------
# END ATTENDANCE (refresh-safe)
# -------------------------------------------------------------


class EndAttendanceView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logger.info("EndAttendance entry raw_user=%s", getattr(request.user, "id", None))

        # ---- tolerant request-body ----
        body = {}
        try:
            raw = request.body.decode("utf-8") if request.body else ""
        except Exception:
            raw = ""
        if raw:
            try:
                body = json.loads(raw)
            except Exception:
                from urllib.parse import parse_qs
                try:
                    parsed = parse_qs(raw)
                    body = {k: v[0] if isinstance(v, list) else v for k,v in parsed.items()}
                except:
                    body = {}

        # authenticate by any means
        user, via = _authenticate_any(request, body)
        if not user:
            logger.warning("EndAttendance auth failed via=%s", via)
            return JsonResponse({"detail": "Authentication failed"}, status=401)

        # log success path for diagnostics
        logger.debug("EndAttendance authenticated via=%s user_id=%s", via, user.id)

        att = _current_active_session(user)
        if not att:
            return JsonResponse({"detail": "No active attendance"}, status=200)

        now = timezone.now()
        time_gap_ms = (now - att.get("last_update", att["start_time"])).total_seconds() * 1000

        # REFRESH-SAFE LOGIC:
        if time_gap_ms < REFRESH_GRACE_MS:
            att["ended_by_refresh"] = True
            att["is_active"] = False
            att["end_time"] = now
            att["last_update"] = now
            return JsonResponse({"detail": "Temporary refresh end"}, status=200)

        # NORMAL END:
        with STORE_LOCK:
            # End break
            for b in att["breaks"]:
                if b.get("end_time") is None:
                    b["end_time"] = now

            # logout_time if provided
            logout_iso = body.get("logout_time")
            if logout_iso:
                try:
                    # parse ISO timestamp robustly and make timezone-aware
                    dt = datetime.fromisoformat(logout_iso)
                    if dt.tzinfo is None:
                        # assume client sends UTC (adjust if your client uses local timezone)
                        dt = timezone.make_aware(dt, timezone.utc)
                    att["end_time"] = dt
                except Exception:
                    att["end_time"] = now
            else:
                att["end_time"] = now

            att["is_active"] = False
            att["last_update"] = now
            att["ended_by_refresh"] = False

        # Save CSV
        try:
            date = att["end_time"].date()
            _save_csv_user_date(date)
        except Exception:
            logger.exception("CSV save failed for user_id=%s", user.id)

        return JsonResponse({
            "detail": "Attendance ended",
            "attendance": {
                "id": att["id"],
                "start_time": att["start_time"].isoformat(),
                "end_time": att["end_time"].isoformat(),
                "is_active": False,
                "breaks": [
                    {
                        "start_time": b["start_time"].isoformat(),
                        "end_time": b["end_time"].isoformat() if b["end_time"] else None,
                    }
                    for b in att["breaks"]
                ]
            }
        })


# ---- add this after EndAttendanceView in attendance/views.py ----

class ReviveAttendanceView(APIView):
    """
    Revive a recently ended session that was marked ended_by_refresh.
    Client calls this on quick reloads; server revives only if last end was within REFRESH_GRACE_MS.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        # tolerant body parsing (token may be in body)
        body = {}
        try:
            raw = request.body.decode('utf-8') if request.body else ''
        except Exception:
            raw = ''
        if raw:
            try:
                body = json.loads(raw)
            except Exception:
                from urllib.parse import parse_qs
                try:
                    parsed = parse_qs(raw)
                    body = {k: v[0] if isinstance(v, list) else v for k, v in parsed.items()}
                except Exception:
                    body = {}

        user, via = _authenticate_any(request, body)
        if not user:
            logger.warning("ReviveAttendance auth failed via=%s", via)
            return JsonResponse({"detail": "Authentication failed"}, status=401)

        # If already active, nothing to do
        att = _current_active_session(user)
        if att:
            return JsonResponse({"detail": "Already active"}, status=200)

        last = _last_session(user)
        if not last:
            return JsonResponse({"detail": "No recent session"}, status=200)

        # Only revive sessions that were marked ended_by_refresh
        if not last.get("ended_by_refresh"):
            return JsonResponse({"detail": "Not ended by refresh"}, status=200)

        now = timezone.now()
        gap_ms = (now - last.get("last_update", last.get("end_time", now))).total_seconds() * 1000

        if gap_ms <= REFRESH_GRACE_MS:
            with STORE_LOCK:
                last["is_active"] = True
                last["end_time"] = None
                last["ended_by_refresh"] = False
                last["last_update"] = now
            logger.info("Revived attendance for user_id=%s session_id=%s (gap_ms=%s)", user.id, last.get("id"), int(gap_ms))
            return JsonResponse({
                "detail": "Revived",
                "attendance": {
                    "id": last["id"],
                    "start_time": last["start_time"].isoformat(),
                    "is_active": True
                }
            }, status=200)
        else:
            logger.info("Revive attempt too old for user_id=%s gap_ms=%s", user.id, int(gap_ms))
            return JsonResponse({"detail": "Too old to revive"}, status=200)



def _save_csv_user_date(date):
    """Internal helper — re-generate CSV for given date."""
    rows = list(_rows_for_date(date))
    filename = f"attendance_{date}.csv"

    export_dir = Path(settings.CSV_EXPORT_DIR)
    export_dir.mkdir(exist_ok=True)

    pathf = export_dir / filename
    with pathf.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for r in rows:
            w.writerow(r)

    return str(pathf)


def _rows_for_date(date):
    with STORE_LOCK:
        snapshot = copy.deepcopy(ATTENDANCE_STORE)

    for uid, data in snapshot.items():
        # uid stored as string keys
        try:
            user_id = int(uid)
        except Exception:
            user_id = None

        u = User.objects.filter(id=user_id).first() if user_id is not None else None
        username = u.username if u else f"user_{uid}"
        full_name = u.get_full_name() if u else ""

        for s in data["sessions"]:
            st = s["start_time"]
            if not st or st.date() != date:
                continue
            et = s["end_time"]
            status = "Active" if s["is_active"] else "Completed"

            try:
                st_local = st.astimezone(timezone.get_current_timezone())
                st_txt = st_local.strftime("%d %b %Y, %I:%M %p")
            except Exception:
                st_txt = st.strftime("%d %b %Y, %I:%M %p")

            if et:
                try:
                    et_local = et.astimezone(timezone.get_current_timezone())
                    et_txt = et_local.strftime("%d %b %Y, %I:%M %p")
                except Exception:
                    et_txt = et.strftime("%d %b %Y, %I:%M %p")
            else:
                et_txt = "—"

            br_lines = []
            for b in s["breaks"]:
                bs = b["start_time"]
                be = b["end_time"]
                try:
                    bs_t = bs.astimezone(timezone.get_current_timezone()).strftime("%I:%M %p")
                except Exception:
                    bs_t = bs.strftime("%I:%M %p")
                try:
                    be_t = be.astimezone(timezone.get_current_timezone()).strftime("%I:%M %p") if be else "—"
                except Exception:
                    be_t = be.strftime("%I:%M %p") if be else "—"
                br_lines.append(f"{bs_t} → {be_t}")

            yield [
                username, full_name,
                st_txt, et_txt,
                status,
                _duration_text(st, et),
                len(s["breaks"]),
                "\n".join(br_lines)
            ]


# -------------------------------------------------------------
# CURRENT STATUS
# -------------------------------------------------------------


class CurrentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        active = _current_active_session(user)
        last = _last_session(user)

        def ser(s):
            if not s:
                return None
            return {
                "id": s["id"],
                "start_time": s["start_time"].isoformat(),
                "end_time": s["end_time"].isoformat() if s.get("end_time") else None,
                "is_active": s.get("is_active"),
                "breaks": [
                    {
                        "start_time": b["start_time"].isoformat(),
                        "end_time": b["end_time"].isoformat() if b["end_time"] else None,
                    }
                    for b in s["breaks"]
                ]
            }

        return JsonResponse({
            "active_attendance": ser(active),
            "last_attendance": ser(last)
        })


# -------------------------------------------------------------
# CSV EXPORT VIEWS (unchanged)
# -------------------------------------------------------------


class DailyCSVExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date = timezone.now().date()
        rows = list(_rows_for_date(date))

        res = HttpResponse(content_type="text/csv")
        res["Content-Disposition"] = f'attachment; filename="attendance_{date}.csv"'
        w = csv.writer(res)
        w.writerow(CSV_HEADER)
        for r in rows:
            w.writerow(r)
        return res


class CSVExportByDateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, year, month, day):
        try:
            date = datetime(int(year), int(month), int(day)).date()
        except Exception:
            return JsonResponse({"detail": "Invalid date"}, status=400)

        rows = list(_rows_for_date(date))
        res = HttpResponse(content_type="text/csv")
        res["Content-Disposition"] = f'attachment; filename="attendance_{date}.csv"'
        w = csv.writer(res)
        w.writerow(CSV_HEADER)
        for r in rows:
            w.writerow(r)
        return res


class SaveCSVToServerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, year=None, month=None, day=None):
        if year and month and day:
            try:
                date = datetime(int(year), int(month), int(day)).date()
            except Exception:
                return JsonResponse({"detail": "Invalid date"}, status=400)
        else:
            date = timezone.now().date()

        path = _save_csv_user_date(date)
        return JsonResponse({"detail": "saved", "path": path})


# -------------------------------------------------------------
# ADMIN ENDPOINTS
# -------------------------------------------------------------


class AdminCreateUserView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        d = request.data
        username = d.get("username")
        password = d.get("password")

        if not username or not password:
            return JsonResponse({"detail": "Missing fields"}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({"detail": "Username exists"}, status=400)

        user = User.objects.create(
            username=username,
            password=make_password(password),
            first_name=d.get("first_name", ""),
            last_name=d.get("last_name", ""),
            email=d.get("email", ""),
            is_staff=d.get("is_staff", False),
            is_active=True
        )
        return JsonResponse({"detail": "user created", "id": user.id}, status=201)


class DeleteEmployeeView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def delete(self, request, user_id):
        t = User.objects.filter(id=user_id).first()
        if not t:
            return JsonResponse({"detail": "not found"}, status=404)
        if t.is_staff:
            return JsonResponse({"detail": "cannot delete staff"}, status=403)
        if t.id == request.user.id:
            return JsonResponse({"detail": "cannot delete yourself"}, status=400)

        with STORE_LOCK:
            ATTENDANCE_STORE.pop(str(t.id), None)

        t.delete()
        return JsonResponse({"detail": "deleted"})


class FlushOtherUserDataView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, user_id):
        t = User.objects.filter(id=user_id).first()
        if not t:
            return JsonResponse({"detail": "not found"}, status=404)

        if t.is_staff:
            return JsonResponse({"detail": "cannot flush admin"}, status=403)

        with STORE_LOCK:
            ATTENDANCE_STORE[str(t.id)] = {"sessions": []}

        return JsonResponse({"detail": "flushed"})


class FlushAllNonAdminDataView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        flushed = []
        skipped = []

        with STORE_LOCK:
            for user in User.objects.filter(is_active=True):
                if user.is_staff:
                    skipped.append(user.id)
                    continue
                ATTENDANCE_STORE[str(user.id)] = {"sessions": []}
                flushed.append(user.id)

        return JsonResponse({
            "detail": "flush done",
            "flushed": flushed,
            "skipped": skipped
        })


class EmployeeListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        users = User.objects.filter(is_active=True)
        return JsonResponse({
            "employees": [
                {
                    "id": u.id,
                    "username": u.username,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                    "email": u.email,
                    "is_staff": u.is_staff
                }
                for u in users
            ]
        })


class EmployeeTrackingView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            return JsonResponse({"detail": "not found"}, status=404)

        with STORE_LOCK:
            sessions = copy.deepcopy(
                ATTENDANCE_STORE.get(str(user.id), {"sessions": []})["sessions"]
            )

        return JsonResponse({
            "user": {"id": user.id, "username": user.username},
            "sessions": [
                {
                    "id": s["id"],
                    "start_time": s["start_time"].isoformat(),
                    "end_time": s["end_time"].isoformat() if s.get("end_time") else None,
                    "is_active": s["is_active"],
                    "breaks": [
                        {
                            "start_time": b["start_time"].isoformat(),
                            "end_time": b["end_time"].isoformat() if b["end_time"] else None,
                        }
                        for b in s["breaks"]
                    ]
                }
                for s in sessions
            ]
        })


class PromoteDemoteUserView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, user_id):
        target = User.objects.filter(id=user_id).first()
        if not target:
            return JsonResponse({"detail": "not found"}, status=404)

        make_admin = bool(request.data.get("is_staff"))
        target.is_staff = make_admin
        target.save()
        return JsonResponse({"detail": "updated", "is_staff": make_admin})


# -------------------------------------------------------------
# CURRENT USER
# -------------------------------------------------------------


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return JsonResponse({
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "email": u.email,
            "is_staff": u.is_staff,
            "is_superuser": u.is_superuser,
        })
