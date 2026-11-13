import { configureRegional } from "@openarga/ui";

// The apps' tests were written for an instance in Spain; a test that cares sets its own.
configureRegional({ locale: "es-ES", timeZone: "Europe/Madrid", currency: "EUR" });
