import csv
import os
import threading
from uuid import uuid4
import logging
import copy
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from .serializers import RegisterSerializer

# logger for this app (route to file via settings.LOGGING)
logger = logging.getLogger('attendance')

# Use a re-entrant lock to avoid deadlocks if a function that already holds the lock
# calls a helper that also acquires the lock.
STORE_LOCK = threading.RLock()

# In-memory store
ATTENDANCE_STORE = {}

CSV_HEADER = ['username', 'full_name', 'start_time', 'end_time', 'is_active', 'break_count', 'break_details']


# Helpers
def _get_user_store(user):
    """
    Ensure a store exists for the given user and return it.
    This function acquires the STORE_LOCK to safely mutate ATTENDANCE_STORE.
    Callers that will further mutate the returned store may still hold the lock,
    since STORE_LOCK is an RLock (re-entrant).
    """
    uid = str(user.id)
    with STORE_LOCK:
        if uid not in ATTENDANCE_STORE:
            ATTENDANCE_STORE[uid] = {'sessions': []}
        return ATTENDANCE_STORE[uid]


def _current_active_session(user):
    """
    Return the most recent active session for the user, or None.
    NOTE: returns a reference into the in-memory store. Callers that plan to mutate
    the returned session must do so while holding STORE_LOCK.
    """
    store = _get_user_store(user)
    for s in reversed(store['sessions']):
        if s.get('is_active'):
            return s
    return None


def _format_breaks_for_row(breaks):
    items = []
    for b in breaks:
        s = b.get('start_time').isoformat() if b.get('start_time') else ''
        e = b.get('end_time').isoformat() if b.get('end_time') else ''
        items.append(f"{s} -> {e}")
    return ' ; '.join(items)


def _attendance_rows_for_date(date):
    """
    Snapshot ATTENDANCE_STORE while holding the lock, then perform DB lookups/writes
    without holding the lock to avoid long blocking. Use deepcopy to avoid nested
    mutation races while exporting.
    """
    with STORE_LOCK:
        snapshot = copy.deepcopy(ATTENDANCE_STORE)

    for uid, data in snapshot.items():
        sessions = data.get('sessions', [])
        try:
            user = User.objects.filter(id=int(uid)).first()
            username = user.username if user else f'user_{uid}'
            full_name = (user.get_full_name() if user else '').strip()
        except Exception:
            username = f'user_{uid}'
            full_name = ''
        for sess in sessions:
            st = sess.get('start_time')
            if not st:
                continue
            if st.date() == date:
                yield [
                    username,
                    full_name,
                    st.isoformat(),
                    sess.get('end_time').isoformat() if sess.get('end_time') else '',
                    str(sess.get('is_active', False)),
                    str(len(sess.get('breaks', []))),
                    _format_breaks_for_row(sess.get('breaks', [])),
                ]


# Attendance endpoints
class StartAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info("StartAttendance called by user_id=%s username=%s",
                    getattr(request.user, 'id', None),
                    getattr(request.user, 'username', None))
        user = request.user
        # Check if there's an active session
        active = _current_active_session(user)
        if active:
            return JsonResponse({'detail': 'Already active', 'attendance': {
                'id': active.get('id'),
                'start_time': active.get('start_time').isoformat() if active.get('start_time') else None,
                'is_active': active.get('is_active', False)
            }}, status=200)

        sess = {
            'id': str(uuid4()),
            'start_time': timezone.now(),
            'end_time': None,
            'is_active': True,
            'breaks': []
        }

        # Acquire lock when mutating shared store
        with STORE_LOCK:
            store = _get_user_store(user)
            store['sessions'].append(sess)
            logger.debug("Appended session %s for user %s; sessions_count=%d",
                         sess['id'], user.id, len(store['sessions']))

        logger.debug("Attendance session created for user_id=%s session_id=%s", user.id, sess['id'])
        return JsonResponse({
            'detail': 'Attendance started',
            'attendance': {
                'id': sess['id'],
                'start_time': sess['start_time'].isoformat(),
                'is_active': True
            }
        }, status=201)


class ToggleBreakView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info("ToggleBreak called by user_id=%s username=%s",
                    getattr(request.user, 'id', None),
                    getattr(request.user, 'username', None))
        user = request.user
        att = _current_active_session(user)
        if not att:
            return JsonResponse({'detail': 'Start attendance first'}, status=400)

        # Mutating shared session - hold the lock while changing breaks
        with STORE_LOCK:
            # find active break (last break with no end_time)
            active_break = None
            for b in reversed(att['breaks']):
                if b.get('end_time') is None:
                    active_break = b
                    break

            if active_break:
                active_break['end_time'] = timezone.now()
                logger.debug("Break ended for user_id=%s session_id=%s", user.id, att.get('id'))
                return JsonResponse({
                    'detail': 'Break ended',
                    'break': {
                        'start_time': active_break['start_time'].isoformat() if active_break.get('start_time') else None,
                        'end_time': active_break['end_time'].isoformat()
                    }
                }, status=200)
            else:
                newb = {'start_time': timezone.now(), 'end_time': None}
                att['breaks'].append(newb)
                logger.debug("Break started for user_id=%s session_id=%s", user.id, att.get('id'))
                return JsonResponse({
                    'detail': 'Break started',
                    'break': {
                        'start_time': newb['start_time'].isoformat(),
                        'end_time': None
                    }
                }, status=201)


class EndAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info("EndAttendance called by user_id=%s username=%s",
                    getattr(request.user, 'id', None),
                    getattr(request.user, 'username', None))
        user = request.user
        att = _current_active_session(user)
        if not att:
            return JsonResponse({'detail': 'No active attendance'}, status=400)

        # End active breaks and set end_time inside lock
        with STORE_LOCK:
            for b in att.get('breaks', []):
                if b.get('end_time') is None:
                    b['end_time'] = timezone.now()

            att['end_time'] = timezone.now()
            att['is_active'] = False

        logger.debug("Attendance ended for user_id=%s session_id=%s", user.id, att.get('id'))
        return JsonResponse({
            'detail': 'Attendance ended',
            'attendance': {
                'id': att['id'],
                'start_time': att['start_time'].isoformat() if att.get('start_time') else None,
                'end_time': att['end_time'].isoformat() if att.get('end_time') else None,
                'breaks': [
                    {
                        'start_time': b['start_time'].isoformat() if b.get('start_time') else None,
                        'end_time': (b['end_time'].isoformat() if b.get('end_time') else None)
                    }
                    for b in att.get('breaks', [])
                ],
                'is_active': att.get('is_active', False)
            }
        }, status=200)


class CurrentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger.debug("CurrentStatus requested by user_id=%s username=%s",
                     getattr(request.user, 'id', None),
                     getattr(request.user, 'username', None))
        user = request.user
        active = _current_active_session(user)
        store = _get_user_store(user)
        last = store['sessions'][-1] if store['sessions'] else None

        def serialize(sess):
            if not sess:
                return None
            return {
                'id': sess.get('id'),
                'start_time': sess.get('start_time').isoformat() if sess.get('start_time') else None,
                'end_time': sess.get('end_time').isoformat() if sess.get('end_time') else None,
                'is_active': sess.get('is_active', False),
                'breaks': [
                    {
                        'start_time': b['start_time'].isoformat() if b.get('start_time') else None,
                        'end_time': (b['end_time'].isoformat() if b.get('end_time') else None)
                    } for b in sess.get('breaks', [])
                ]
            }

        return JsonResponse({
            'active_attendance': serialize(active),
            'last_attendance': serialize(last)
        })


# CSV export
class DailyCSVExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger.info("DailyCSVExport requested by user_id=%s", getattr(request.user, 'id', None))
        today = timezone.now().date()
        rows = list(_attendance_rows_for_date(today))
        filename = f"attendance_{today}.csv"

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow(CSV_HEADER)
        for r in rows:
            writer.writerow(r)
        return response


class CSVExportByDateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, year, month, day):
        logger.info("CSVExportByDate requested by user_id=%s date=%s-%s-%s",
                    getattr(request.user, 'id', None), year, month, day)
        try:
            date = timezone.datetime(int(year), int(month), int(day)).date()
        except Exception:
            return JsonResponse({'detail': 'Invalid date'}, status=400)

        rows = list(_attendance_rows_for_date(date))
        filename = f"attendance_{date}.csv"
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow(CSV_HEADER)
        for r in rows:
            writer.writerow(r)
        return response


class SaveCSVToServerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, year=None, month=None, day=None):
        logger.info("SaveCSVToServer called by user_id=%s params=%s",
                    getattr(request.user, 'id', None), (year, month, day))
        try:
            if year and month and day:
                try:
                    date = timezone.datetime(int(year), int(month), int(day)).date()
                except Exception:
                    return JsonResponse({'detail': 'Invalid date'}, status=400)
            else:
                date = timezone.now().date()

            rows = list(_attendance_rows_for_date(date))
            filename = f"attendance_{date}.csv"

            # Ensure CSV_EXPORT_DIR is a Path
            export_dir = Path(getattr(settings, 'CSV_EXPORT_DIR', Path(settings.BASE_DIR) / 'csv_exports'))
            export_dir.mkdir(parents=True, exist_ok=True)
            filepath = export_dir / filename

            with filepath.open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADER)
                for r in rows:
                    writer.writerow(r)

            rel = os.path.relpath(str(filepath), str(settings.BASE_DIR))
            logger.info("CSV saved to %s by user_id=%s", filepath, request.user.id)
            return JsonResponse({'detail': 'saved', 'path': rel})
        except Exception:
            logger.exception("Failed to save CSV for user_id=%s", getattr(request.user, 'id', None))
            return JsonResponse({'detail': 'server error'}, status=500)


# Flush endpoints
class FlushUserDataView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.warning("FlushUserData called by user_id=%s", getattr(request.user, 'id', None))
        uid = str(request.user.id)
        with STORE_LOCK:
            ATTENDANCE_STORE[uid] = {'sessions': []}
        return JsonResponse({'detail': 'flushed user data'})


class FlushAllDataAdminView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        logger.warning("FlushAllDataAdmin called by admin_id=%s", getattr(request.user, 'id', None))
        with STORE_LOCK:
            ATTENDANCE_STORE.clear()
        return JsonResponse({'detail': 'flushed all data'})


# Auth & admin endpoints
class RegisterView(APIView):
    # Allow anonymous registration explicitly
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        logger.info("Register attempt username=%s", request.data.get('username'))
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            logger.debug("Register validation errors: %s", serializer.errors)
            return JsonResponse({'errors': serializer.errors}, status=400)
        data = serializer.validated_data
        try:
            user = User.objects.create(
                username=data['username'],
                password=make_password(data['password']),
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                email=data.get('email', ''),
                is_active=True,
                is_staff=False
            )
            logger.info("User created id=%s username=%s", user.id, user.username)
            return JsonResponse({'detail': 'user created', 'id': user.id, 'username': user.username}, status=201)
        except Exception:
            logger.exception("Failed to create user username=%s", data.get('username'))
            return JsonResponse({'detail': 'server error'}, status=500)


class AdminCreateUserView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        logger.info("AdminCreateUser called by admin_id=%s", getattr(request.user, 'id', None))
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            logger.debug("AdminCreateUser validation errors: %s", serializer.errors)
            return JsonResponse({'errors': serializer.errors}, status=400)
        data = serializer.validated_data
        is_staff = bool(request.data.get('is_staff', False))
        try:
            user = User.objects.create(
                username=data['username'],
                password=make_password(data['password']),
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                email=data.get('email', ''),
                is_active=True,
                is_staff=is_staff
            )
            logger.info("Admin created user id=%s username=%s is_staff=%s", user.id, user.username, user.is_staff)
            return JsonResponse({'detail': 'user created', 'id': user.id, 'username': user.username, 'is_staff': user.is_staff}, status=201)
        except Exception:
            logger.exception("AdminCreateUser failed by admin_id=%s username=%s", getattr(request.user, 'id', None), data.get('username'))
            return JsonResponse({'detail': 'server error'}, status=500)


class EmployeeListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        logger.debug("EmployeeList requested by admin_id=%s", getattr(request.user, 'id', None))
        users = User.objects.filter(is_active=True, is_superuser=False).order_by('username')
        data = [{'id': u.id, 'username': u.username, 'first_name': u.first_name, 'last_name': u.last_name, 'email': u.email, 'is_staff': u.is_staff} for u in users]
        return JsonResponse({'employees': data})


class EmployeeTrackingView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, user_id):
        logger.debug("EmployeeTracking requested by admin_id=%s for user_id=%s", getattr(request.user, 'id', None), user_id)
        user = User.objects.filter(id=user_id).first()
        if not user:
            return JsonResponse({'detail': 'not found'}, status=404)
        uid = str(user.id)
        with STORE_LOCK:
            store = ATTENDANCE_STORE.get(uid, {'sessions': []})
            sessions = copy.deepcopy(store.get('sessions', []))

        def serialize(sess):
            return {
                'id': sess.get('id'),
                'start_time': sess.get('start_time').isoformat() if sess.get('start_time') else None,
                'end_time': sess.get('end_time').isoformat() if sess.get('end_time') else None,
                'is_active': sess.get('is_active', False),
                'breaks': [
                    {
                        'start_time': b['start_time'].isoformat() if b.get('start_time') else None,
                        'end_time': (b['end_time'].isoformat() if b.get('end_time') else None)
                    } for b in sess.get('breaks', [])
                ]
            }

        return JsonResponse({'user': {'id': user.id, 'username': user.username}, 'sessions': [serialize(s) for s in sessions]})


class PromoteDemoteUserView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, user_id):
        logger.info("PromoteDemoteUser called by admin_id=%s target_user_id=%s", getattr(request.user, 'id', None), user_id)
        user = User.objects.filter(id=user_id).first()
        if not user:
            return JsonResponse({'detail': 'not found'}, status=404)
        make_admin = bool(request.data.get('is_staff', False))
        user.is_staff = make_admin
        user.save()
        logger.info("User id=%s is_staff set to %s by admin_id=%s", user.id, user.is_staff, getattr(request.user, 'id', None))
        return JsonResponse({'detail': 'updated', 'id': user.id, 'is_staff': user.is_staff})
