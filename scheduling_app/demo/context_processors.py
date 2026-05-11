_DEMO_USERNAMES = frozenset(['demo_employee', 'demo_scheduler', 'demo_admin'])


def demo_context(request):
    if request.user.is_authenticated and request.user.username in _DEMO_USERNAMES:
        return {
            'is_demo': True,
            'demo_user_name': request.user.get_full_name(),
            'demo_role_display': request.user.get_role_display(),
        }
    return {'is_demo': False}
