-- Схема для ИИ-помощника оценщика.
-- Применить: Supabase → SQL Editor → вставить и выполнить
-- (или `supabase db push`, если используете Supabase CLI).

-- Отчёты. Полный отчёт лежит в payload (JSON), ключевые поля вынесены
-- в колонки для фильтров и статистики в веб-панели.
create table if not exists public.reports (
    id                  text primary key,
    vin_or_plate        text not null,
    payload             jsonb not null,
    needs_manual_review boolean not null default true,
    approved_price      bigint,
    approved_by         bigint,           -- Telegram ID старшего оценщика
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create index if not exists reports_vin_idx on public.reports (vin_or_plate);
create index if not exists reports_created_idx on public.reports (created_at desc);

-- Итог сделки: за сколько машину реально продали и что всплыло потом.
-- Главный источник для калибровки и для отчёта «ИИ против реальности».
create table if not exists public.outcomes (
    report_id        text primary key references public.reports (id) on delete cascade,
    sold_price       bigint,
    sold_at          date,
    missed_defects   text,                -- что пропустили (и ИИ, и человек)
    comment          text,
    created_at       timestamptz not null default now()
);

-- Цены аналогов, если ведёте их в базе, а не в CSV
create table if not exists public.comparables (
    id          bigint generated always as identity primary key,
    make        text not null,
    model       text not null,
    year        int not null,
    mileage_km  int not null,
    price_kzt   bigint not null,
    source      text,
    listed_at   date,
    created_at  timestamptz not null default now()
);

create index if not exists comparables_model_idx on public.comparables (lower(make), lower(model), year);

-- Сводка для веб-панели (Appsmith/ToolJet): оценка против реального результата
-- security_invoker: view подчиняется RLS таблиц, иначе обходил бы защиту
create or replace view public.report_accuracy with (security_invoker = true) as
select
    r.id,
    r.vin_or_plate,
    r.created_at,
    (r.payload -> 'car' ->> 'make') || ' ' || (r.payload -> 'car' ->> 'model') as car,
    (r.payload -> 'estimate' ->> 'offer_low')::bigint  as ai_offer_low,
    (r.payload -> 'estimate' ->> 'offer_high')::bigint as ai_offer_high,
    r.approved_price,
    o.sold_price,
    o.sold_price - r.approved_price as margin,
    jsonb_array_length(coalesce(r.payload -> 'defects', '[]'::jsonb)) as defects_found,
    o.missed_defects
from public.reports r
left join public.outcomes o on o.report_id = r.id;

-- updated_at автоматически
create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end $$;

drop trigger if exists reports_touch on public.reports;
create trigger reports_touch before update on public.reports
for each row execute function public.touch_updated_at();

-- Безопасность: RLS включён, политик для anon/authenticated нет.
-- Бот работает через service_role (обходит RLS). Для веб-панели добавьте
-- отдельные политики под роли руководства, когда настроите Auth.
alter table public.reports enable row level security;
alter table public.outcomes enable row level security;
alter table public.comparables enable row level security;

-- Приватный бакет для фото (номера, документы, люди — персональные данные)
insert into storage.buckets (id, name, public)
values ('car-photos', 'car-photos', false)
on conflict (id) do nothing;
