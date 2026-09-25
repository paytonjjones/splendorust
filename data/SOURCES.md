# Functional data and rules sources

Checked on 2026-09-25. No artwork, scans, portraits, or game UI assets are included. CSV files contain only game-mechanical facts. Rust metadata mirrors those files and is checked by tests.

## Rules

Publisher, Space Cowboys / Asmodee, English refreshed base-game rules:
https://cdn.svc.asmodee.net/production-asmodeeca/uploads/2022/01/SCSPL01EN_SPLENDOR_RULES_LIGHT.pdf

Original English rules, used as an additional reference:
https://images-cdn.asmodee.us/filer_public/bb/99/bb99c065-fb11-4cad-a918-e02099fd1a36/spl01_rules.pdf

The refreshed rules clarify reduced distinct-token takes, optional gold substitution, and shared victories after the purchased-card tiebreak. Neither rulebook specifies what to do when none of the four actions is available.

## Development cards

All 90 tuples (tier, bonus, prestige, five costs) matched after normalizing color order:

- https://github.com/bouk/splendimax/blob/master/Splendor%20Cards.csv
- https://github.com/seal256/splendor/blob/263abc066c563a1c89dba4bdc408446a20ad9d1d/assets/cards.csv

Card IDs follow that row order. CSV tiers are 1–3. Rust tiers are 0–2. Color order is white, blue, green, red, black. `scripts/check_data.py` accepts local copies of either source to repeat the comparison. It never requires network access for the ordinary offline data checks.

## Nobles

The ten requirements match `NOBLES_STR` at:
https://github.com/seal256/splendor/blob/263abc066c563a1c89dba4bdc408446a20ad9d1d/src/splendor.cpp

There are five adjacent pairs with four bonuses each, and five adjacent triples with three bonuses each, on the white→blue→green→red→black color cycle. Every noble gives three prestige. Noble IDs use pair order first, then triple order. Tests check the explicit complete list as well as CSV equality.

Source audit caught two issues: bouk's `src/noble.rs` has only nine entries; another inspected implementation (`boardgamers/splendor`, `data.ts`) replaces the white/red/black triple with white/green/red. Neither list was used as the ground truth. The complete seal256 list agrees with the nine valid bouk entries plus the missing white/blue pair.

No reference implementation code was copied. The reference engine chooses the first eligible noble and does not expose a noble-choice action, so full trajectory equivalence would not validate our rules. Its absent repository license is another reason not to embed an adapter or copied implementation.
