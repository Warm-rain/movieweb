from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.views import LoginView
from .forms import SignUpForm


class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    
    def form_valid(self, form):
        messages.success(self.request, f'欢迎回来，{form.get_user().username}！')
        return super().form_valid(form)


def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'欢迎，{user.username}！注册成功。')
            return redirect('movie_list')
    else:
        form = SignUpForm()
    
    return render(request, 'registration/signup.html', {'form': form}) 