# Authorized Telegram Lookup

## Scope

The application checks public `t.me` metadata first. When that public lookup is
unavailable or inconclusive, the optional MTProto path can resolve information
visible to the operator's own authenticated Telegram account.

For a normal username, Telegram collection runs when Telegram is the selected
primary platform or when the public profile probe selects it as a candidate. It
does not trigger an unconditional all-platform Actor fan-out. Paid social
collection remains bounded by `INVESTIGATION_MAX_SOCIAL_PLATFORMS`; Telegram
itself does not consume a paid-social provider unit.

Normal Telegram collection is read-only:

- It does not join groups or channels.
- It does not read or download the investigated user's, group's, or channel's
  message history.
- It does not enumerate contacts.
- It does not return phone numbers or Telegram access hashes.
- It previews a valid invite only when Telegram permits the authenticated
  account to do so.

It cannot bypass Telegram privacy settings, membership requirements, or flood
controls.

## Third-Party Bot Queries

Queries to third-party Telegram bots are disabled by default:

```env
TELEGRAM_OSINT_BOT_QUERIES_ENABLED=false
```

Changing this setting to `true` sends the investigated username to the built-in
third-party bot list. For each queried bot, the service fetches at most five
recent bot-dialog messages and accepts only a newer response tied to the exact
target username. That is an active external disclosure, not passive profile
resolution. Enable it only after an explicit case-level privacy and authorization
decision. The response separately reports attempted queries, sent messages,
bot-dialog messages fetched, accepted responses, and whether target-chat history
was accessed (always false).

Invite-link previews never use third-party bot queries.

## One-Time MTProto Setup

1. Sign in at `https://my.telegram.org` and create an application under
   **API development tools**.
2. Put the resulting values in `backend/.env` locally, leaving the integration
   disabled until authorization is complete:

   ```env
   TELEGRAM_MTPROTO_ENABLED=false
   TELEGRAM_API_ID=123456
   TELEGRAM_API_HASH=replace_with_your_api_hash
   TELEGRAM_SESSION_PATH=./data/telegram_osint
   TELEGRAM_MTPROTO_TIMEOUT_SECONDS=20
   TELEGRAM_OSINT_BOT_QUERIES_ENABLED=false
   ```

3. From the `backend` directory, install dependencies and authorize once:

   ```powershell
   pip install -r requirements.txt
   python -m backend.scripts.telegram_authorize
   ```

   Telegram will ask for the account phone number, a one-time code, and the 2FA
   password when enabled. Complete these prompts only in your own terminal.

4. Change `TELEGRAM_MTPROTO_ENABLED=true` in `backend/.env` and restart the
   backend. Keep third-party bot queries false for normal operation.

## Username Lookup

Choosing Telegram makes it the primary platform:

```http
POST /api/v1/investigation/username
Content-Type: application/json

{
  "username": "example_username",
  "platform": "telegram",
  "correlation_depth": 2
}
```

The response includes safe authorized-session readiness information and the
Telegram collection result in the provider-neutral social envelope. Readiness
means local dependency, credential, and session-file state; it does not prove
that Telegram will permit a particular lookup.

## Invite-Link Privacy Guard

The same endpoint accepts a Telegram invite link only when `platform` is
`telegram`:

```json
{
  "username": "https://t.me/+validInviteHash",
  "platform": "telegram"
}
```

Invite previews are isolated. The backend redacts the invite hash, bypasses the
investigation cache, and skips cross-platform probes, paid social Actors,
search, databases, AI, reverse lookup, report generation, persistent history,
and third-party bot queries. The aggregate response identifies this path with
`apify_social_results.mode: "privacy_guard"`.

## Session Security

The `.session` file is equivalent to a logged-in Telegram session. Anyone who
obtains it can act as that account. The repository ignores `*.session` and
`*.session-journal`, but the file must still be protected with operating-system
permissions and must never be emailed, uploaded, or committed.

Revoke the session from an official Telegram client immediately if the file may
have leaked.
