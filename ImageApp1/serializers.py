from rest_framework import serializers
from .models import Document


from rest_framework import serializers
from .models import Document

class DocumentSerializer(serializers.ModelSerializer):
    filename = serializers.SerializerMethodField()  # ✅ Custom field

    class Meta:
        model = Document
        fields = '__all__'  # or list all explicitly, including 'filename'

    def get_filename(self, obj):
        return obj.file.name.split('/')[-1] if obj.file else None
