# Shopping glossary

The domain terms and how they are computed. It is injected into the agent's context: it is what
separates getting it right from making it up.

**List.** What has to be bought. There is one: what is pending, by section, and what is already in
the trolley.

**Product.** Something that is bought, with its household name ("Milk", "Chicken breast"). It is born
the first time it is added and never created again: names are compared ignoring case, accents and
extra spaces. It keeps its section and the quantity of the last time.

**Section.** Where it is in the supermarket: fruit and vegetables, bakery, meat, fish, deli and
cheese, dairy and eggs, pantry, breakfast and sweets, frozen, drinks, cleaning, personal care and
other, in that order, which is a shop's. A new product gets one from a dictionary; what it does not
know goes to "other". Saying a product's section changes it for good.

**Added, in the trolley, bought, removed.** The four states of a product on the list. Adding the
same thing twice does not create another entry. Removing deletes nothing: the product and its
history stay.

**Trip.** What was in the trolley when shopping was finished, with its date. What was added and not
picked up stays on the list for next time.

**How often.** The median of days between two purchases of a product, counting distinct days. It
needs three purchases; with fewer it is unknown, and that is said. The median and not the mean, so
that a week away does not change the habit.

**Due.** A product that has gone at least its "how often" without being bought and is not on the
list. It is a proposal: it is added only if asked.

**Usual.** What has been bought most often and is not on the list.

**Quantity.** Short text as it would be said: "2", "1 kg", "pack of 6". It is neither added up nor
converted.
