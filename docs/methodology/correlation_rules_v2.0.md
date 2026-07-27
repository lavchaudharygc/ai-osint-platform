# Public-Source Identity Correlation Rules v2.0

## Status and Scope

This is the current evidence-handling guide for bounded, authorized
public-source investigations. It separates discovery, collection, identity
corroboration, and threat risk. Runtime output and preserved source evidence are
authoritative if an older document differs from this guide.

These rules support analyst triage; they do not establish legal identity and do
not authorize enforcement, access-control bypass, or collection of private
content.

## Evidence States

| State | Meaning | Permitted conclusion |
|---|---|---|
| URL candidate | A public HTTP probe or search result produced a plausible URL | Unverified lead only |
| Collector-confirmed profile | The assigned collector returned a recognizable public profile | A profile exists; ownership remains unconfirmed |
| Identity-corroborated | Independent public evidence links the profile to the target | Probable relationship requiring human review |
| Identity-confirmed | Strong, independently verified evidence and an authorized human decision support the attribution | Case-specific conclusion with provenance and limitations |

HTTP status, search snippets, and the same username alone never advance a result
beyond an unverified candidate or weak identity indicator.

## Identity Evidence

Weak indicators may prioritize review but are insufficient by themselves:

- exact or similar usernames;
- exact or similar display names;
- generic biographies, occupations, locations, or interests;
- visual resemblance that has not been independently verified; and
- platform presence or HTTP 200 responses.

Stronger corroboration requires independent, target-specific evidence, such as:

- an explicit cross-link between profiles;
- the same verified public contact point, with authority to process it;
- a matching owned domain or official organization page linking the profiles;
- consistent, specific biography facts supported by separate public sources; or
- other provenance-preserved evidence that is unlikely to be shared by
  unrelated people.

Email addresses and phone numbers can be shared, recycled, delegated, spoofed,
or copied. They are strong only after normalization, source verification,
authorization, and conflict review; they are not automatic proof.

## Negative and Conflicting Evidence

Record and surface evidence that weakens attribution:

- fan, parody, tribute, mirror, news, or impersonation labels;
- conflicting names, organizations, locations, biographies, or linked domains;
- a collector reporting not found, blocked, or inconclusive;
- stale search snippets or redirected/login pages; and
- evidence that belongs to a brand, group, bot, or public figure rather than the
  investigated person.

Negative evidence must not be hidden by a higher count of weak matches.

## Decision Rules

1. Same username across platforms is a discovery lead, not identity proof.
2. Collector-confirmed presence proves only that the returned public profile
   exists.
3. High identity confidence requires independent, target-specific
   corroboration and no unresolved material conflict.
4. Fan pages, conflicting biographies, and generic-name collisions require a
   reduced or inconclusive assessment.
5. Incomplete, blocked, rate-limited, and skipped collectors are unknown—not
   negative proof and not successful matches.
6. A human reviewer must examine source URLs, timestamps, provider provenance,
   and conflicting evidence before attribution.

## Risk Is Independent of Identity

Identity-correlation confidence is not a threat score. Cross-platform presence,
popularity, account age, or an exact username must not create medium, high, or
critical threat risk.

Risk requires separately supported harmful-behavior indicators from authorized
public evidence. Automated elevation additionally requires a substantial exact
quote, an exact evidence source reference, and narrow explicit harmful-conduct
language; otherwise it remains unknown for human review. A model cannot suppress
an explicit local review trigger by returning a low label. If indicators are
absent or analysis fails, return low or unknown risk with the limitation stated.
Never recommend legal interception, account action, or enforcement solely from
automated correlation.

## Required Output and Provenance

Where available, reports should distinguish:

- `candidate_platforms`;
- `collector_confirmed_platforms`;
- `identity_corroborated_platforms` or `identity_confirmed_platforms`;
- supporting and conflicting `evidence`;
- `requires_human_review`;
- provider, source URL, collection timestamp, and collection status; and
- a risk assessment whose score and narrative agree.

Do not label an HTTP probe as “profile found,” assign a fixed confidence to a
URL response, or convert identity confidence into threat severity.

## Privacy and Retention

Collect only public or otherwise authorized data. Minimize sensitive fields,
redact Telegram invite hashes, protect local sessions and provider keys, and
apply case-specific retention. Optional SQLite investigation history is
plaintext local storage and remains disabled by default.
