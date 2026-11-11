from django.contrib.admin.apps import AdminConfig


class ForumAdminConfig(AdminConfig):
    default_site = 'config.admin_site.ForumAdminSite'
