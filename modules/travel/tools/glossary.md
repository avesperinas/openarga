# Travel glossary

The domain's terms and how they are computed. It is put in the agent's context: it is what
separates getting it right from making it up.

**Trip.** With a title, a first and a last day, how many you are, with whom and tags. An
**archived** one (`archived`) does not show in the app's list or in the route, but it counts like
any other in countries, nights and figures.

**Idea.** A trip one wants to make that has no dates yet: destinations, budget per person, from
how many to how many days and the good months to go. It is not a trip and counts in nothing that
was visited. When it is decided, `plan_idea` creates a plan with dates and its destinations wait
in "No day"; the idea stays and remembers the trips that came out of it.

**Plan and confirmed.** A trip is a **plan** (`status: plan`) while it is not decided: its dates
can move, it lives only in Travel and does not show in the calendar. **Confirmed** (`confirmed`)
shows in the calendar. The phase (`phase`) follows from that and from the dates: `plan`,
`upcoming` (confirmed and still to come), `ongoing` and `done`. Only what is ongoing or done counts
in countries, regions, nights, kilometres, spend and figures: what has not happened has not been
visited.

**Main place.** Where one sleeps, with the arrival day and the departure day. A trip is the
sequence of its main places. Its nights are the days between arriving and leaving.

**Visited place.** What is seen from a main place without sleeping there: a city on a day trip, a
museum, a beach. On the map it is painted in a soft tone; where one slept, in a strong one.

**Itinerary and block.** The itinerary is the trip day by day: which lodging one leaves, the legs,
where one arrives and the **blocks**, what one does, in the order given to them. A block has a kind
(`activity`, `transport`, `meal`, `accommodation`, `free_time`, `other`) and, if known, a day,
times, a place and notes. Without a day it is a place kept, waiting for room. An `activity` block
with a place is a visit: it counts as visited and shows on the map. Every visit has its block.

**Booking.** It is not a piece apart: it is what is known about something of the trip. A lodging's
goes in its main place (check-in, check-out, address), a flight's or a train's in its leg (times,
company, number, codes, terminal, seat) and a ticket's or a table's in its block. All carry a
booking code, where it was booked and a link. Its `cost_eur` is what it cost the group: it is noted
as an expense of the trip, per person among the travellers, and if the booking is removed, the
expense stays.

**What is nearby.** `find_nearby` asks OpenStreetMap what is around a place of the trip or a
point, of one class: what to see, where to eat, nature, shopping or going out at night, within
3 km at most. The chosen candidate is kept with `add_block`: without a day it waits for room; with
a day, it goes in it. A meal is `meal`; something seen, `activity`.

**Today.** During a trip, `get_today` gives that day's things in their order: which lodging one
leaves, the legs with their ticket, where one arrives and what one does, with times and where it
is. The day is today in the person's zone unless another is said.

**Weather.** `get_weather` gives the forecast for the next 16 days of a place, in its local time,
or its climate, each month's average over ten years. The climate is what says which months are
good for an idea; the forecast, what to pack for tomorrow.

**Leg.** A journey from one place to another with its mode: plane, train, car, bus or boat. They
are the map's routes. The way out leaves from home, which is not a main place. Each one says
whether it is painted in the thumbnails, the trip map and the route (`on_map`); if not said, the
way out from home and the way back are not, because they would cover the trip, and the rest are.
A plane's kilometres are the straight line; the rest, an estimate on it, because the road is not
traced.

**Country and region.** ISO 3166-1 and 3166-2, computed on saving the place against the map's
polygons. The region is the traveller's first-level one: a Spanish autonomous community, a French
or Italian region, a German Land, a nation of the United Kingdom.

**Expense in another currency.** An expense can keep what was paid (the total) in its currency,
who paid it (a traveller) and the day. It is converted to euros at the ECB reference rate of that
day (the last working day's if there is none that day), and the amount per person comes from that
total. The travellers are the people on the trip: "Me", the companions and "Traveller N" up to the
number of travellers.

**Accounts.** An expense with who paid is split among the travellers, in equal shares or custom
ones (`shares`). Each one's balance is what they paid minus what was theirs, plus what they paid
back and minus what was paid back to them: positive, they are owed. `get_trip` with
`include: [balance]` also gives the fewest transfers to settle up. What was spent without who paid
does not count in the accounts.

**Expense.** Per person and in euros, in three fixed categories: transport (flights, car, fuel and
parking, ferry, train, bus), lodging (hotel, apartment) and other (cash, excursions, insurance and
vaccines, other). The group's total is per person times the number of travellers.

**Budget.** What one means to spend per person on a trip, in euros; a plan that comes from an idea
inherits it. `budget_left_per_person_eur` is what is left: the budget minus the spend per person
noted.

**Days and cost per day.** A trip's days count the first and the last: Friday to Sunday is three,
with two nights. The cost per day is the spend per person over those days.

**Europe.** The UN's 44 states of Europe. "Countries of Europe" is how many of those 44.
