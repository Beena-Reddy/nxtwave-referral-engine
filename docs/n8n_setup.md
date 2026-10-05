# Connecting n8n (optional)

Every registration is POSTed as JSON to `N8N_WEBHOOK_URL` (in a background thread, so a failing
automation never blocks a sign-up). Payload:

```json
{"event":"registration","name":"...","email":"...","phone":"9876543210","college":"...",
 "source":"ambassador","ref_code":"VISH-AB12","referred_by":null,
 "personal_link":"https://.../r/VISH-AB12","workshop":"...","date":"...","created_at":"..."}
```

Suggested workflow:
1. **Webhook** node (POST) → copy its Production URL into `.env` as `N8N_WEBHOOK_URL`.
2. **Google Sheets** → Append row (backup + shareable with the team).
3. **Gmail / Email** → welcome mail with the joining link and their `personal_link`.
4. **IF** `referred_by` is set → notify the referrer ("Your friend just joined, 2 more for the certificate").
5. **Wait** until T-24h / T-1h → reminder email or WhatsApp (WhatsApp Business Cloud API node).

Test locally: run n8n (`npx n8n`), use the webhook's *Test URL*, register on the site, and watch the execution.
