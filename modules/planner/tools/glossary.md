# Glosario de Planner

- **Capa**: un calendario con su nombre y su tono (Personal, Trabajo, Deporte). Cada evento está en
  una. Una capa oculta no sale en la app ni en los widgets, pero sus eventos siguen existiendo.
- **Evento** o **serie**: algo con título, inicio y fin. Una serie es un evento con repetición; se
  guarda una vez y sus ocurrencias se calculan.
- **Ocurrencia**: cada vez que una serie cae en el calendario. Se nombra por su `original_start`, el
  inicio que le daba la regla aunque luego se haya movido. Para tocar solo una hay que pasarlo.
- **Alcance** (`scope`): al cambiar o cancelar algo de una serie, `this` es solo esa ocurrencia,
  `following` esa y las siguientes (la serie se corta y empieza otra), `all` la serie entera.
- **Todo el día**: fechas sin hora. Para las tools, el último día va incluido ("del 1 al 3").
- **Zona**: la de cada evento decide el cambio de hora. Una serie a las 10:00 de Madrid sigue a las
  10:00 tras el cambio de hora. Una hora sin zona se lee en la de casa.
- **Cancelar** no borra: el evento deja de verse y la fila se queda.
- **Fondo**: una capa que no se ve como eventos sino como el marco en el que caen: el horario
  laboral, un viaje. Lo suyo no ocupa tiempo; las lecturas lo devuelven aparte, en `backgrounds`.
  Para saber si hay hueco cuentan los eventos, y el fondo dice en qué marco cae.
- **Suscrita**: una capa que se llena sola desde fuera (festivos, deportes, un `.ics`). No se edita.
