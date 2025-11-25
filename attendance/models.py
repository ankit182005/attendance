from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Attendance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendances')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.start_time.isoformat()}"


class BreakInterval(models.Model):
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE, related_name='breaks')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Break({self.attendance.user.username}) {self.start_time.isoformat()}"
