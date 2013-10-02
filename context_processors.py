from django.conf import settings

def processors(request):
    return {
        'site_url': request.build_absolute_uri('/')[:-1],
        'settings': settings,
        'request': request
    }
