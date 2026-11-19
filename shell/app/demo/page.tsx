import { headers } from "next/headers";

import { DemoDoor, type DemoLanguage } from "../components/DemoDoor";

export const dynamic = "force-dynamic";

const spoken = (accept: string): DemoLanguage =>
  accept
    .split(",")
    .map((part) => part.split(";")[0]?.trim().slice(0, 2).toLowerCase())
    .find((code): code is DemoLanguage => code === "en" || code === "es") ?? "en";

export default async function DemoPage({ searchParams }: { searchParams: Promise<{ next?: string; lang?: string }> }) {
  const { next, lang } = await searchParams;
  const language = lang === "en" || lang === "es" ? lang : spoken((await headers()).get("accept-language") ?? "");
  const target = next?.startsWith("/") && !next.startsWith("//") ? next : "/";
  return <DemoDoor initial={language} next={target} />;
}
