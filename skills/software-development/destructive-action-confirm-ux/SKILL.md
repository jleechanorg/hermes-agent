---
name: destructive-action-confirm-ux
description: Gate irreversible deletes with a typed-value confirm.
version: 1.0.0
author: hermes-curator
license: MIT
metadata:
  hermes:
    tags: [ux, safety, destructive, confirmation, react-native, ios]
    related_skills: [worldai-ios-app, ui-behavior-change-test-migration, fail-closed-evidence-gates]
---

# Destructive-action confirmation gates

## When to Use

Use when a user asks to make an irreversible action harder to trigger — "make them type their email
before deleting", "require typing DELETE", "add a confirmation step to the wipe button" — or when
auditing one that already exists. Covers account deletion, campaign/data wipe, disconnect-and-erase,
token revocation with data loss.

## Design rules

1. **Typed value, not another button.** A third "are you sure" tap adds friction without cognition.
   Require typing something only the account holder knows: the full signed-in email, the account
   handle, or the literal word `DELETE`.
2. **Gate on what the product actually has.** Check the identity model before writing copy: an app
   with email sign-in and no username field must require the **full email**, not a display name, not
   the local part, not an email prefix. Accepting a prefix is a real weakening — call it out.
3. **Fallback must be explicit.** When no email/handle is on file, the expected text becomes the
   literal `DELETE` and the hint says so. Never silently skip the gate.
4. **Normalize predictably.** Compare `String(v ?? '').trim().toLowerCase()` on both sides. State the
   normalization next to the helper so a reviewer can see prefixes are rejected.
5. **Identity fence.** Pin the account key (uid) when the gate opens and re-read it on submit. If it
   changed, refuse with a specific message ("The signed-in account changed. Nothing was deleted.")
   and delete nothing. Mirrors the uid re-check already required before the backend delete call.
6. **Preserve every pre-existing safeguard.** Existing warning steps, Apple/Google reauthentication,
   revocation and the backend deletion call stay exactly as they are; the typed gate is additive.
7. **Mismatch must explain itself.** Do not merely disable the destructive button. Keep it pressable
   and show an inline error ("That does not match. Type the full account email exactly.") so the user
   is not left guessing. A disabled button with no explanation is a dead end on mobile.
8. **Never run the destructive flow yourself.** Do not execute account deletion, wipe, or token
   revocation against any account or backend to "verify". Unit/component tests plus typecheck are the
   proof you own; the human owns the live test.

## Implementation recipe (React Native / Expo, adapts to web)

Extract pure helpers so they are unit-testable without rendering:

```ts
export interface DeleteAccountConfirmationIdentity { email?: string | null }
export function deletionConfirmationExpected(identity): string      // email.trim() || 'DELETE'
export function typedDeletionConfirmationMatches(typed, identity)   // trim+lowercase equality
export function deletionConfirmationHint(identity): string          // "Type <email> to confirm."
```

Component shape:

- After the existing `confirm()` promise resolves true: pin the uid, clear the input, open the gate.
  Do **not** call the destructive API yet.
- Render the gate as an **inline card in the same scroll view as the trigger row**, not as a second RN
  `<Modal>`. Two reasons: (a) iOS presents one modal per view controller, and opening a modal in the
  same tick an alert/modal dismisses can silently fail to present; (b) an inline card is trivially
  testable in jest without modal-host plumbing.
- Controls: hint `Text`, `TextInput` with `autoCapitalize="none"`, `autoCorrect={false}`,
  `spellCheck={false}`, `keyboardType="email-address"`, `returnKeyType="done"`, a destructive
  `Delete Forever` action, a `Cancel` action, and an error `Text` with `accessibilityRole="alert"`.
- Each element carries a `testID` (`…-confirm-hint`, `…-confirm-input`, `…-confirm-submit`,
  `…-confirm-cancel`, `…-confirm-error`) so tests assert behavior, not pixels.
- Wire the account identity from the auth source at the call site
  (`accountEmail={auth.currentUser?.email ?? null}`, `getAccountUid={() => auth.currentUser?.uid ?? null}`),
  not from component-local guesses.

## Test migration (do not loosen)

An intended behavior change invalidates the old "confirm → deletes immediately" assertions. Migrate
them, never delete the coverage:

- Rewrite the happy path to assert: confirm true → gate visible, destructive call **not** yet made →
  type the email → submit → call once, sign-out callback once.
- Keep the cancel path. Add: mismatch (error text, no call), case/whitespace normalization,
  no-email `DELETE` fallback (both accept and reject), identity-fence refusal, cancel-closes-gate.
- Add direct unit tests for the three pure helpers, including empty-string and whitespace-only.
- Leave any untouched util's existing suite (e.g. the two-step warning alerts) as-is and say so.

## Evidence and PR reporting

- If the user says some variant of "do not test it, I'll manually test": that is a **waiver for the
  live flow**, not a waiver for unit tests, typecheck, or honesty. Run the gates, then state in the
  PR body: the waiver verbatim, what was NOT run (device, simulator, real deletion), and that manual
  acceptance is pending with the user.
- Name what the PR does **not** prove — native keyboard/focus behavior of the new input, and the real
  backend delete still firing after the gate — instead of implying coverage.
- Report prod vs non-prod line deltas (source vs tests) computed from `git diff --numstat`.

## Pitfalls

- Accepting `displayName` or the email local part because "username" was in the request: check the
  identity model first; the app may have no username field at all.
- Putting the gate in a second modal immediately after an alert resolves (iOS presentation race; the
  dialog simply never appears on device while unit tests pass).
- Reading the uid only at open time — without a re-read at submit, an account switch deletes the wrong
  account.
- Silent hooks (`window.confirm`) on web: a browser confirm cannot collect text, so the gate must be a
  real component, not a native/browser alert.
- Leaving the original trigger row enabled while the gate is open, so a second tap restarts the flow
  and drops typed input — guard re-entry (`if (busy) return`) and close the card on submit/cancel.
