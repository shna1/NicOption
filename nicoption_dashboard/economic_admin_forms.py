from __future__ import annotations

from django import forms

from .models import DataSource, EconomicIndicator, IndicatorObservation


class IndicatorChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: EconomicIndicator) -> str:
        unit = f" — {obj.unit}" if obj.unit else ""
        return f"{obj.code} · {obj.name_fa}{unit}"


class SourceChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: DataSource) -> str:
        organization = f" · {obj.organization}" if obj.organization else ""
        return f"{obj.name}{organization}"


class ManualEconomicObservationForm(forms.Form):
    indicator = IndicatorChoiceField(
        queryset=EconomicIndicator.objects.none(),
        label="شاخص اقتصادی",
        empty_label="یک شاخص را انتخاب کنید",
    )
    source = SourceChoiceField(
        queryset=DataSource.objects.none(),
        label="منبع اصلی داده",
        empty_label="یک منبع را انتخاب کنید",
    )
    period_date = forms.DateField(
        label="تاریخ دوره",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="تاریخ میلادی و با قالب YYYY-MM-DD وارد شود.",
    )
    value = forms.CharField(
        label="مقدار",
        max_length=80,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "dir": "ltr"}),
        help_text="اعداد فارسی و جداکننده هزارگان نیز پذیرفته می‌شوند.",
    )
    published_at = forms.DateTimeField(
        label="زمان انتشار",
        required=False,
        input_formats=("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"),
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    status = forms.ChoiceField(
        label="وضعیت داده",
        choices=IndicatorObservation.Status.choices,
        initial=IndicatorObservation.Status.PUBLISHED,
    )
    source_url = forms.URLField(
        label="نشانی صفحه منبع",
        required=False,
        widget=forms.URLInput(attrs={"dir": "ltr", "placeholder": "https://…"}),
    )
    external_id = forms.CharField(
        label="شناسه منبع",
        required=False,
        max_length=180,
        widget=forms.TextInput(attrs={"dir": "ltr"}),
        help_text="در صورت وجود، شناسه ردیف یا انتشار در منبع اصلی.",
    )
    notes = forms.CharField(
        label="یادداشت",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["indicator"].queryset = EconomicIndicator.objects.filter(
            is_active=True
        ).order_by("code")
        self.fields["source"].queryset = DataSource.objects.filter(
            is_active=True
        ).order_by("name")
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("id", f"id_manual_{name}")

    def as_import_row(self) -> dict[str, str]:
        indicator = self.cleaned_data["indicator"]
        published_at = self.cleaned_data.get("published_at")
        return {
            "indicator_code": indicator.code,
            "period_date": self.cleaned_data["period_date"].isoformat(),
            "value": self.cleaned_data["value"],
            "unit": indicator.unit,
            "published_at": published_at.isoformat() if published_at else "",
            "original_source": self.cleaned_data["source"].name,
            "source_url": self.cleaned_data.get("source_url") or "",
            "status": self.cleaned_data["status"],
            "revision": "",
            "notes": self.cleaned_data.get("notes") or "",
            "external_id": self.cleaned_data.get("external_id") or "",
        }


class EconomicCSVUploadForm(forms.Form):
    file = forms.FileField(
        label="فایل CSV",
        help_text="UTF-8، حداکثر ۱ مگابایت و ۵٬۰۰۰ ردیف.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )
    strict = forms.BooleanField(
        label="در صورت وجود هر خطا، هیچ ردیفی ثبت نشود",
        required=False,
        initial=True,
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded.size > 1024 * 1024:
            raise forms.ValidationError("حجم فایل باید حداکثر ۱ مگابایت باشد.")
        if uploaded.name and not uploaded.name.lower().endswith(".csv"):
            raise forms.ValidationError("فقط فایل با پسوند CSV پذیرفته می‌شود.")
        return uploaded
