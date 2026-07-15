import os
from django.conf import settings


def version_context(request):
    """Add app version to template context."""
    version_file = os.path.join(settings.BASE_DIR, 'VERSION')
    version = '0.0.0'
    
    try:
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                version = f.read().strip()
    except Exception:
        pass
    
    return {
        'APP_VERSION': version
    }
