-- New users receive 50 manga tokens on signup.
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
