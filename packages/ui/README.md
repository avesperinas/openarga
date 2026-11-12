# packages/ui

Design system de OpenArga. Obligatorio para todos los módulos.

- `tokens.css` es la única fuente de color, tipografía, espacio, radio, material y movimiento.
- Primitivas headless (Radix o Base UI) con estilo propio. Nada de librerías de componentes.
- Exporta `<Widget>` completo, con cabecera, menú y los estados `loading`, `error`, `empty` y
  `disconnected`. Un módulo que pinta su propia cabecera no pasa revisión.
- Storybook desde el primer commit. Si no se puede ver, no se usa.

CI rechaza fuera de este paquete: valores hex, `style={{}}` y clases arbitrarias de Tailwind.
