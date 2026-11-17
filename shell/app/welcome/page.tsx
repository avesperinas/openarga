import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { Welcome } from "../components/Welcome";
import { launchable, readFirstRun, readModules } from "../lib/kernel";
import { fromHeaders } from "../lib/regional";

export const dynamic = "force-dynamic";

export default async function FirstRun() {
  if (!(await readFirstRun()).pending) redirect("/");
  const person = fromHeaders(await headers());
  const apps = launchable(await readModules())
    .filter((module) => module.view)
    .map((module) => ({ id: module.id, name: module.name, hue: module.hue ?? null }))
    .sort((a, b) => a.name.localeCompare(b.name, person.locale));
  return <Welcome initial={person} apps={apps} />;
}
