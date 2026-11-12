# Glosario de Macros

**Entrada**: un momento en que comiste o bebiste, con su hora: el desayuno, el café de las once. Si
vino de Claude, guarda la frase tal como se dijo.

**Línea**: lo que tomaste en esa entrada. Cuatro clases: un **alimento** de la despensa de Recipes
(en gramos, mililitros o unidades), una **receta** de Recipes (en raciones), algo **a ojo** (en
kcal, con las macros si se dicen) y **agua** (en ml, solo la bebida como agua).

**Estimada** (≈): la cantidad la calculó Claude a ojo. Un peso que diste tú o una ración de receta
no lo son. La aproximación está siempre en la cantidad, nunca en los nutrientes.

**Nutrientes**: salen de la despensa, por 100 g o por ración, multiplicados por la cantidad. Se
guardan al apuntar y no cambian si mañana se corrige el alimento. Solo cambian si el alimento se
**sustituye** por otro en Recipes (`replace_food`): entonces lo apuntado pasa al nuevo y se
recalcula con lo suyo. Lo que un alimento no trae no está, que no es lo mismo que cero.

**Cobertura**: de un nutriente en un periodo, qué parte de las kcal viene de líneas que sí traen ese
dato. Por debajo del 80 %, la cifra no es la tuya: faltan datos.

**Referencia**: con qué se compara cada micro. Las de la EFSA para tu sexo y edad (de la ficha de
Apple Salud), o la tuya si la cambias. **Mínimo** (llegar), **máximo** (no pasarse) o **fracción de
las kcal** (grasa saturada y azúcares, por debajo del 10 %).

**Objetivo del día**: kcal, proteína, hidratos y grasa, desde una fecha. Vale hasta que pones otro.

**Unidad de alcohol**: 10 g de etanol.
