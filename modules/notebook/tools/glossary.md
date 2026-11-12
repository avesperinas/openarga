# Notebook · diccionario

- **Nota**: un fichero Markdown con su título, en una carpeta. Su texto entero, frontmatter
  incluido, es lo que se guarda: es el mismo fichero que en Obsidian.
- **Título**: el nombre del fichero sin `.md`. Es único dentro de su carpeta, sin distinguir
  mayúsculas. No lleva `/ \ : [ ] # ^ |`.
- **Ruta**: `carpeta/subcarpeta/título`. Se usa para nombrar una nota cuando hay dos con el mismo
  título en carpetas distintas.
- **Enlace**: `[[título]]`, `[[carpeta/título]]`, `[[título#encabezado]]` o `[[título|texto que se
  ve]]`. Llega a la nota con ese título; si hay varias, a la de la misma carpeta y después a la de
  ruta más corta. Un enlace a una nota que aún no existe es válido: la espera.
- **Backlink**: una nota que enlaza a esta.
- **Propiedades**: el frontmatter YAML entre dos `---` al principio. Las fechas van en ISO.
- **Tag**: `#tag` en el texto o en la propiedad `tags`. `#a/b` es hijo de `#a`, y buscar por `a`
  encuentra los dos.
- **Sección**: lo que hay bajo un encabezado hasta el siguiente encabezado del mismo nivel o de uno
  más alto, con sus subsecciones.
- **Nota del día**: la que se llama como el día, `2026-09-28`, en la carpeta del diario.
- **Historial**: cada cambio guarda cómo estaba la nota. Lo que cambia Claude queda marcado como
  suyo y se deshace en la app.
- **Papelera**: donde van las notas borradas en la app. Claude no borra.
- **Ficha**: la nota de algo de una app de arga (un libro de Library, un viaje de Travel, una
  cuenta de Money), en la carpeta de esa app. La escribe la app y se rehace sola cuando cambia
  allí (ADR-0092). Lleva `arga` (su enlace, `library:<id>`) y `tipo` (`Libro`) en las propiedades.
- **Bloque de arga**: lo que hay entre `%% arga %%` y `%% /arga %%` en una ficha o en la nota del
  día. Lo escribe su app, igual que sus propiedades: no se cambia en Notebook sino con las tools de esa
  app. Lo que está fuera del bloque es de la persona y ninguna app lo toca.
- **Lo de un día**: en la nota del día, un bloque al final con una sección por app (el entreno, lo
  que se comió, los gastos, las clases) y sus cifras en las propiedades (`pasos`, `kcal`,
  `gasto_eur`). Para preguntar "qué hice el martes", se lee la nota de ese día.
- **Enlace a algo de una app**: `[[library:<id>|texto]]`. Lleva a su ficha si la tiene.
