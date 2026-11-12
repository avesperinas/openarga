# Diccionario de Shopping

Los términos del dominio y cómo se calculan. Se inyecta en el contexto del agente: es lo que
separa que acierte de que invente.

**Lista.** Lo que hay que comprar. Es una: lo pendiente, por secciones, y lo que ya está en el
carro.

**Producto.** Algo que se compra, con su nombre de casa ("Leche", "Pechuga de pollo"). Nace la
primera vez que se apunta y ya no se vuelve a crear: el nombre se compara sin mayúsculas, sin tildes
y sin espacios de más. Guarda su sección y la cantidad de la última vez.

**Sección.** Dónde está en el súper: fruta y verdura, panadería, carne, pescado, charcutería y
quesos, lácteos y huevos, despensa, desayuno y dulces, congelados, bebidas, limpieza, higiene y
otros, en ese orden, que es el de una tienda. Un producto nuevo la recibe de un diccionario; lo que
no conoce va a "otros". Decir la sección de un producto la cambia para siempre.

**Apuntado, en el carro, comprado, quitado.** Los cuatro estados de un producto en la lista.
Apuntar dos veces lo mismo no crea otra entrada. Quitar no borra: el producto y su historial se
quedan.

**Compra.** Lo que había en el carro cuando se terminó, con su fecha. Lo apuntado y no cogido se
queda en la lista para la próxima.

**Cada cuánto.** La mediana de días entre dos compras de un producto, por días distintos. Hace falta
haberlo comprado tres veces; con menos, no se sabe y se dice. La mediana y no la media, para que una
semana fuera no cambie la costumbre.

**Te toca.** Un producto que lleva al menos su "cada cuánto" sin comprarse y no está apuntado. Es
una propuesta: se apunta solo si se pide.

**Habituales.** Lo que más veces se ha comprado y no está apuntado.

**Cantidad.** Texto corto como se diría: "2", "1 kg", "pack de 6". No se suma ni se convierte.
