import type { Locale, Translate } from "@openarga/ui";

import type { BodyPoint, Figure, Profile } from "./api";
import { fixed, unitName } from "./words";

export function figureValue(
  figure: Pick<Figure, "unit" | "digits">,
  value: number,
  t: Translate,
  locale: Locale,
): string {
  if (figure.unit === "min" && value >= 90) {
    const hours = Math.floor(Math.round(value) / 60);
    const minutes = Math.round(value) % 60;
    return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
  }
  const number = fixed(value, locale, figure.digits);
  return figure.unit ? `${number} ${unitName(t, figure.unit)}` : number;
}

export function figureName(t: Translate, figure: Pick<Figure, "id" | "name">): string {
  const key = `metric.${figure.id}.name`;
  const found = t(key);
  return found === key ? figure.name : found;
}

export function figureAbout(t: Translate, figure: Pick<Figure, "id" | "about">): string {
  const key = `metric.${figure.id}.about`;
  const found = t(key);
  return found === key ? figure.about : found;
}

export function figureFoot(figure: Figure, t: Translate, locale: Locale): string {
  if (figure.mean_30 !== null) return t("figure.mean_30", { value: figureValue(figure, figure.mean_30, t, locale) });
  if (figure.mean_365 !== null) return t("figure.mean_year", { value: figureValue(figure, figure.mean_365, t, locale) });
  return figure.latest ? t("figure.old") : "";
}

export function rolling(
  points: BodyPoint[],
  size = 7,
  changedOn: string | null = null,
): { day: string; value: number; average: number }[] {
  const side = (day: string) => changedOn !== null && day >= changedOn;
  return points.map((one, index) => {
    const window = points
      .slice(Math.max(0, index - size + 1), index + 1)
      .filter((each) => side(each.day) === side(one.day));
    const average = window.reduce((sum, each) => sum + each.value, 0) / window.length;
    return { day: one.day, value: one.value, average };
  });
}

export function profileRows(
  profile: Profile,
  t: Translate,
  locale: Locale,
  medications = true,
): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  if (profile.blood_type) rows.push({ label: t("profile.blood_type"), value: profile.blood_type });
  if (profile.age !== null) rows.push({ label: t("profile.age"), value: t("profile.years", { count: profile.age }) });
  if (profile.sex) rows.push({ label: t("profile.sex"), value: t(`profile.sex.${profile.sex}`) });
  if (profile.height_cm !== null) {
    rows.push({ label: t("profile.height"), value: `${fixed(profile.height_cm / 100, locale, 2)} m` });
  }
  const stride = (cm: number) => `${fixed(cm, locale, 0)} cm`;
  if (profile.walking_stride_cm != null) rows.push({ label: t("profile.walking_stride"), value: stride(profile.walking_stride_cm) });
  if (profile.running_stride_cm != null) rows.push({ label: t("profile.running_stride"), value: stride(profile.running_stride_cm) });
  if (medications && profile.cardio_medications) {
    rows.push({ label: t("profile.cardio_medications"), value: profile.cardio_medications });
  }
  return rows;
}
