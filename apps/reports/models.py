from django.utils import timezone
from django.contrib.auth.models import User
from django.db import models
from .validators import validate_image_content



class ReportCategory(models.Model):
    """Admin-managed report category option used in dashboard settings."""

    key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Sector(models.Model):
    """Admin-managed sector option used in dashboard settings."""

    key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


MUNICIPALITY_CHOICES = [
    ('aerodrom', 'Аеродром'),
    ('aracinovo', 'Арачиново'),
    ('berovo', 'Берово'),
    ('bitola', 'Битола'),
    ('bogdanci', 'Богданци'),
    ('bogovinje', 'Боговиње'),
    ('bosilovo', 'Босилово'),
    ('brvenica', 'Брвеница'),
    ('butel', 'Бутел'),
    ('valandovo', 'Валандово'),
    ('vasilevo', 'Василево'),
    ('veles', 'Велес'),
    ('vevchani', 'Вевчани'),
    ('vinica', 'Виница'),
    ('vrapchishte', 'Врапчиште'),
    ('gazi_baba', 'Гази Баба'),
    ('gevgelija', 'Гевгелија'),
    ('gjorche_petrov', 'Ѓорче Петров'),
    ('gostivar', 'Гостивар'),
    ('gradsko', 'Градско'),
    ('debar', 'Дебар'),
    ('debarca', 'Дебарца'),
    ('delchevo', 'Делчево'),
    ('demir_hisar', 'Демир Хисар'),
    ('demir_kapija', 'Демир Капија'),
    ('dojran', 'Дојран'),
    ('dolneni', 'Долнени'),
    ('zhelino', 'Желино'),
    ('zelenikovo', 'Зелениково'),
    ('zrnovci', 'Зрновци'),
    ('ilinden', 'Илинден'),
    ('jegunovce', 'Јегуновце'),
    ('kavadarci', 'Кавадарци'),
    ('karbinci', 'Карбинци'),
    ('karposh', 'Карпош'),
    ('kichevo', 'Кичево'),
    ('kisela_voda', 'Кисела Вода'),
    ('kochani', 'Кочани'),
    ('konche', 'Конче'),
    ('kratovo', 'Кратово'),
    ('kriva_palanka', 'Крива Паланка'),
    ('krivogashtani', 'Кривогаштани'),
    ('krushevo', 'Крушево'),
    ('kumanovo', 'Куманово'),
    ('lipkovo', 'Липково'),
    ('lozovo', 'Лозово'),
    ('makedonska_kamenica', 'Македонска Каменица'),
    ('makedonski_brod', 'Македонски Брод'),
    ('mavrovo_rostushe', 'Маврово и Ростуше'),
    ('mogila', 'Могила'),
    ('negotino', 'Неготино'),
    ('novaci', 'Новаци'),
    ('novo_selo', 'Ново Село'),
    ('ohrid', 'Охрид'),
    ('petrovec', 'Петровец'),
    ('pehchevo', 'Пехчево'),
    ('plasnica', 'Пласница'),
    ('prilep', 'Прилеп'),
    ('probishtip', 'Пробиштип'),
    ('radovish', 'Радовиш'),
    ('rankovce', 'Ранковце'),
    ('resen', 'Ресен'),
    ('rosoman', 'Росоман'),
    ('saraj', 'Сарај'),
    ('sveti_nikole', 'Свети Николе'),
    ('skopje', 'Град Скопје'),
    ('sopishte', 'Сопиште'),
    ('staro_nagorichane', 'Старо Нагоричане'),
    ('struga', 'Струга'),
    ('strumica', 'Струмица'),
    ('studenichani', 'Студеничани'),
    ('tearce', 'Теарце'),
    ('tetovo', 'Тетово'),
    ('centar', 'Центар'),
    ('centar_zhupa', 'Центар Жупа'),
    ('chair', 'Чаир'),
    ('chashka', 'Чашка'),
    ('cheshinovo_obleshevo', 'Чешиново-Облешево'),
    ('chucher_sandevo', 'Чучер-Сандево'),
    ('shtip', 'Штип'),
    ('shuto_orizari', 'Шуто Оризари'),
]

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

class AllObjectsManager(models.Manager):
    """Includes soft-deleted reports — use only in admin/restore contexts."""
    pass


class Report(models.Model):
    STATUS_CHOICES = [
        ("new", "Нова"),
        ("in_progress", "Во тек"),
        ("resolved", "Завршена"),
        ("unclassified", "Некласифицирана"),
        ("withdrawn", "Повлечена"),
    ]

    PRIORITY_CHOICES = [
        ("urgent", "Итен"),
        ("normal", "Нормален"),
        ("low", "Низок"),
    ]
    CATEGORY_CHOICES = [
        ("infrastructure", "Инфраструктура"),
        ("utilities", "Комунални услуги"),
        ("safety", "Безбедност"),
        ("health", "Здравство"),
        ("other", "Друго"),
    ]
    SECTOR_CHOICES = [
        ("infrastructure", "Инфраструктура"),
        ("utilities", "Комунални услуги"),
        ("safety", "Безбедност"),
        ("health", "Здравство"),
        ("admin", "Администрација"),
    ]

    citizen = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports')
    description = models.TextField()
    image = models.ImageField(upload_to='reports/', blank=True, null=True, validators=[validate_image_content])
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    municipality = models.CharField(max_length=100, choices=MUNICIPALITY_CHOICES, blank=True, default='')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new')
    sector = models.CharField(max_length=50, choices=SECTOR_CHOICES, default='admin')
    assigned_officer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_reports')
    internal_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    ai_processed = models.BooleanField(default=False)
    is_duplicate = models.BooleanField(default=False)
    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
    )  
    
    
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()  

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="report_status_idx"),
            models.Index(fields=["sector"], name="report_sector_idx"),
            models.Index(fields=["category"], name="report_category_idx"),
            models.Index(fields=["municipality"], name="report_municipality_idx"),
            models.Index(fields=["priority"], name="report_priority_idx"),
            models.Index(fields=["latitude"], name="report_latitude_idx"),
            models.Index(fields=["longitude"], name="report_longitude_idx"),
            models.Index(fields=["sector", "status"], name="report_sector_status_idx"),
            models.Index(fields=["is_duplicate"], name="report_is_duplicate_idx"),
        ]

    def __str__(self) -> str:
        return f"Report #{self.pk} ({self.status})"


    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])


class ReportStatusHistory(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at"]

    def __str__(self) -> str:
        return f"Report #{self.report_id}: {self.from_status or '-'} -> {self.to_status}"
