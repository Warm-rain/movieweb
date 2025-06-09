from django import forms
from .models import MovieRating


class MovieRatingForm(forms.ModelForm):
    class Meta:
        model = MovieRating
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(
                choices=[(i, f'{i} 星') for i in range(1, 6)],
                attrs={'class': 'form-select'}
            ),
            'comment': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': '请输入您的评论...'
                }
            ),
        }
        labels = {
            'rating': '评分',
            'comment': '评论',
        } 