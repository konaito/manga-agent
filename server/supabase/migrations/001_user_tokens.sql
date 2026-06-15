-- Manga token balance per authenticated user.
create table if not exists public.user_tokens (
  user_id uuid primary key references auth.users(id) on delete cascade,
  balance integer not null default 0 check (balance >= 0),
  updated_at timestamptz not null default now()
);

create table if not exists public.token_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  delta integer not null,
  reason text,
  created_at timestamptz not null default now()
);

create index if not exists token_ledger_user_id_idx on public.token_ledger(user_id);

-- Auto-create welcome balance when a new user signs up.
create or replace function public.handle_new_user_tokens()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  welcome_amount constant integer := 50;
  inserted boolean := false;
begin
  insert into public.user_tokens (user_id, balance)
  values (new.id, welcome_amount)
  on conflict (user_id) do nothing
  returning true into inserted;

  if inserted then
    insert into public.token_ledger (user_id, delta, reason)
    values (new.id, welcome_amount, 'signup_grant');
  end if;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created_tokens on auth.users;
create trigger on_auth_user_created_tokens
  after insert on auth.users
  for each row execute function public.handle_new_user_tokens();

-- Atomic debit: returns new balance or null if insufficient funds.
create or replace function public.debit_manga_token(p_user_id uuid, p_reason text default 'generate')
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  new_balance integer;
begin
  update public.user_tokens
  set balance = balance - 1,
      updated_at = now()
  where user_id = p_user_id
    and balance >= 1
  returning balance into new_balance;

  if not found then
    return null;
  end if;

  insert into public.token_ledger (user_id, delta, reason)
  values (p_user_id, -1, p_reason);

  return new_balance;
end;
$$;

-- Credit tokens (admin / refund).
create or replace function public.credit_manga_tokens(
  p_user_id uuid,
  p_amount integer,
  p_reason text default 'credit'
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  new_balance integer;
begin
  if p_amount <= 0 then
    raise exception 'amount must be positive';
  end if;

  insert into public.user_tokens (user_id, balance)
  values (p_user_id, p_amount)
  on conflict (user_id) do update
    set balance = public.user_tokens.balance + excluded.balance,
        updated_at = now()
  returning balance into new_balance;

  insert into public.token_ledger (user_id, delta, reason)
  values (p_user_id, p_amount, p_reason);

  return new_balance;
end;
$$;

alter table public.user_tokens enable row level security;
alter table public.token_ledger enable row level security;

-- Users can read their own balance; writes go through service role / RPC.
create policy "Users read own token balance"
  on public.user_tokens for select
  using (auth.uid() = user_id);

create policy "Users read own token ledger"
  on public.token_ledger for select
  using (auth.uid() = user_id);
