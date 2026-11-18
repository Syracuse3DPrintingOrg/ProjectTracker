# Administration

Running a shared SQ: users and roles, the Settings panes, backups, and what the tokens can and cannot do.

## Users and the three roles

SQ starts with no logins at all. Add the first user (an admin, required) under Settings, Users and Access, and the instance locks: from then on every page needs a login, an API key, or a device token. Boards and the Today list are shared by everyone; SQ is a household or small-team tracker, and roles decide who can change what, not who can see which board.

| Can they... | Admin | Member | Viewer |
|---|---|---|---|
| View boards, cards, calendar, and search | Yes | Yes | Yes |
| Create, edit, move, and delete cards and projects | Yes | Yes | No |
| Manage the Today list and comment on cards | Yes | Yes | No |
| Pop a registered display up on a TV (show and hide) | Yes | Yes | No |
| Change their own password | Yes | Yes | Yes |
| Settings, users, API keys, display configuration | Yes | No | No |
| Download backups and restore | Yes | No | No |

A few guardrails: SQ always keeps at least one active admin, so the last one cannot be demoted, disabled, or deleted, and you cannot delete yourself while logged in. Deleting a user keeps their cards; the cards just lose their assignee. A disabled user cannot log in but keeps their account for later.

## Accounts and passwords

Every signed-in user has an Account page for changing their password (current password required, minimum 4 characters). Changing a password signs that user out everywhere, including the session that made the change: session cookies carry a fragment of the password hash, so older sessions stop working the moment it changes. That is the fastest way to cut off a lost laptop. Sessions otherwise last 30 days.

Passwords are stored as salted PBKDF2 (SHA-256, 200,000 rounds). Accounts created before 0.12 used a simpler salted hash; those still verify, so nobody gets locked out by updating, and any password change moves the account onto PBKDF2. An even older install that used the single shared password gets that password migrated automatically into an `admin` account.

## Sign in with Pocket ID

SQ can sign people in with [Pocket ID](https://pocket-id.org), so they use a passkey instead of a password. Any OpenID Connect provider that sends a `groups` claim works the same way.

1. In Pocket ID, create an OIDC client for SQ with PKCE on. Its callback URL is your public SQ address followed by `/auth/oidc/callback`, for example `https://sq.example.com/auth/oidc/callback`.
2. In SQ, open Settings, Users and Access, and fill in the Pocket ID sign-in section: SQ's public address, the Pocket ID address, the client ID and the client secret. You can also set them with `TRACKER_PUBLIC_URL`, `TRACKER_OIDC_ISSUER`, `TRACKER_OIDC_CLIENT_ID` and `TRACKER_OIDC_CLIENT_SECRET`, or put the secret alone in `data/oidc_client_secret`.
3. Each person signs in the usual way once, opens their Account page on the public address, and presses **Link Pocket ID**. From then on the login page's **Sign in with Pocket ID** button takes them straight in.

The button only appears on the public address, because Pocket ID sends people back there. On any other address the login page points at the public one.

Roles follow Pocket ID's groups: anyone in the `admins` group is an admin in SQ, and an admin who leaves that group becomes a member the next time they sign in. If Pocket ID sends no groups at all, roles stay as they are. SQ never demotes its last admin.

### Pocket ID as the only way in

Once your own account is linked, the **Pocket ID is the only way in** switch appears under the sign-in settings. With it on, the password form disappears, passwords are refused, and sessions that started with a password end. Sessions from Pocket ID carry on.

If Pocket ID is ever down, admins can still get in at `/login/recovery` with their SQ password (the login page links to it). Members and viewers wait for Pocket ID to come back. API keys, the display token and the Claude Code connector are not affected by any of this.

## A tour of the Settings panes

Settings is a sidebar of panes, admin only once logins are on:

- **Overview**: stat tiles (projects, open cards, users, displays) plus health checks: is the data folder writable, is AI assist configured, are logins on. A red data-folder check is worth fixing before anything else, since everything lives there.
- **AI Assist**: provider, keys, model, and the Test button. Covered on the [AI features](ai-features.md) page.
- **General**: rename the tracker; the title shows in the header and on displays.
- **Users and Access**: user accounts and API keys, covered above and on the [Integrations](integrations.md) page.
- **Hardware**: the wall display registry, the display token, the tracker address handed to devices, and the Claude Code connector command.
- **Backup and Restore**: covered below.
- **Updates**: shows the version you are running and checks GitHub for the newest release. A tracker with no internet access just says it could not check, and that is fine; nothing else depends on the check. When an update is out, pull it:

```bash
docker pull ghcr.io/syracuse3dprintingorg/projecttracker:latest
docker compose up -d
```

Your data folder carries everything over. On Unraid, use Check for Updates on the container instead.

## Display and connector tokens

Two credentials exist for devices, so a wall screen or a dev machine never sees a login page:

- The **display token** authenticates wall displays once logins are on: displays call `/display`, `/kiosk`, and their data APIs with `?token=...` appended. Generate or remove it under Settings, Hardware; registered displays get URLs with the token already in place. Rotating it invalidates the old one, so re-point your screens after.
- The **connector token** authenticates the Claude Code connector's status reports, sent as an `X-Connector-Token` header. It is generated on demand and shown, inside the ready-made setup command, only to admins.

Treat both like passwords for a single narrow job, and rotate the display token if a screen or its URL wanders off.

## Backup and restore

Settings, Backup and Restore downloads one JSON file holding every project, column, and card (subtasks are cards too, so they ride along). Restoring replaces all projects, columns, and cards with the file's contents, so it asks for confirmation; backups from older versions that carried a separate subtasks list import cleanly.

Know what the JSON does **not** contain: user accounts and passwords, settings (including AI keys, the app title, and both device tokens), API keys, attachment files, and each card's comment and activity trail. The JSON is great for moving boards between instances or keeping a second copy of the work itself. For a complete backup, copy the whole data folder: `tracker.db`, `settings.json`, `secret_key`, and `attachments/` together are the entire instance.

## Security notes

- **Open until the first user.** With no users, SQ trusts the network completely, which suits a home LAN. Do not expose an open instance to the internet; add users first, and even then prefer keeping SQ on the LAN or behind your own access controls.
- **What locks when users exist.** Everything requires a session, an API key, or a device token, except the login page, the Pocket ID sign-in pages, the health check, static assets, and the display pages with a valid token.
- **What tokens can and cannot do.** The display token reads the Today list and can toggle a task done from the kiosk; that is its entire reach, with no access to boards, settings, or the rest of the API. The connector token can only post Claude Code status snapshots. API keys act as member or viewer, never admin, so they cannot touch users, settings, keys, display configuration, or backups. A leaked device credential is an annoyance, not a takeover.
- **Passwords and sessions.** The 4-character minimum is a floor for a household; use longer passwords for anything more exposed. Sessions are signed with a key stored at `data/secret_key` (overridable with `TRACKER_SECRET_KEY`), so guard the data folder like the credential store it is.


## Notifications

When someone assigns you a card, mentions you with @username in a
comment, or comments on a card assigned to you, SQ drops a notification
in the bell at the top of the page. Unread ones show as a badge; the
dropdown marks them read as you click through.

Want them on your phone? Put an [ntfy](https://ntfy.sh) topic URL (or
any webhook receiver) in the Push notifications box on your account
page. SQ posts each notification there as it happens: ntfy topics get
the text directly, and URLs with "hook" in the path get JSON with text
and url fields. Self-hosted ntfy works exactly the same way.
