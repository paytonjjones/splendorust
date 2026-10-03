# Original raster assets

The production game uses generated raster sprite sheets. It contains no drawn SVG art. Built-in image generation created all three sheets. WebP encoding reduces size and preserves transparency. CSS selects atlas cells; it does not draw the assets.

## gems

File: `web/src/assets/gems.webp`. Generated with the built-in image tool.

Prompt:

> Use case: stylized-concept. Asset type: production game sprite atlas, transparent background. Primary request: A simple clean original 3-column by 2-row equal-cell sprite sheet of exactly six small faceted gem token illustrations for an elegant ivory tabletop game. Each of six cells centered at x 1/6, 1/2, 5/6 and y 1/4, 3/4 of the canvas, equal cell size, generous transparent padding 20% around each symbol, absolutely no overlap. Reading order: top-left white/ivory diamond (not pure white; warm stone with dark outlines), top-center blue sapphire octagon, top-right green emerald rectangle with clipped corners; bottom-left terracotta red ruby octagon, bottom-center charcoal black onyx teardrop, bottom-right muted antique gold coin with a small star impression. Flat printed mineral colors with only 2-3 facet shades, bold simple recognizable silhouettes and fine dark outline. The Atelier visual style: restrained museum gift-shop boardgame, tactile screenprint, original. All symbols comparable size, sharp edges and readable at 24 pixels. No text, numbers, labels, frames, shadows outside objects, sparkle particles, elaborate decoration, letters, official Splendor/Space Cowboys art, SVG. Must be truly transparent around the six assets.

## engravings

File: `web/src/assets/engravings.webp`. Generated with the built-in image tool.

Prompt:

> Use case: illustration-story. Asset type: production game card motif atlas, transparent background. Primary request: A precise equal-cell 3-column by 2-row sprite sheet containing exactly six original simple architectural engravings for small boardgame cards. All six centered precisely in equal rectangular cells; no cell overlaps, 18% transparent padding all edges. Reading order: arched stone arcade, small glass conservatory, simple classical column pavilion, round observatory dome, tall garden gateway, symmetrical old workshop facade. Each illustration uses only muted dark warm slate ink linework, slightly hand-engraved printed quality, 2 pixel strong lines, simple hatch accents, clean front-on architectural elevation, no perspective clutter. Each is a compact silhouette roughly twice as wide as tall, readable at 100x60px. Elegant European letterpress Atelier style. Background fully transparent; NO paper background, labels, text, color, official Splendor art, unrelated flourishes. Consistent stroke weight and scale. Keep very simple, distinctive and original.

## seals

File: `web/src/assets/seals.webp`. Generated with the built-in image tool.

Prompt:

> Use case: stylized-concept. Asset type: production game noble seal sprite atlas, transparent background. Primary request: a 3-column by 1-row sheet of exactly three original small antique bronze noble guild seal medallions centered precisely in three equal square cells. Transparent padding 18% all around each round seal. First seal contains a simple arched window, second contains a small classical pavilion, third contains a sun above an observatory. Each seal is circular, restrained warm antique bronze single-tone with dark engraved detail, very simple flat relief illustration with one outer border, screenprinted museum letterpress Atelier style. Readable at 40x40 pixels. Consistent exact size, clean silhouettes, subtle tactile engraving. NO text, crowns, faces, official artwork, large shadows, background, elaborate decor. Truly transparent background.

The direction study at `docs/web/design-concepts.png` uses this prompt:

> Use case: ui-mockup. Asset type: visual concept board for an original browser-based Splendor game called SplendoRust. Create a high fidelity landscape design triptych with three clearly separated, meaningfully different representative mid-game boards, each legible and professionally art directed. Each board uses the physical game's familiar layout: compact opponent score/tableau top, three noble tiles, twelve development cards in three rows of four, six circular gem-bank tokens, human tableau bottom; no sidebar SaaS panels. Use original assets only, no official Splendor graphics. Panel A 'THE ATELIER': ivory linen table, ink blue printed fine lines, editorial elegant serif headings, cream square-ish cards with subtle original geometric architectural engraving, colored gem cost pips and strong point numeral, faceted gemstone tokens, airy and tactile warm paper. Panel B 'MIDNIGHT GUILD': deep pine felt, restrained brass fine lines, dark indigo cards with luminous jewel symbols, small caps typography, rich intimate physical tabletop. Panel C 'FORM & COLOR': very clean modern stone-grey and soft white board, bold Bauhaus coral/cobalt/forest colored card bands, large geometric gem shapes, sturdy modern sans-serif, compact playful graphic design. Clearly show functional readable game cards with prestige at upper left, bonus gemstone upper right, costs at bottom, no unrelated illustration, no marketing hero. Frame all three as actual web browser content with a small SplendoRust wordmark and minimal help/new game controls. Refined spacing, outstanding readability, restrained original decorative language; no gradients everywhere, no emoji, no generic app dashboard, no fake 3D perspective. This is a design exploration image, not a gameplay screenshot.

The chosen direction is The Atelier, with darker mineral card stock, as requested by the user. The browser studies use the generated production assets. The study is kept outside the production bundle.


The favicon is a 64×64 PNG extracted from the first generated patron seal. It adds no new illustration.
