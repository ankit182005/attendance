# attendance/urls.py
from django.urls import path
from .views import (
    StartAttendanceView,
    EndAttendanceView,
    ToggleBreakView,
    CurrentStatusView,
    ReviveAttendanceView,

    DailyCSVExportView,
    CSVExportByDateView,
    SaveCSVToServerView,

    FlushOtherUserDataView,
    FlushAllNonAdminDataView,
    DeleteEmployeeView,

    AdminCreateUserView,
    EmployeeListView,
    EmployeeTrackingView,
    PromoteDemoteUserView,
    CurrentUserView,
)

urlpatterns = [
    path('start/', StartAttendanceView.as_view()),
    path('end/', EndAttendanceView.as_view()),
    path('break/toggle/', ToggleBreakView.as_view()),
    path('status/', CurrentStatusView.as_view()),
    path('revive_if_recent/', ReviveAttendanceView.as_view()),

    # CSV export
    path('export/today/', DailyCSVExportView.as_view()),
    path('export/<int:year>/<int:month>/<int:day>/', CSVExportByDateView.as_view()),
    path('export/save/today/', SaveCSVToServerView.as_view()),
    path('export/save/<int:year>/<int:month>/<int:day>/', SaveCSVToServerView.as_view()),

    # Admin-only
    path('auth/admin/flush/<int:user_id>/', FlushOtherUserDataView.as_view()),
    path('auth/admin/flush_all/', FlushAllNonAdminDataView.as_view()),
    path('auth/admin/delete/<int:user_id>/', DeleteEmployeeView.as_view()),

    # Admin user creation & management (no public register)
    path('auth/admin/create/', AdminCreateUserView.as_view()),
    path('auth/admin/promote/<int:user_id>/', PromoteDemoteUserView.as_view()),
    path('auth/me/', CurrentUserView.as_view()),

    path('employees/', EmployeeListView.as_view()),
    path('employees/<int:user_id>/tracking/', EmployeeTrackingView.as_view()),
]
