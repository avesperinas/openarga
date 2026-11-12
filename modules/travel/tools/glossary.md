# Diccionario de Travel

Los términos del dominio y cómo se calculan. Se inyecta en el contexto del agente: es lo que
separa que acierte de que invente.

**Viaje.** Con título, primer y último día, cuántos sois, con quién y etiquetas. Uno
**archivado** (`archived`) no sale en la lista de la app
ni en el recorrido, pero cuenta como cualquier otro en países, noches y cifras.

**Idea.** Un viaje que se quiere hacer y aún no tiene fechas: destinos, presupuesto por persona,
de cuántos a cuántos días y los meses buenos para ir. No es un viaje ni cuenta en nada de lo
visitado. Cuando se decide, `plan_idea` crea un plan con fechas y sus destinos esperan en «Sin día»;
la idea se queda y recuerda los viajes que salieron de ella.

**Plan y confirmado.** Un viaje es un **plan** (`status: plan`) mientras no está decidido: sus
fechas pueden moverse, vive solo en Travel y no sale en el calendario. **Confirmado**
(`confirmed`) sale en el calendario. La fase (`phase`) se deduce de eso y de las fechas: `plan`,
`upcoming` (confirmado y por llegar), `ongoing` (en curso) y `done` (hecho). Solo lo que está en
curso o hecho cuenta en países, regiones, noches, kilómetros, gasto y cifras: lo que no ha pasado
no se ha visitado.

**Lugar principal.** Donde se duerme, con el día de llegada y el de salida. Un viaje es la
secuencia de los suyos. Sus noches son los días entre llegar y salir.

**Lugar visitado.** Lo que se ve desde un lugar principal sin dormir allí: una ciudad de excursión,
un museo, una playa. En el mapa pinta en tono suave; lo dormido, en intenso.

**Itinerario y bloque.** El itinerario es el viaje día a día: de qué alojamiento se sale, los
trayectos, adónde se llega y los **bloques**, lo que se hace, en el orden que se les da. Un bloque
tiene tipo (`activity`, `transport`, `meal`, `accommodation`, `free_time`, `other`), y si se sabe,
día, horas, lugar y notas. Sin día es un sitio guardado que espera hueco. Un bloque `activity` con
lugar es una visita: cuenta como visitado y sale en el mapa. Toda visita tiene su bloque.

**Reserva.** No es una pieza aparte: es lo que se sabe de algo del viaje. La de un alojamiento va
en su lugar principal (entrada, salida, dirección), la de un vuelo o un tren en su trayecto (horas,
compañía, número, códigos, terminal, asiento) y la de una entrada o una mesa en su bloque. Todas
llevan localizador, dónde se reservó y enlace. Su `cost_eur` es lo que costó al grupo: se apunta
como un gasto del viaje, por persona entre los viajeros, y si la reserva se quita, el gasto se
queda.

**Lo que hay cerca.** `find_nearby` pregunta a OpenStreetMap qué hay alrededor de un lugar del
viaje o de un punto, de una clase: qué ver, dónde comer, naturaleza, compras o salir de noche, a
como mucho 3 km. El candidato elegido se guarda con `add_block`: sin día espera hueco; con día, entra
en él. Una comida es `meal`; lo que se ve, `activity`.

**Hoy.** Durante un viaje, `get_today` da lo de ese día en su orden: de qué alojamiento se sale,
los trayectos con su billete, adónde se llega y lo que se hace, con horas y dónde es. El día es el
de España salvo que se diga otro.

**Tiempo.** `get_weather` da la previsión de los próximos 16 días de un sitio, en su hora, o su
clima de cada mes de media de diez años. El clima es lo que dice qué meses son buenos para una idea;
la previsión, qué llevar mañana.

**Trayecto.** Un viaje de un sitio a otro con su medio: avión, tren, coche, bus o barco. Son las
rutas del mapa. La ida sale de casa, que no es un lugar principal. Cada uno dice si se pinta en
las miniaturas, el mapa del viaje y el recorrido (`on_map`); sin decirlo, la ida desde casa y la
vuelta no, porque taparían el viaje, y el resto sí. Los kilómetros del avión son la
línea recta; los del resto, una estimación sobre ella, porque no se traza la carretera.

**País y región.** ISO 3166-1 y 3166-2, calculados al guardar el lugar contra los polígonos del
mapa. La región es la de primer nivel de quien viaja: comunidad autónoma, région, regione, Land,
nación del Reino Unido.

**Gasto en otra moneda.** Un gasto puede guardar lo que se pagó (el total) en su moneda, quién lo
pagó (un viajero) y el día. Se pasa a euros con el cambio de referencia del BCE de ese día (el del
último día hábil si ese día no hay), y de ese total sale el importe por persona. Los viajeros son
las personas del viaje: «Yo», los acompañantes y «Viajero N» hasta el número de viajeros.

**Cuentas.** Un gasto con quién pagó se reparte entre los viajeros, a partes iguales o a medida
(`shares`). El saldo de cada uno es lo que pagó menos lo que le tocaba, más lo que ha devuelto y
menos lo que le han devuelto: positivo, le deben. `get_trip` con `include: [balance]` da también las transferencias
mínimas para quedar en paz. Lo gastado sin quién pagó no cuenta en las cuentas.

**Gasto.** Por persona y en euros, en tres categorías fijas: transporte (vuelos, coche, gasolina y
parking, ferry, tren, bus), alojamiento (hotel, apartamento) y otros (efectivo, excursiones, seguro
y vacunas, otros). El total del grupo es por persona por el número de viajeros.

**Presupuesto.** Lo que se quiere gastar por persona en un viaje, en euros; un plan que sale de una
idea lo hereda de ella. `budget_left_per_person_eur` es lo que queda: el presupuesto menos el gasto
por persona apuntado.

**Días y coste por día.** Los días de un viaje cuentan el primero y el último: de viernes a domingo
son tres, con dos noches. El coste por día es el gasto por persona entre esos días.

**Europa.** Los 44 estados de Europa de la ONU. "Países de Europa" es cuántos de esos 44.
