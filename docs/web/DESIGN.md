# Design review

The user selected Atelier, asked for darker cards, and then asked to remove the parts that felt like a generic generated UI. The light table and generated raster engravings remain the visual basis.

## Online research

[Adrian Krebs's original Show HN audit](https://www.adriankrebs.ch/blog/design-slop) lists repeated font pairs, small all-caps labels, decorative badges, repeated frames, gradients, glows, and weak contrast among common generated-page patterns. The author notes false positives and says one pattern does not prove a page is AI-generated. This review uses the list to find unnecessary design choices, not to assign a provenance score.

## Board changes

- Keep the serif wordmark and the architectural art. Use clear sans serif numbers for card prestige and player scores. Omit printed zero prestige on cards; accessible card names still state the exact value.
- Use darker mineral card colors on the light table. Keep costs on a solid ivory band.
- Use sentence case and normal spacing for board labels. Remove the decorative wordmark dot and vague loading, help, and opponent copy.
- Use one frame for decks and bonus counters. Remove extra outlines, most ornamental shadows, and backdrop blur.
- Keep colored gems, card bonuses, and selection states. They carry game information.
- Keep reserve controls visible on mobile and on card focus or hover. Use real buttons for every choice.

## Keyboard contract

[W3C keyboard guidance](https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/) calls for visible, predictable focus and a clear distinction between focus and selection. The board adds directional arrow navigation. Arrows move focus; Enter activates the focused native control. Up and Down change native selection lists; Left and Right move to another control. Tab and Space remain available. Dialog navigation stays inside the open dialog. After a bot turn, the board restores a valid game control if the previous control disappeared or became disabled. Mouse and touch use the same action methods.

The final acceptance checks use browser screenshots, mouse interaction, arrow-and-Enter game flows, and Axe checks at desktop and mobile widths.
