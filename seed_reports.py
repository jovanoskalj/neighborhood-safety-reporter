# seed_reports.py
# Стави го во root на проектот (до manage.py)
# Пушти со: python manage.py shell < seed_reports.py

# seed_reports.py

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "neighborhood_safety_reporter.settings")  # ⚠️ види подолу
django.setup()

from django.contrib.auth.models import User
from reports.models import Report

# ── Креирај test user ако не постои ──────────────────────────────────────────
user, created = User.objects.get_or_create(
    username='test_citizen',
    defaults={'email': 'test@test.com', 'first_name': 'Тест', 'last_name': 'Граѓанин'}
)
if created:
    user.set_password('test1234')
    user.save()
    print("✔ Креиран test_citizen корисник")
else:
    print("✔ test_citizen веќе постои")

# ── Бриши стари seed пријави (опционално) ────────────────────────────────────
old = Report.objects.filter(citizen=user)
count = old.count()
old.delete()
print(f"✔ Избришани {count} стари seed пријави")

# ── Податоци ─────────────────────────────────────────────────────────────────
reports_data = [
    # Скопје — Центар
    dict(description="Скршена улична ламба на бул. Партизански Одреди, темно е навечер и е опасно за пешаците",
         latitude=41.9981, longitude=21.4254,
         category="infrastructure", priority="urgent", status="new",
         sector="infrastructure", opshtina="centar"),

    dict(description="Дупка на патот кај križišteто на ул. Македонија и ул. Димитрие Чуповски",
         latitude=41.9965, longitude=21.4312,
         category="infrastructure", priority="normal", status="in_progress",
         sector="infrastructure", opshtina="centar"),

    dict(description="Расипан водовод — вода тече по улицата три дена, губење на вода",
         latitude=41.9972, longitude=21.4198,
         category="utilities", priority="urgent", status="new",
         sector="utilities", opshtina="centar"),

    # Скопје — Карпош
    dict(description="Графити на фасадата на основното училиште Браќа Миладиновци",
         latitude=41.9876, longitude=21.3954,
         category="safety", priority="low", status="resolved",
         sector="safety", opshtina="karpos"),

    dict(description="Нелегална депонија со градежен шут кај ул. Лерински, загадување на животната средина",
         latitude=41.9901, longitude=21.3821,
         category="health", priority="normal", status="new",
         sector="health", opshtina="karpos"),

    # Скопје — Аеродром
    dict(description="Поплава во подземна гаража на ул. Битолска 200 по дождот",
         latitude=41.9734, longitude=21.4456,
         category="infrastructure", priority="urgent", status="in_progress",
         sector="infrastructure", opshtina="aerodrom"),

    dict(description="Оштетена сообраќајна табела — знакот е свртен во погрешна насока",
         latitude=41.9712, longitude=21.4389,
         category="infrastructure", priority="low", status="unclassified",
         sector="infrastructure", opshtina="aerodrom"),

    # Скопје — Гази Баба
    dict(description="Бучава од градилиште во забранети часови (после 22:00), жителите не можат да спијат",
         latitude=42.0134, longitude=21.4678,
         category="safety", priority="normal", status="new",
         sector="safety", opshtina="gazi_baba"),

    dict(description="Скршена клупа во паркот кај ул. Кедрова 12, опасна за деца",
         latitude=42.0098, longitude=21.4612,
         category="infrastructure", priority="low", status="new",
         sector="infrastructure", opshtina="gazi_baba"),

    # Скопје — Кисела Вода
    dict(description="Графити на влезот на зградата на ул. Бреза 88",
         latitude=41.9645, longitude=21.4523,
         category="safety", priority="normal", status="in_progress",
         sector="safety", opshtina="kisela_voda"),

    dict(description="Нема осветлување во паркот Градски зид, несигурно навечер",
         latitude=41.9678, longitude=21.4489,
         category="infrastructure", priority="urgent", status="new",
         sector="infrastructure", opshtina="kisela_voda"),

    # Струмица
    dict(description="Оштетен тротоар на главната улица во Струмица, опасност за постари лица",
         latitude=41.4378, longitude=22.6432,
         category="infrastructure", priority="normal", status="new",
         sector="infrastructure", opshtina="strumica"),

    dict(description="Контејнерите за смет не се празнат редовно, лош мирис во квартот",
         latitude=41.4412, longitude=22.6389,
         category="health", priority="urgent", status="in_progress",
         sector="health", opshtina="strumica"),

    dict(description="Уличното осветлување на ул. Маршал Тито не работи повеќе од недела",
         latitude=41.4356, longitude=22.6478,
         category="infrastructure", priority="normal", status="resolved",
         sector="infrastructure", opshtina="strumica"),

    # Охрид
    dict(description="Оштетена ограда кај Охридското Езеро, туристите се во опасност",
         latitude=41.1231, longitude=20.8016,
         category="safety", priority="urgent", status="new",
         sector="safety", opshtina="ohrid"),

    dict(description="Нелегално паркирање пред болницата — блокиран пристап за амбуланти",
         latitude=41.1189, longitude=20.7998,
         category="safety", priority="urgent", status="in_progress",
         sector="safety", opshtina="ohrid"),

    # Битола
    dict(description="Расипан семафор на главното крстосување, хаос во сообраќајот",
         latitude=41.0297, longitude=21.3294,
         category="infrastructure", priority="urgent", status="new",
         sector="infrastructure", opshtina="bitola"),

    dict(description="Дива депонија на влезот на градот кај Битола, ургентно чистење потребно",
         latitude=41.0334, longitude=21.3412,
         category="health", priority="normal", status="unclassified",
         sector="health", opshtina="bitola"),

    # Куманово
    dict(description="Течење на гас кај ул. Свети Климент Охридски, ургентна ситуација",
         latitude=42.1322, longitude=21.7144,
         category="utilities", priority="urgent", status="in_progress",
         sector="utilities", opshtina="kumanovo"),

    # Тетово
    dict(description="Оштетен мост на реката Пена, потребна итна проверка на безбедноста",
         latitude=42.0104, longitude=20.9714,
         category="infrastructure", priority="urgent", status="new",
         sector="infrastructure", opshtina="tetovo"),
]

# ── Креирај ги пријавите ──────────────────────────────────────────────────────
created_reports = []
for data in reports_data:
    r = Report.objects.create(citizen=user, **data)
    created_reports.append(r)

print(f"\n✔ Креирани {len(created_reports)} тест пријави\n")
print("─" * 55)
print(f"{'ID':<6} {'Општина':<15} {'Приоритет':<10} {'Статус'}")
print("─" * 55)
for r in created_reports:
    print(f"PRJ-{r.id:<3} {r.opshtina:<15} {r.priority:<10} {r.status}")
print("─" * 55)
print("\n✅ Готово! Отвори http://localhost:8000/search/ за да ги видиш.")