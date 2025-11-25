from django.urls import path
from .views import (
    StartAttendanceView, EndAttendanceView, ToggleBreakView, CurrentStatusView,
    DailyCSVExportView, CSVExportByDateView, SaveCSVToServerView,
    FlushUserDataView, FlushAllDataAdminView,
    RegisterView, AdminCreateUserView, EmployeeListView, EmployeeTrackingView,
    PromoteDemoteUserView
)

urlpatterns = [
    path('start/', StartAttendanceView.as_view()),
    path('end/', EndAttendanceView.as_view()),
    path('break/toggle/', ToggleBreakView.as_view()),
    path('status/', CurrentStatusView.as_view()),

    path('export/today/', DailyCSVExportView.as_view()),
    path('export/<int:year>/<int:month>/<int:day>/', CSVExportByDateView.as_view()),
    path('export/save/today/', SaveCSVToServerView.as_view()),
    path('export/save/<int:year>/<int:month>/<int:day>/', SaveCSVToServerView.as_view()),

    path('flush/', FlushUserDataView.as_view()),
    path('flush/all/', FlushAllDataAdminView.as_view()),

    # auth / admin
    path('auth/register/', RegisterView.as_view()),
    path('auth/admin/create/', AdminCreateUserView.as_view()),
    path('employees/', EmployeeListView.as_view()),
    path('employees/<int:user_id>/tracking/', EmployeeTrackingView.as_view()),
    path('auth/admin/promote/<int:user_id>/', PromoteDemoteUserView.as_view()),
]
