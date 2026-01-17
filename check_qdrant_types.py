from qdrant_client.http import models
print(dir(models.PayloadSchemaType))
try:
    print(f"DATETIME: {models.PayloadSchemaType.DATETIME}")
except Exception as e:
    print(f"Error accessing DATETIME: {e}")
