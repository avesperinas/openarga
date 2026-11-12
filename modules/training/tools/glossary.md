# Glosario de Training

Lo que hay que saber para contestar sobre entrenamiento sin inventarse nada. Va con las tools
(T-R17), todas de lectura: lo que se registra en Training se registra entrenando.

- `find_exercises` — el índice: traduce un nombre a la variante con la que se entrena.
- `get_sessions` — los entrenos terminados, con rango de fechas. Devuelve **el total del rango**
  además de los que quepan en `limit`: si `returned` es menor que `total`, la lista viene cortada
  y hay que pedir menos rango o más límite, no dar por hecho que eso es todo.
- `summarise_training` — cuenta entrenos, horas y volumen por año, mes, semana, tipo de día o
  centro. **Es la que contesta "cuántos entrenos hice en 2025"**: no hay que leer sesión a sesión,
  y no tiene tope de filas.
- `get_progress` — la carga de una variante a lo largo del tiempo, separada por centro, con el
  mejor día del periodo y los días que no cuentan dichos con su motivo.
- `get_muscles` — la fuerza de cada grupo muscular en un rango, sus series por semana y qué lo ha
  trabajado. **Es la que contesta "¿cómo va mi pecho?"** o "¿qué músculo tengo flojo?".
- `get_activities` — lo que no es fuerza: escalada, pádel, lo que se haya registrado.

## Variante, centro, y por qué la carga solo se compara dentro de una máquina

Un **ejercicio** es el movimiento: press banca, sentadilla, dominada. Una **variante** es ese
ejercicio con un aparato concreto (barra, mancuerna, multipower, máquina, polea, peso corporal).

La regla dura del dominio: **la carga solo se compara dentro de una variante y en un mismo
centro**. 140 kg en multipower y 80 kg en prensa no se suman ni se comparan, porque no miden lo
mismo; y el mismo jalón en dos gimnasios tampoco, porque son dos poleas distintas. Si en un centro
la máquina cambió, `get_progress` marca ese día con `machine_changed`, y lo de antes no se compara
con lo de después. Por eso `get_progress` pide una variante y no un nombre, y por eso
`find_exercises` existe: para traducir "¿cómo va mi press banca?" a la variante con la que esa
persona entrena de verdad. Si hay varias que encajan, hay que preguntar cuál antes de comparar, no
elegir una.

## Días que no cuentan

Un día cuyo e1RM se aleja más de un 30 % de las sesiones de alrededor en su misma máquina no cuenta
para la fuerza: casi siempre es un dato mal apuntado (140 donde iba 104, el par de mancuernas donde
iba una). `get_progress` lo trae con `counts: false` y el motivo en `why_not`. No se borra ni se
corrige desde aquí: se menciona como dudoso o no se menciona, y nunca se usa como récord.

## Serie, repeticiones y carga

Una **serie** son unas repeticiones seguidas con una carga. Puede llevar:

- `weight`: carga externa, en kilos.
- `added_load`: lastre sobre el peso corporal. En dominadas, `4 × 20 kg` son cuatro repeticiones
  con veinte kilos colgados, no con veinte kilos en total.
- Una serie **no completada** es la que se registró sin repeticiones. No cuenta, y no se rellena a
  ojo.

**Serie efectiva** es la que cuenta para un grupo muscular: cada serie cuenta entera para el
músculo principal de su ejercicio y para ninguno más. El jalón es dorsal; que el bíceps trabaje no
lo convierte en una serie de bíceps.

## Sesión y rotación

Una **sesión** es un entreno: el día, el día del plan que tocaba (Push, Pull, Leg…), su duración y
sus series. Una sesión **sin terminar** está en curso y no es histórico: no aparece en
`get_sessions` y no entra en ninguna comparación.

Una **rotación** es una vuelta completa al plan. No es una semana: si el plan tiene tres días y se
entrena cuatro veces por semana, las rotaciones y las semanas no coinciden. "Día 2 de 3" es la
posición dentro de la rotación en curso.

## e1RM, y cuándo no fiarse

El **e1RM** es el peso máximo estimado para una repetición, calculado desde una serie normal con la
fórmula de Epley: `carga × (1 + repeticiones / 30)`. Sirve para comparar sesiones donde no se
hicieron las mismas repeticiones.

Es una estimación, y por encima de **diez repeticiones deja de ser fiable**: con muchas
repeticiones manda la resistencia, no la fuerza máxima. `get_progress` lo dice en cada dato con
`e1rm_reliable`, y un dato marcado como poco fiable se menciona como tal o no se menciona. Las series
de más de quince repeticiones y las de cero (un fallo) no cuentan para la fuerza.

## Fuerza de un músculo e índice de rendimiento

La fuerza de un músculo sale de comparar cada máquina consigo misma: lo que sube o baja cada una
respecto a sus sesiones anteriores, juntado en una curva por músculo. Cambiar de gimnasio, de
máquina o de ejercicio no la mueve; las tres primeras semanas de un ejercicio nuevo tampoco, porque
al empezar se sube por aprender, no por ganar fuerza. `get_muscles` la da en % de cambio en el
rango.

El **índice de rendimiento** es la media de los músculos con datos, base 100, cada músculo con el
mismo peso. En dominadas y fondos la carga es el peso corporal más el lastre: sin peso corporal
apuntado en Ajustes, esos ejercicios no cuentan para la fuerza (`bodyweight_kg` vale `null`).

## Contar, y no confundir cortado con completo

Para cuántos, cuánto o cuándo, `summarise_training`. Para ver los entrenos, `get_sessions` con su
rango. Toda respuesta que venga de una lista trae `total` y `returned`: si no coinciden, lo que se
está viendo es una parte, y decir un número a partir de ahí es inventárselo.

## Lo que no se puede contestar

- **Nada de otra persona.** Cada quien ve lo suyo y lo garantiza la base de datos.
- **Nada que no esté registrado.** Si no hay series de una variante, la respuesta es que no hay
  datos, no una media de otras.
- **Ningún consejo médico ni de rehabilitación.** Un dolor no es un dato de entrenamiento.
