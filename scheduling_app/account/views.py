from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import RegistrationForm


@login_required
@user_passes_test(lambda u: u.role == 'ADMIN')
def registration(request):
    if request.method == 'POST':
        user_form = RegistrationForm(request.POST)
        if user_form.is_valid():
            new_user = user_form.save(commit=False)
            new_user.save()
            return render(
                request,
                'account/register_done.html',
                {'new_user':new_user}
            )
    else:
        user_form = RegistrationForm()
    return render(
        request,
        'account/register.html',
        {'user_form': user_form}
    )

