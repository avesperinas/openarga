# Design system

Everything visual lives in `packages/ui`: tokens, primitives, the widget shell, charts, maps and
every piece an app screen is made of, each with its Storybook story and its test.

## Hard rules

1. **No module writes a colour, a radius, a shadow, a spacing or a font size.** Only tokens. CI
   rejects hex values, hand-written `rgb()`/`hsl()`, pixel font sizes, inline `style={{}}` and
   arbitrary classes outside `packages/ui` (`pnpm run lint:tokens`).
2. **A new visual piece is born in `packages/ui`**, never inside an app. An app's CSS is for what
   only makes sense in that app.
3. **No third-party component library as a base.** Headless primitives, our own style.
4. **One glass layer at a time**, and nothing draggable is glass: widgets use `.surface`, without
   `backdrop-filter`. Glass is for still, floating chrome (bars, sheets, modals).
5. **Glass opacity is a user setting**, and `prefers-reduced-transparency` and
   `prefers-reduced-motion` are honoured.

## The scales

- Three radii: surface, control and pill.
- Spacing on a closed base-4 scale, `--space-1` to `--space-24`.
- A closed type scale from 11 to 34, plus four sizes for a KPI figure.
- Icons in four sizes and two stroke weights.
- Secondary text reaches 4.5:1 contrast on cards and background in both themes; a test checks it.
- Spring animations, not `ease`. Empty states are designed, not left blank.

## Light, dark and wallpaper

Both themes are first-class. A person can set their own wallpaper; an image that cannot reach the
contrast floor even with the veil at maximum is rejected on upload, saying why.
