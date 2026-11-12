import type { BodyPoint, Figure, Profile } from "./api";

export function figureValue(figure: Pick<Figure, "unit" | "digits">, value: number): string {
  if (figure.unit === "min" && value >= 90) {
    const hours = Math.floor(Math.round(value) / 60);
    const minutes = Math.round(value) % 60;
    return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
  }
  const number = value.toLocaleString("es-ES", {
    minimumFractionDigits: figure.digits,
    maximumFractionDigits: figure.digits,
  });
  return figure.unit ? `${number} ${figure.unit}` : number;
}

export function figureFoot(figure: Figure): string {
  if (figure.mean_30 !== null) return `media 30 días: ${figureValue(figure, figure.mean_30)}`;
  if (figure.mean_365 !== null) return `media del año: ${figureValue(figure, figure.mean_365)}`;
  return figure.latest ? `último dato hace tiempo` : "";
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

const SEX: Record<NonNullable<Profile["sex"]>, string> = { female: "Mujer", male: "Hombre", other: "Otro" };

export function profileRows(profile: Profile, medications = true): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  if (profile.blood_type) rows.push({ label: "Grupo sanguíneo", value: profile.blood_type });
  if (profile.age !== null) rows.push({ label: "Edad", value: `${profile.age} años` });
  if (profile.sex) rows.push({ label: "Sexo", value: SEX[profile.sex] });
  if (profile.height_cm !== null) {
    rows.push({
      label: "Altura",
      value: `${(profile.height_cm / 100).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} m`,
    });
  }
  const stride = (cm: number) => `${cm.toLocaleString("es-ES", { maximumFractionDigits: 0 })} cm`;
  if (profile.walking_stride_cm != null) rows.push({ label: "Zancada al andar", value: stride(profile.walking_stride_cm) });
  if (profile.running_stride_cm != null) rows.push({ label: "Zancada al correr", value: stride(profile.running_stride_cm) });
  if (medications && profile.cardio_medications) rows.push({ label: "Medicación cardiaca", value: profile.cardio_medications });
  return rows;
}
