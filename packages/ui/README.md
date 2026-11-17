# packages/ui

OpenArga's design system. Every module must use it.

- `tokens.css` is the only source of colour, type, spacing, radius, material and motion.
- Headless primitives (Radix or Base UI) with our own styling. No component libraries.
- It exports a complete `<Widget>`, with header, menu and the `loading`, `error`, `empty` and
  `disconnected` states. A module that draws its own header does not pass review.
- Storybook from the first commit. If it cannot be seen, it is not used.

CI rejects, outside this package: hex values, `style={{}}` and arbitrary Tailwind classes.
