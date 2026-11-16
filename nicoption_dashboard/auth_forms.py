from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import UserAccessProfile


DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username",)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = ""
        if commit:
            user.save()
            profile, _ = UserAccessProfile.objects.get_or_create(user=user)
            profile.email_verified_at = None
            profile.verification_email_sent_at = None
            profile.save(
                update_fields=(
                    "email_verified_at",
                    "verification_email_sent_at",
                    "updated_at",
                )
            )
        return user


class VerificationEmailForm(forms.Form):
    email = forms.EmailField(required=True)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        users = get_user_model().objects.filter(email__iexact=email)
        if self.user is not None:
            users = users.exclude(pk=self.user.pk)
        if users.exists():
            raise forms.ValidationError("این ایمیل قبلاً برای یک حساب ثبت شده است.")
        return email
