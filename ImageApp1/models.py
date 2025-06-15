from django.db import models

# Create your models here.
from django.db import models

# class Document(models.Model):
#     filepath = models.CharField(max_length=255, blank=True)
#     file = models.FileField(upload_to='uploads/')
#     json_data = models.JSONField(blank=True, null=True)

#     def __str__(self):
#         return f"Document {self.id}"



from django.db import models
from django.conf import settings
from django.utils import timezone

class Document(models.Model):
    userid = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    filepath = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to='uploads/')
    json_data = models.JSONField(blank=True, null=True)
    entry_date = models.DateField(default=timezone.now)

    def __str__(self):
        return f"Document {self.id} for {self.user.username}"

