import {
  DateField,
  EmptyState,
  GroupLabel,
  Hint,
  Icon,
  type IconName,
  Screen,
  SelectField,
  Sheet,
  TextField,
} from "@openarga/ui";
import { useState } from "react";

import {
  type Block,
  type Booking,
  type BookingIn,
  type Itinerary,
  type Traveller,
  type Trip,
  Unauthorised,
  readBookings,
  readDays,
  readTravellers,
  readTrip,
  signIn,
  updateBlock,
  updateLeg,
  updateStay,
} from "./api";
import type { Navigate } from "./App";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { TripTabs } from "./TripChrome";
import { MODES, dateRange, dayLabel, eurosExact, hours } from "./words";

type Loaded = { trip: Trip; days: Itinerary; bookings: Booking[]; travellers: Traveller[] };

export function BookingsScreen({ id, navigate }: { id: string; navigate: Navigate }) {
  const read = useLoad<Loaded>(`bookings/${id}`, async () => {
    const [trip, days, bookings, travellers] = await Promise.all([
      readTrip(id),
      readDays(id),
      readBookings(id),
      readTravellers(id).catch(() => [] as Traveller[]),
    ]);
    return { trip, days, bookings, travellers };
  });
  const loaded = read.data;
  const load = read.reload;
  const [problem, setProblem] = useState("");
  const [open, setOpen] = useState<Booking | null>(null);

  const back = { label: "Viaje", onClick: () => navigate({ screen: "trip", id }) };
  if (!loaded) {
    return (
      <Screen>
        <ScreenHeader title="Reservas" back={back} />
        <Pending found={read.found} label="Cargando las reservas" />
      </Screen>
    );
  }

  const { trip, bookings } = loaded;
  const ahead = trip.phase !== "done";
  const pending = ahead ? bookings.filter((one) => !one.booked) : [];
  const rest = bookings.filter((one) => !pending.includes(one));
  const total = bookings.reduce((sum, one) => sum + (one.cost_eur ?? 0), 0);

  return (
    <Screen>
      <ScreenHeader eyebrow={trip.title} title="Reservas" back={back} />
      <TripTabs id={id} active="bookings" navigate={navigate} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {bookings.length === 0 && (
        <EmptyState
          icon="calendar"
          title="Aún no hay nada que reservar"
          action={{ label: "Editar el viaje", icon: "edit", onClick: () => navigate({ screen: "edit", id }) }}
        >
          Añade alojamientos y trayectos al editar el viaje, o una entrada desde el día a día, y aquí apuntas su reserva.
        </EmptyState>
      )}
      {pending.length > 0 && (
        <section className="travel-group">
          <GroupLabel>
            Por reservar
            <span className="travel-group-detail">{pending.length}</span>
          </GroupLabel>
          <BookingList bookings={pending} trip={trip} onOpen={setOpen} />
        </section>
      )}
      {rest.length > 0 && (
        <section className="travel-group">
          <GroupLabel>
            {pending.length > 0 ? "Reservado" : "Reservas"}
            {total > 0 && <span className="travel-group-detail">{eurosExact(total)} en total</span>}
          </GroupLabel>
          <BookingList bookings={rest} trip={trip} onOpen={setOpen} />
        </section>
      )}
      {open && (
        <BookingSheet
          booking={open}
          loaded={loaded}
          onClose={() => setOpen(null)}
          onSaved={async () => {
            setOpen(null);
            await load();
          }}
          onProblem={setProblem}
        />
      )}
    </Screen>
  );
}

function iconOf(booking: Booking, trip: Trip): IconName {
  if (booking.type === "stay") return "home";
  if (booking.type === "leg") {
    const leg = trip.legs.find((one) => one.id === booking.id);
    return leg ? MODES[leg.mode].icon : "plane";
  }
  return "note";
}

function BookingList({
  bookings,
  trip,
  onOpen,
}: {
  bookings: Booking[];
  trip: Trip;
  onOpen: (one: Booking) => void;
}) {
  return (
    <ol className="surface travel-day">
      {bookings.map((one) => (
        <li key={`${one.type}-${one.id}`} className="travel-block">
          <button type="button" className="travel-block-body travel-booking" onClick={() => onOpen(one)}>
            <span className="travel-step-mark" data-kind={one.type}>
              <Icon name={iconOf(one, trip)} />
            </span>
            <span className="travel-step-text">
              <span className="travel-step-title">{one.title}</span>
              <span className="travel-step-detail">
                {[
                  one.day && (one.until && one.until !== one.day ? dateRange(one.day, one.until) : dayLabel(one.day)),
                  hours(one.at),
                  one.detail,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
              {(one.confirmation || one.provider || one.ticket_of) && (
                <span className="travel-step-detail travel-booking-code">
                  {[one.ticket_of && `En el billete de ${one.ticket_of}`, one.provider, one.confirmation]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              )}
              {one.paid_by && <span className="travel-step-detail">Pagó {one.paid_by}</span>}
            </span>
            {one.cost_eur !== null && <span className="travel-booking-cost">{eurosExact(one.cost_eur)}</span>}
          </button>
        </li>
      ))}
    </ol>
  );
}

const orNull = (text: string) => text.trim() || null;
const time = (value: string | null | undefined) => value?.slice(0, 5) ?? "";
const money = (value: number | null | undefined) => (value === null || value === undefined ? "" : String(value));

function BookingSheet({
  booking,
  loaded,
  onClose,
  onSaved,
  onProblem,
}: {
  booking: Booking;
  loaded: Loaded;
  onClose: () => void;
  onSaved: () => Promise<void>;
  onProblem: (problem: string) => void;
}) {
  const stay = booking.type === "stay" ? loaded.trip.stays.find((one) => one.id === booking.id) : undefined;
  const leg = booking.type === "leg" ? loaded.trip.legs.find((one) => one.id === booking.id) : undefined;
  const block: Block | undefined =
    booking.type === "block"
      ? [...loaded.days.days.flatMap((day) => day.items.flatMap((item) => (item.block ? [item.block] : []))), ...loaded.days.unscheduled].find(
          (one) => one.id === booking.id,
        )
      : undefined;
  const facts = stay ?? leg ?? block;

  const [confirmation, setConfirmation] = useState(facts?.confirmation ?? "");
  const [provider, setProvider] = useState(facts?.provider ?? "");
  const [url, setUrl] = useState(facts?.booking_url ?? "");
  const [cost, setCost] = useState(money(facts?.cost_eur));
  const [checkIn, setCheckIn] = useState(time(stay?.check_in_at));
  const [checkOut, setCheckOut] = useState(time(stay?.check_out_at));
  const [address, setAddress] = useState(stay?.address ?? "");
  const [departs, setDeparts] = useState(time(leg?.departs_at));
  const [arrivesOn, setArrivesOn] = useState(leg?.arrives_on ?? "");
  const [arrives, setArrives] = useState(time(leg?.arrives_at));
  const [carrier, setCarrier] = useState(leg?.carrier ?? "");
  const [number, setNumber] = useState(leg?.number ?? "");
  const [fromCode, setFromCode] = useState(leg?.from_code ?? "");
  const [toCode, setToCode] = useState(leg?.to_code ?? "");
  const [terminal, setTerminal] = useState(leg?.terminal ?? "");
  const [seat, setSeat] = useState(leg?.seat ?? "");
  const [ticket, setTicket] = useState(leg?.ticket_leg_id ?? "");
  const expense = loaded.trip.expenses.find(
    (one) => (stay && one.stay_id === stay.id) || (leg && one.leg_id === leg.id) || (block && one.block_id === block.id),
  );
  const [payer, setPayer] = useState(expense?.paid_by ?? "");
  const [busy, setBusy] = useState(false);
  const tickets = leg
    ? loaded.trip.legs.filter((one) => one.id !== leg.id && !one.ticket_leg_id)
    : [];

  const amount = cost.trim().replace(",", ".");
  const badCost = amount !== "" && !/^\d+(\.\d{1,2})?$/.test(amount);
  const badUrl = url.trim() !== "" && !/^https?:\/\//.test(url.trim());
  const ready = !busy && !badCost && !badUrl && facts !== undefined;

  const save = async () => {
    const shared: BookingIn = {
      confirmation: orNull(confirmation),
      provider: orNull(provider),
      booking_url: orNull(url),
      cost_eur: amount || null,
      ...(amount ? { paid_by: payer || null } : {}),
    };
    const tripId = loaded.trip.id;
    if (stay) {
      await updateStay(tripId, stay.id, {
        place_id: stay.place.id,
        arrives_on: stay.arrives_on,
        leaves_on: stay.leaves_on,
        accommodation: stay.accommodation,
        check_in_at: checkIn || null,
        check_out_at: checkOut || null,
        address: orNull(address),
        ...shared,
      });
    } else if (leg) {
      await updateLeg(tripId, leg.id, {
        from_place_id: leg.from_place.id,
        to_place_id: leg.to_place.id,
        mode: leg.mode,
        travelled_on: leg.travelled_on,
        note: leg.note,
        on_map: leg.on_map,
        departs_at: departs || null,
        arrives_on: arrivesOn || null,
        arrives_at: arrives || null,
        carrier: orNull(carrier),
        number: orNull(number),
        from_code: orNull(fromCode),
        to_code: orNull(toCode),
        terminal: orNull(terminal),
        seat: orNull(seat),
        ticket_leg_id: ticket || null,
        ...shared,
      });
    } else if (block) {
      await updateBlock(tripId, block.id, {
        day: block.day,
        kind: block.kind,
        title: block.title,
        starts_at: block.starts_at,
        ends_at: block.ends_at,
        place_id: block.place?.id ?? null,
        notes: block.notes,
        ...shared,
      });
    }
  };

  return (
    <Sheet
      title={booking.title}
      onClose={onClose}
      action={{
        label: "Guardar",
        disabled: !ready,
        onClick: () => {
          setBusy(true);
          save()
            .then(onSaved)
            .catch((error: unknown) => {
              if (error instanceof Unauthorised) return signIn();
              onProblem(error instanceof Error ? error.message : "No se ha podido guardar la reserva.");
              onClose();
            })
            .finally(() => setBusy(false));
        },
      }}
    >
      <div className="travel-sheet-stack">
        {stay && (
          <>
            <div className="travel-form-row">
              <TextField label="Entrada" type="time" value={checkIn} onChange={setCheckIn} />
              <TextField label="Salida" type="time" value={checkOut} onChange={setCheckOut} />
            </div>
            <TextField label="Dirección" value={address} onChange={setAddress} />
          </>
        )}
        {leg && (
          <>
            <div className="travel-form-row">
              <TextField label="Compañía" value={carrier} onChange={setCarrier} placeholder="Iberia, Renfe…" />
              <TextField label="Número" value={number} onChange={setNumber} placeholder="IB3166" />
            </div>
            <div className="travel-form-row">
              <TextField label="Sale" type="time" value={departs} onChange={setDeparts} />
              <TextField label="Llega" type="time" value={arrives} onChange={setArrives} />
            </div>
            <DateField
              label="Día que llega"
              value={arrivesOn}
              onChange={setArrivesOn}
              hint="Solo si no es el de salida: un vuelo de noche."
            />
            <div className="travel-form-row">
              <TextField label="Desde" value={fromCode} onChange={setFromCode} placeholder="MAD" />
              <TextField label="Hasta" value={toCode} onChange={setToCode} placeholder="KIX" />
            </div>
            <div className="travel-form-row">
              <TextField label="Terminal" value={terminal} onChange={setTerminal} />
              <TextField label="Asiento" value={seat} onChange={setSeat} />
            </div>
            {tickets.length > 0 && (
              <SelectField
                label="Billete"
                value={ticket}
                onChange={setTicket}
                options={[
                  { value: "", label: "El suyo propio" },
                  ...tickets.map((one) => ({
                    value: one.id,
                    label: `El de ${one.from_place.name} → ${one.to_place.name}`,
                  })),
                ]}
              />
            )}
            {ticket && <Hint>El localizador y lo que costó van en el billete de aquel trayecto.</Hint>}
          </>
        )}
        <div className="travel-form-row">
          <TextField label="Localizador" value={confirmation} onChange={setConfirmation} />
          <TextField label="Dónde se reservó" value={provider} onChange={setProvider} placeholder="Booking…" />
        </div>
        <TextField
          label="Enlace"
          value={url}
          onChange={setUrl}
          placeholder="https://…"
          invalid={badUrl}
          hint={badUrl ? "Empieza por https://" : undefined}
        />
        {facts?.booking_url && (
          <a className="travel-booking-link" href={facts.booking_url} target="_blank" rel="noreferrer">
            <Icon name="link" /> Abrir la reserva
          </a>
        )}
        <TextField
          label="Lo que costó, en euros"
          inputMode="decimal"
          value={cost}
          onChange={setCost}
          invalid={badCost}
          hint={
            badCost
              ? "Un importe como 240 o 240,50"
              : `Total del grupo: se apunta como gasto del viaje${loaded.trip.travellers > 1 ? `, ${loaded.trip.travellers} viajeros` : ""}.`
          }
        />
        {amount && loaded.travellers.length > 1 && (
          <SelectField
            label="Quién pagó"
            value={payer}
            onChange={setPayer}
            options={[
              { value: "", label: "Sin decir" },
              ...loaded.travellers.map((one) => ({ value: one.id, label: one.me ? "Tú" : one.name })),
            ]}
          />
        )}
      </div>
    </Sheet>
  );
}
