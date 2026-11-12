/**
 * La API de `<Widget>`, comprobada por el compilador.
 *
 * Este fichero **no se ejecuta**: lo verifica `tsc`, que es quien corre en `pnpm lint`. Cada
 * `@ts-expect-error` es una afirmación al revés: si algún día esa línea dejara de ser un
 * error, `tsc` falla y el PR se cae. Es la forma de escribir "un módulo no puede hacer
 * esto" sin depender de que alguien se acuerde.
 *
 * Lo que defiende, que es el criterio de T-025: **un módulo no puede pintar su propia
 * cabecera.** Si pudiera, veinte widgets escritos en veinte momentos distintos dejarían de
 * parecer del mismo sistema (ADR-0004).
 */
import * as React from "react";

import { Widget, WidgetDetail, WidgetValue } from "../src/index";

const valido = (
  <Widget title="Eventos" hue={1} size="2x2" shape="number" state="ready">
    <WidgetValue>1.284</WidgetValue>
    <WidgetDetail>12 hoy</WidgetDetail>
  </Widget>
);

// @ts-expect-error · no hay prop de cabecera: la cabecera es del sistema, no del módulo
const conCabecera = <Widget title="Eventos" hue={1} size="2x2" shape="number" state="ready" header={<h2>Mía</h2>} />;

// @ts-expect-error · tampoco por partes: ni icono propio
const conIcono = <Widget title="Eventos" hue={1} size="2x2" shape="number" state="ready" icon="📊" />;

// @ts-expect-error · ni acciones propias en la cabecera
const conAcciones = <Widget title="Eventos" hue={1} size="2x2" shape="number" state="ready" actions={[]} />;

// @ts-expect-error · ni clases sueltas con las que colarse
const conClase = <Widget title="Eventos" hue={1} size="2x2" shape="number" state="ready" className="mia" />;

// @ts-expect-error · ni estilo inline, que es la puerta de atrás del principio 5
const conEstilo = <Widget title="Eventos" hue={1} size="2x2" shape="number" state="ready" style={{ padding: 0 }} />;

// @ts-expect-error · el título no es opcional: sale del manifiesto y se pinta antes que los datos
const sinTitulo = <Widget hue={1} size="2x2" shape="number" state="ready" />;

// @ts-expect-error · los tamaños son los tres del catálogo y ninguno más
const tamanoInventado = <Widget title="Eventos" hue={1} size="3x1" shape="number" state="ready" />;

// @ts-expect-error · el tono sale de la paleta fija de ocho, no se inventa en el componente
const tonoInventado = <Widget title="Eventos" hue={99} size="2x2" shape="number" state="ready" />;

// @ts-expect-error · `uncertain` no es un estado: es un modificador de `ready` (ADR-0016)
const dudaComoEstado = <Widget title="Eventos" hue={1} size="2x2" shape="number" state="uncertain" />;

export { valido, conCabecera, conIcono, conAcciones, conClase, conEstilo, sinTitulo, tamanoInventado, tonoInventado, dudaComoEstado };
