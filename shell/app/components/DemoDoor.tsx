"use client";

import { Avatar, Icon, SegmentedControl, WallpaperLayer, createT, WALLPAPERS } from "@openarga/ui";
import * as React from "react";

import { CATALOGS } from "../words";

export type DemoLanguage = "en" | "es";

const PEOPLE = [
  { key: "alex", name: "Alex" },
  { key: "sam", name: "Sam" },
] as const;

export function doorOf(person: string, language: DemoLanguage, next: string): string {
  const query = new URLSearchParams({ as: person, locale: language, next });
  return `/login/demo?${query.toString()}`;
}

export function DemoDoor({ initial, next }: { initial: DemoLanguage; next: string }) {
  const [language, setLanguage] = React.useState<DemoLanguage>(initial);
  const t = createT(CATALOGS, language);

  React.useEffect(() => {
    document.documentElement.lang = language;
    document.title = t("demo.title");
  }, [language, t]);

  return (
    <main className="demo-door">
      <WallpaperLayer wallpaper={WALLPAPERS[0]!} />
      <section className="demo-door-card glass" aria-labelledby="demo-title">
        <img className="demo-door-mark" src="/icon.svg" alt="" width={56} height={56} />
        <h1 id="demo-title" className="demo-door-title">
          {t("demo.title")}
        </h1>
        <p className="demo-door-lead">{t("demo.lead")}</p>
        <ul className="demo-door-people">
          {PEOPLE.map((person) => (
            <li key={person.key}>
              <a className="demo-door-person" href={doorOf(person.key, language, next)}>
                <Avatar name={person.name} size="l" />
                <span className="demo-door-person-text">
                  <span className="demo-door-person-name">{t("demo.as", { name: person.name })}</span>
                  <span className="demo-door-person-about">{t(`demo.${person.key}`)}</span>
                </span>
                <Icon name="chevron-right" />
              </a>
            </li>
          ))}
        </ul>
        <div className="demo-door-language">
          <SegmentedControl
            label={t("demo.language")}
            value={language}
            onChange={setLanguage}
            options={[
              { value: "en", label: ownName("en") },
              { value: "es", label: ownName("es") },
            ]}
          />
        </div>
        <p className="demo-door-note">{t("demo.note")}</p>
      </section>
    </main>
  );
}

function ownName(language: "en" | "es"): string {
  const name = new Intl.DisplayNames([language], { type: "language" }).of(language) ?? language;
  return name.charAt(0).toLocaleUpperCase(language) + name.slice(1);
}
