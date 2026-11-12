# Diccionario de Recipes

Los términos del dominio y cómo se calculan. Se inyecta en el contexto del agente: es lo que
separa que acierte de que invente.

**Receta.** Un nombre, unas raciones, unos ingredientes y unos pasos. Lo que se enlaza y lo que se
busca es la receta; lo que se lee es su **versión vigente**.

**Versión.** El contenido de una receta en un momento. Una vez sellada no se modifica nunca:
editar escribe la siguiente. Por eso `update_recipe` puede aceptar la receta entera sin poder
perder nada, y por eso se puede volver a la de antes (ADR-0042).

**Ración.** Para cuánta gente está escrita la receta. Pedirla para otras multiplica las cantidades
por `pedidas / guardadas`; el número guardado no cambia.

**Alimento.** Una entrada del catálogo con sus macros **por 100 g**, importada de USDA o de
OpenFoodFacts y cacheada, o tecleada a mano cuando la fuente no la tiene. Un ingrediente de una
receta apunta a un alimento; no lleva macros propias.

**Procedencia.** De dónde salen las cifras de un alimento tecleado: «etiqueta HSN», «estimado por
el modelo», «receta casera». Se ve en la ficha, porque un dato medido y uno estimado no valen lo
mismo.

**Micros prestados.** Los nutrientes que un alimento no trae y toma de otro (`micros_from`): las
macros de la etiqueta de un producto de marca y los micros de la ficha genérica de USDA. Nunca se
prestan las macros ni lo que el alimento ya trae.

**Porción.** Una medida de casa de un alimento con sus gramos comestibles: «loncha», «puñado».
Un ingrediente en `unit` con `portion` la usa; sin ella, cuenta `grams_per_unit`.

**Sustituir.** Cambiar un alimento por otro en todas partes (`replace_food`): las recetas que lo
usan reciben una versión nueva con el otro, lo apuntado en Macros se recalcula, y el viejo queda
archivado con `replaced_by`. No se borra: las versiones anteriores de las recetas lo nombran.

**Parte comestible.** Lo que se come de lo que se pesa entero (`edible_fraction`): una rueda de
bonito de 730 g son unos 600 g limpios, 0,82. Solo se aplica a una cantidad marcada
`as_purchased`.

**Alias.** Cómo llamas tú a un alimento, corto y en español: "pechuga de pollo" para el "Chicken,
broiler or fryers, breast…" de USDA. Es lo que se lee en la receta y con lo que se escribe: un
ingrediente dictado por nombre se busca primero por alias y después por el nombre de la fuente,
que no se toca nunca porque dice de dónde salen las macros. Un alias nombra un solo alimento.

**Ingrediente sin resolver.** Un nombre que alguien puso y no está en el catálogo. Cuenta como
ingrediente, **no suma macros** y la app pide resolverlo. Nunca se le asigna un alimento parecido:
eso sería mentir en las macros.

**Macros.** Kilocalorías, proteína, grasa e hidratos. Se suman pasando cada cantidad a gramos:
`g` directo, `ml` por la densidad, `tbsp` 15 ml, `tsp` 5 ml, `unit` por los gramos de una unidad,
`pinch` 0,5 g. `kcal` no se deriva de las otras tres: la fuente la da medida.

**Macros incompletas.** Las de una receta a la que le falta algún ingrediente por convertir o por
resolver. Se devuelven igual, con cuántos faltan de cuántos. Media cebolla no son 50 g porque sí.

**Paso.** Un verbo, una duración en minutos, el aparato que ocupa y de qué pasos depende.

**Paso atendido.** El que te tiene delante: picar, remover. Dos atendidos no pueden solaparse,
porque solo hay una persona.

**Paso desatendido.** El que corre solo: horno, reposo, marinado. Libera al cocinero, y es lo que
permite que la receta dure menos que la suma de sus pasos.

**Carril.** El aparato que ocupa un paso (fuego, horno, tabla…). Dos pasos del mismo carril a la
vez se ven en el diagrama, que es como se descubre que no caben.

**Tiempo total.** Desde que empiezas hasta que sirves, con los desatendidos corriendo en paralelo.

**Tiempo activo.** De ese total, cuánto estás tú delante. Es el número con el que se decide si una
receta entra un martes.
