# Authorized Telegram Lookup

## Scope

The application checks public `t.me` metadata first. When public evidence is unavailable, the optional MTProto integration can resolve data that is visible to your own authenticated Telegram account.

This integration is deliberately read-only:

- It does not join groups or channels.
- It does not read or download messages.
- It does not enumerate contacts.
- It does not return phone numbers or Telegram access hashes.
- It previews a valid invite only when Telegram permits the authenticated account to do so.

It cannot bypass Telegram privacy settings or membership requirements.

## One-Time Setup

1. Sign in at `https://my.telegram.org` and create an application under **API development tools**.
2. Put the resulting values in `backend/.env` locally:

```env
TELEGRAM_MTPROTO_ENABLED=false
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=replace_with_your_api_hash
TELEGRAM_SESSION_PATH=./data/telegram_osint
TELEGRAM_MTPROTO_TIMEOUT_SECONDS=20
```

3. From the `backend` directory, install dependencies and authorize once:

```powershell
pip install -r requirements.txt
python -m backend.scripts.telegram_authorize
```

Telegram will ask for the account phone number, a one-time code, and the 2FA password when enabled. Complete these prompts only in your own terminal.

4. Change `TELEGRAM_MTPROTO_ENABLED=true` in `backend/.env` and restart the backend.

5. Use the same username-investigation endpoint for a public username:

```text
POST /api/v1/investigation/username
```

```json
{
  "username": "example_username",
  "platform": "telegram",
  "correlation_depth": 2
}
```

The response includes safe readiness information at
`platform_data.authorized_access_status`.

6. The same endpoint also accepts an invite link:

```json
{
  "username": "https://t.me/+validInviteHash",
  "platform": "telegram"
}
```

Invite previews are isolated. The backend redacts the invite hash and skips
cross-platform search, web dorking, databases, AI, reverse lookup, and report
generation so the hash is never fanned out to another provider.

## Session Security

The `.session` file is equivalent to a logged-in Telegram session. Anyone who obtains it can act as that account. The repository ignores `*.session` and `*.session-journal`, but the file must still be protected with operating-system permissions and must never be emailed, uploaded, or committed.

Revoke the session from an official Telegram client immediately if the file may have leaked.
