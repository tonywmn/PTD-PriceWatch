# PTD-PriceWatch
Mobile PWA for validated price and availability monitoring.

## Architecture
- GitHub Pages: PWA dashboard
- GitHub Actions: scans and tests
- Supabase: configuration, status, history, push subscriptions
- Native Web Push: iOS Home Screen app

## One-time setup
1. Run `supabase/migrations/003_endversion.sql` in Supabase SQL Editor.
2. Add GitHub secrets: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`.
3. Replace `__VAPID_PUBLIC_KEY__` in `config.js` with the public VAPID key.
4. In GitHub Settings > Pages, set Source to GitHub Actions.
5. In Supabase Authentication > URL Configuration, set Site URL and Redirect URL to the GitHub Pages URL.
6. Run Quality Gate, then Price Scan manually once.
7. Open the Pages URL on iPhone, Add to Home Screen, open the installed app, and enable notifications.

## Safety design
- Fail closed: unclear product, price or availability never triggers an alert.
- Explicit sold-out messages override cart text.
- The last confirmed price is not presented as a current confirmed offer after a failed scan.
- No CAPTCHA bypass, proxy rotation, identity spoofing, or access-control circumvention.
