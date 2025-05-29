from django.db import models

# Create your models here.
from django.db import models

class Document(models.Model):
    filepath = models.CharField(max_length=255, blank=True)
    file = models.FileField(upload_to='uploads/')
    json_data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"Document {self.id}"
