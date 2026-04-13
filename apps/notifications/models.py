from django.db import models

class Notification(models.Model):
    time = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=50)
    message = models.TextField()
    recipient = models.CharField(max_length=255)
    status = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.type} - {self.recipient} - {self.status}"