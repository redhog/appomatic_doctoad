import django.db.models

class Auth(django.db.models.Model):
    class Meta:
        permissions = (("merge", "Can merge changes"),
                       ("close", "Can close changes"),)
