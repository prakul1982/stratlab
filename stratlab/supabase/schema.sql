-- StratLab database schema. Run in Supabase: SQL Editor > New query > paste > Run.

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  plan text not null default 'free' check (plan in ('free','basic','pro')),
  plan_status text,                         -- 'active', 'cancelled', 'halted', ...
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  razorpay_subscription_id text,
  pending_subscription_id text,
  live_trial_started_at timestamptz,
  alerts_enabled boolean not null default false,
  telegram_chat_id text,
  alert_email text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists profiles_sub_idx on public.profiles (razorpay_subscription_id);

create table if not exists public.usage_events (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null,                       -- 'backtest' | 'ai'
  created_at timestamptz not null default now()
);
create index if not exists usage_user_kind_time on public.usage_events (user_id, kind, created_at);

create table if not exists public.strategies (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  body jsonb not null,
  instrument_token bigint,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists strategies_user on public.strategies (user_id, updated_at desc);

create table if not exists public.live_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  strategy jsonb not null,
  instrument jsonb not null,
  status text not null default 'running' check (status in ('running','stopped')),
  state jsonb,
  stop_reason text,
  started_at timestamptz not null default now(),
  stopped_at timestamptz
);
create index if not exists live_user on public.live_sessions (user_id, started_at desc);
create index if not exists live_status on public.live_sessions (status);

create table if not exists public.live_orders (
  id bigserial primary key,
  session_id uuid not null references public.live_sessions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  side text not null check (side in ('buy','sell')),
  qty integer not null,
  price numeric not null,
  reason text,
  pnl numeric,
  candle_time text,
  ts timestamptz not null default now()
);
create index if not exists orders_session on public.live_orders (session_id, ts desc);

-- server-only key/value store (Kite access token). No policies = no client access.
create table if not exists public.app_settings (
  key text primary key,
  value text,
  updated_at timestamptz not null default now()
);

-- Option chains recorded every few minutes in market hours, for options backtesting later.
-- chain: one [strike, ce bid, ce ask, ce ltp, ce oi, pe bid, pe ask, pe ltp, pe oi] per strike. Server only.
create table if not exists public.option_snapshots (
  id bigserial primary key,
  taken_at timestamptz not null,
  exchange text not null,
  name text not null,
  expiry date not null,
  spot double precision,
  lot integer,
  chain jsonb not null
);
create index if not exists option_snapshots_lookup on public.option_snapshots (name, expiry, taken_at);

-- Create a profile row for every new sign-up
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email) on conflict (id) do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Row level security: the browser only ever talks to the FastAPI backend,
-- which uses the service-role key. Users may read their own rows; nothing else.
alter table public.profiles      enable row level security;
alter table public.usage_events  enable row level security;
alter table public.strategies    enable row level security;
alter table public.live_sessions enable row level security;
alter table public.live_orders   enable row level security;
alter table public.app_settings  enable row level security;
alter table public.option_snapshots enable row level security;

drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles for select using (auth.uid() = id);
drop policy if exists "own strategies" on public.strategies;
create policy "own strategies" on public.strategies for select using (auth.uid() = user_id);
drop policy if exists "own sessions" on public.live_sessions;
create policy "own sessions" on public.live_sessions for select using (auth.uid() = user_id);
drop policy if exists "own orders" on public.live_orders;
create policy "own orders" on public.live_orders for select using (auth.uid() = user_id);
