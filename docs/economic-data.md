# لایه داده شاخص‌های اقتصادی

درخواست وب `/api/economic-indicators` فقط PostgreSQL را می‌خواند و مستقیم به Google Sheets متصل نمی‌شود.

داده‌های آماده‌شده مرکز آمار از snapshot بازبینی‌شده داخل
`outputs/website_data_prepared` خوانده می‌شوند. فهرست با
`/api/statistical-center-indicators` به‌صورت server-side صفحه‌بندی می‌شود و
تاریخچه هر سری فقط از `/api/statistical-center-series?series_key=...` خوانده
می‌شود. فایل `website_series_index.json` امکان دسترسی مستقیم به بازه همان سری را
فراهم می‌کند و از خواندن کامل فایل تفصیلی ۱۷۳ مگابایتی در هر درخواست جلوگیری
می‌کند.

پس از بازتولید CSVهای آماده، نمایه را نیز بازسازی کنید:

```bash
python scripts/build_statistical_center_index.py
python scripts/verify_website_data.py
```

## مدل و grain

- `EconomicIndicator`: کاتالوگ و سیاست تازگی/دسترسی.
- `DataSource`: منبع اصلی آماری؛ Google Sheets منبع محسوب نمی‌شود.
- `IndicatorSource`: نگاشت زمان‌دار شاخص به منبع و اولویت منبع اصلی.
- `IndicatorObservation`: grain برابر `indicator + source + period_date + revision` است و فقط یک revision جاری برای هر دوره مجاز است.
- `IngestionRun` و `DataIssue`: سابقه اجرا و خطا/هشدار ایمن.
- `IndicatorRelease`: برنامه انتشار قابل اتکا.

مشاهده قبلی overwrite نمی‌شود. محتوای یکسان `unchanged` است؛ تغییر مقدار یا metadata مهم revision جدید می‌سازد و با `supersedes` به نسخه قبلی متصل می‌شود. صفر مقدار معتبر است و blank یا missing نیست.

## کاتالوگ اولیه

```bash
python manage.py seed_economic_indicators
```

فرمان metadata کاتالوگ را می‌سازد، idempotent است و observation ایجاد نمی‌کند. برای
چهار دارایی بازار، منبع تجمیع‌کننده PriceToDay و نگاشت اصلی آن نیز ساخته می‌شود.
برای `IR_TEDPIX` نیز منبع رسمی TSETMC با مسیر دریافت FinPy-TSE ساخته و به‌عنوان
منبع اصلی ثبت می‌شود؛ سایر منابع همچنان باید پیش از import در Admin تنظیم شوند.

## قرارداد Google Sheet و CSV

```text
indicator_code,period_date,value,unit,published_at,original_source,source_url,status,revision,notes,external_id
```

ستون‌های اجباری: `indicator_code`, `period_date`, `value`, `unit`, `original_source`.

نمونه صرفاً ساختاری و بدون مقدار اقتصادی واقعی:

```csv
indicator_code,period_date,value,unit,published_at,original_source,source_url,status,revision,notes,external_id
TEST_CODE,YYYY-MM-DD,DECIMAL_VALUE,CONFIGURED_UNIT,ISO_DATETIME,CONFIGURED_SOURCE,https://example.invalid/data,published,0,STRUCTURAL_EXAMPLE,ROW_ID
```

نام ستون‌ها trim و case-insensitive است. `period_date` باید ISO Gregorian و `published_at` باید ISO-8601 باشد. تاریخ مبهم یا شمسی بدون تبدیل صریح رد می‌شود. ارقام فارسی/عربی، جداکننده هزارگان و ممیز فارسی پشتیبانی می‌شوند؛ `NaN`، Infinity، URL نامعتبر، status نامعتبر، منبع ناشناخته و unit ناسازگار رد می‌شوند.

## Service Account و تنظیمات

1. در Google Cloud یک Service Account بسازید و Sheets API v4 را فعال کنید.
2. Sheet را فقط با ایمیل Service Account و نقش **Viewer** share کنید.
3. فایل JSON را خارج repository و با دسترسی محدود نگه دارید.
4. متغیرهای `ECONOMIC_GOOGLE_SHEET_ID`، `ECONOMIC_GOOGLE_SHEET_RANGE`، `GOOGLE_SERVICE_ACCOUNT_FILE`، `ECONOMIC_GOOGLE_TIMEOUT_SECONDS` و `ECONOMIC_GOOGLE_RETRIES` را تنظیم کنید.

scope فقط `spreadsheets.readonly` است. Sheet ID، range و credential حدس زده نمی‌شوند و credential در log، issue یا metadata اجرای ingestion ذخیره نمی‌شود.

## اجرا

```bash
python manage.py sync_economic_google_sheet --dry-run
python manage.py import_economic_csv /path/to/observations.csv --dry-run
python manage.py sync_economic_google_sheet
python manage.py import_economic_csv /path/to/observations.csv
python manage.py sync_economic_google_sheet --indicator IR_CPI --strict
python manage.py seed_economic_indicators
python manage.py sync_economic_pricetoday --strict
python manage.py sync_economic_finpy_tse --strict
python manage.py check_economic_data_freshness
```

## بروزرسانی از پنل مدیریت

مدیر کل می‌تواند از مسیر «Admin ← اجرای ورود داده ← بروزرسانی داده‌های اقتصادی»
یک مقدار را دستی وارد کند یا فایل CSV بارگذاری کند. هر دو مسیر ابتدا dry-run
می‌شوند و تعداد ردیف‌های جدید، اصلاح‌شده، بدون تغییر و ردشده را نمایش می‌دهند.
ثبت نهایی فقط در مرحله دوم انجام می‌شود؛ پیش‌نمایش به نشست همان مدیر متصل است و
پس از ۳۰ دقیقه منقضی می‌شود.

ورود دستی واحد را از کاتالوگ شاخص می‌خواند. CSV حداکثر ۱ مگابایت و ۵٬۰۰۰ ردیف
دارد و در حالت پیش‌فرض strict است. دسترسی پنل فقط برای `is_superuser` فعال است و
کاربر ثبت‌کننده در `IngestionRun.created_by` نگهداری می‌شود.

`sync_economic_pricetoday` قیمت دلار بازار آزاد، سکه بهار آزادی، طلای ۱۸ عیار و
تتر را از PriceToDay دریافت می‌کند. تاریخ داده روزانه ابتدا به تقویم هجری شمسی
تبدیل می‌شود و پس از حذف تاریخ‌های تکراری، آخرین قیمت معتبر هر ماه شمسی انتخاب
می‌شود. سپس رشد ماهانه نسبت به ماه شمسی قبل و رشد سالانه نسبت به ماه مشابه سال
شمسی قبل محاسبه می‌شود. برای هر دارایی، کارت قیمت ماهانه و دو کارت
مستقل رشد درصدی ماهانه (MoM) و سالانه (YoY) ساخته می‌شود. بازه پیش‌فرض از ابتدای سال
قبل است تا محاسبه YoY ممکن باشد. شناسه صحیح طلای ۱۸ عیار `gold-18k` است؛
`coin-emami` سکه امامی است و برای طلا استفاده نمی‌شود. ماه جاری تا پیش از پایان
ماه با وضعیت مقدماتی ذخیره می‌شود.

`sync_economic_finpy_tse` سابقه روزانه شاخص کل را با تابع `Get_CWI_History`
کتابخانه FinPy-TSE از TSETMC دریافت می‌کند و آخرین مقدار معتبر هر ماه شمسی را
به‌عنوان شاخص ماهانه ذخیره می‌کند. همانند دلار، برای شاخص کل نیز دو کارت مستقل
رشد ماهانه (`IR_TEDPIX_MOM_CHANGE`) و رشد سالانه
(`IR_TEDPIX_YOY_CHANGE`) با تطبیق دقیق ماه شمسی ساخته می‌شود. بازه پیش‌فرض شش
سال تقویمی اخیر است تا نمودار پنج‌ساله و دوره مرجع رشد سالانه پوشش داده شوند.

تورم مصرف‌کننده، رشد پایه پولی و رشد نقدینگی برای نرخ سالانه و ماهانه کارت‌های
مستقل دارند: نرخ سالانه `YoY = ((مقدار ماه جاری / مقدار ماه مشابه سال قبل) - 1) *
100` و نرخ ماهانه `MoM = ((مقدار ماه جاری / مقدار ماه قبل) - 1) * 100`. مقدار،
نمودار و خروجی CSV هر کارت فقط به نرخ درج‌شده در عنوان همان کارت مربوط است. کارت
`IR_CPI` همچنان شاخص خام را مستقل نمایش می‌دهد.
محاسبه فقط با تطبیق دقیق دوره انجام می‌شود؛ اگر دوره مرجع موجود نباشد یا مقدار آن
صفر باشد، نرخ مربوط نمایش داده نمی‌شود.

در non-strict ردیف‌های سالم وارد و اجرا `partial` می‌شود. در `--strict` با هر error هیچ observation نوشته نمی‌شود و exit code غیرصفر است. lock دیتابیس PostgreSQL اجرای هم‌زمان را مهار می‌کند. بررسی تازگی issueهای باز تکراری نمی‌سازد.

## دسترسی API

API فقط current revisionها را می‌خواند، series را صعودی مرتب و provenance را از `DataSource` برمی‌گرداند. پنج سال اخیر سقف عمومی backend است. چون entitlement مستقل وجود ندارد، `range=all` برای همه کاربران حتی staff با `full_history_subscription_required` رد می‌شود؛ permission بازار اشتراک کامل نیست.

## rollback عملیاتی

1. اجرای مشکل‌دار و issueها را در Admin پیدا کنید.
2. منبع یا CSV را اصلاح کنید.
3. observation تاریخی را در Admin ویرایش یا حذف نکنید؛ Admin آن را read-only نگه می‌دارد.
4. همان دوره را با مقدار درست دوباره import کنید تا revision جدید ساخته شود.
5. rollback schema فقط با backup تأییدشده PostgreSQL و migration برنامه‌ریزی‌شده انجام شود.

فرمان پیشنهادی production، بدون اجرای deploy یا timer:

```bash
cd /opt/nicoption
docker compose -f compose.production.yml exec -T web \
  python manage.py sync_economic_google_sheet
```

همین command برای systemd timer مناسب است؛ Celery، Redis یا سرویس جدید لازم نیست.
## داده‌های بانک مرکزی با cbi-mcp

صفحه `/central-bank` دو لایه داده را جداگانه نمایش می‌دهد: تاریخچه شاخص‌های پولی
بسته‌بندی‌شده در پروژه و تصویر تازه داده‌های عمومی بانک مرکزی که فقط از سرور
خواندنی [`cbi-mcp`](https://github.com/sepehr071/cbi-mcp) دریافت می‌شود.

```bash
python manage.py sync_cbi_mcp
```

این فرمان نرخ‌های رسمی منتخب ارز و تاریخچه دلار، تورم، نرخ‌های سیاستی و بازار
بین‌بانکی، نقدینگی، حراج اوراق دولتی، عملیات بازار باز، اخبار، چهار خانواده انتشار
و اولین برگه از جدول‌های ماهانه پولی، تراز پرداخت‌ها، مالی دولت و بازار سرمایه را
از طریق MCP می‌خواند. نتیجه به‌صورت snapshot در پایگاه داده ذخیره می‌شود؛ درخواست
صفحه کاربر هیچ فراخوانی زنده‌ای به بانک مرکزی انجام نمی‌دهد. در استقرار Docker،
سرویس `cbi-sync` هر شش ساعت این فرمان را اجرا می‌کند. فاصله با
`CBI_MCP_SYNC_INTERVAL_SECONDS` قابل تنظیم است.

همگام‌سازی برای چهار برگه عددی منتخب، ماه‌های گذشته را نیز جداگانه از MCP می‌خواند
و ردیف‌های Excel را به سری زمانی تبدیل می‌کند: «متغیرهای عمده» پول و اعتبار، «نرخ
دلار» تراز پرداخت‌ها، «جدول گزیده ۱» مالی دولت و «شاخص فعالیت» بازار سرمایه. صفحه
بانک مرکزی خود اعداد، نمودار، آخرین مقدار، تغییر دوره‌ای و جدول تاریخچه را نمایش
می‌دهد؛ پیوند فایل فقط برای ردیابی منبع باقی می‌ماند. حداکثر ۱۲ دوره معتبر از ۱۸
ماه اخیر نگهداری می‌شود و اگر ناشر برای حوزه‌ای ماه‌های کمتری منتشر کرده باشد، همان
تعداد واقعی بدون پرکردن یا برآورد نمایش داده می‌شود.

`cbi-mcp` یک adapter غیررسمی است و داده را از صفحات عمومی `cbi.ir` می‌خواند.
نرخ ارز این بخش نرخ رسمی بانک مرکزی است، نه نرخ بازار آزاد. این داده‌ها با آمار
مرکز آمار ایران و adapter مستقل `amar` یکی نیستند و در رابط با منشأ جدا نمایش داده
می‌شوند.

## آمارهای گسترده مرکز آمار با amar-mcp

صفحه `/statistical-center` علاوه بر فهرست قیمت و تورم قبلی، دو مجموعهٔ جدا دارد:
«آمارهای جدید» برای بازار کار، جمعیت، خانوار، حساب‌های ملی، مالی دولت، تجارت،
انرژی، صنعت و کشاورزی؛ و «داده‌های تکمیلی» برای پول و اعتبار، بازار سرمایه و
مسکن. داده‌ها فقط از ابزار خواندنی
[`amar-mcp`](https://github.com/sepehr071/amar-mcp) دریافت می‌شوند.

```bash
python manage.py sync_amar_mcp --year 1405
```

فرمان بالا نماگرهای آمادهٔ بازار کار، تولید ناخالص داخلی، جمعیت و تقویم انتشار را
همراه همهٔ جدول‌های دفترچهٔ شاخص‌های کلان در یک snapshot پایگاه داده ذخیره می‌کند.
درخواست کاربر هرگز اتصال زنده به `amar.org.ir` ایجاد نمی‌کند. در استقرار Docker،
سرویس `amar-sync` هر شش ساعت فرمان را اجرا می‌کند و فاصله با
`AMAR_MCP_SYNC_INTERVAL_SECONDS` قابل تنظیم است. نام سازمان اصلی هر جدول در رابط
حفظ می‌شود و اعتبار adapter به سپهر رادمرد نمایش داده می‌شود.

