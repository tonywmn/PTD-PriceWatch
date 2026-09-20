alter table product_sources add column if not exists next_check_at timestamptz;
create index if not exists idx_sources_next_check on product_sources(next_check_at) where active=true;
create index if not exists idx_history_source_time on price_history(source_id,checked_at desc);
create unique index if not exists idx_alert_source on alert_state(source_id);
-- Required for scanner upserts via secret key; RLS is bypassed only by the server-side secret.
-- Authenticated dashboard users may manage central settings.
create policy "Authenticated manage push" on push_subscriptions for all to authenticated using(true) with check(true);
-- Restrict central dashboard changes to the owner account.
drop policy if exists "Authenticated update products" on products;
drop policy if exists "Authenticated update providers" on providers;
drop policy if exists "Authenticated update sources" on product_sources;
drop policy if exists "Authenticated update settings" on app_settings;
create policy "Owner manage products" on products for all to authenticated using ((auth.jwt()->>'email')='tony.weimann@siemens.com') with check ((auth.jwt()->>'email')='tony.weimann@siemens.com');
create policy "Owner manage providers" on providers for all to authenticated using ((auth.jwt()->>'email')='tony.weimann@siemens.com') with check ((auth.jwt()->>'email')='tony.weimann@siemens.com');
create policy "Owner manage sources" on product_sources for all to authenticated using ((auth.jwt()->>'email')='tony.weimann@siemens.com') with check ((auth.jwt()->>'email')='tony.weimann@siemens.com');
create policy "Owner manage settings" on app_settings for all to authenticated using ((auth.jwt()->>'email')='tony.weimann@siemens.com') with check ((auth.jwt()->>'email')='tony.weimann@siemens.com');
