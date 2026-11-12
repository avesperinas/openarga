# Library · diccionario

- **Lectura**: una vez que lees un libro. Leerlo dos veces son dos lecturas, cada una con sus
  fechas y su valoración. Lo que la app llama "libro" es una lectura con los datos de su edición.
- **Edición**: el libro concreto, identificado por su ISBN-13. Viene de un catálogo (Open Library,
  Google Books) o se teclea cuando no está en ninguno.
- **Estado**: `want` (quiero leerlo), `reading` (leyendo), `read` (leído), `abandoned` (lo dejé).
  Las fechas lo acompañan: leyendo lleva inicio, leído lleva inicio y fin.
- **Valoración**: de 0 a 5, de medio en medio punto.
- **Temática**: una por lectura, de una lista fija: novela, ensayo, historia, ciencia, biografía,
  negocio, fantasía y ciencia ficción, policiaca, poesía, cómic, otros.
- **Páginas al día**: sin progreso página a página, las páginas de un libro se reparten a partes
  iguales entre su inicio y su fin. Es una estimación.
