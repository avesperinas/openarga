import { type Trip, coverUrl } from "./api";

const KEY = "travel.trip-app";

let current: string | null = null;
export const setLock = (id: string | null) => {
  current = id;
};
export const lock = () => current;
const PREFIX = "/travel/viaje/";

export function tripOfPath(pathname: string): string | null {
  const found = /^\/travel\/viaje\/([0-9a-f-]{36})\/?$/.exec(pathname);
  return found ? found[1]! : null;
}

export const tripAppPath = (id: string) => `${PREFIX}${id}`;

export function standalone(): boolean {
  const ios = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return ios || window.matchMedia?.("(display-mode: standalone)").matches === true;
}

const launched = typeof window === "undefined" ? "" : window.location.pathname;

export function lockedTrip(pathname: string, isStandalone = standalone(), launch = launched): string | null {
  return tripOfPath(pathname) ?? (isStandalone ? tripOfPath(launch) : null);
}

export function forgetStoredLock(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
  }
}

export function initials(title: string): string {
  const words = title
    .split(/\s+/)
    .filter((word) => word.length > 2 || /^[A-ZÁÉÍÓÚÑ]/.test(word))
    .filter((word) => !/^(de|del|la|las|los|el|en|y|a)$/i.test(word));
  return (words.length ? words : [title])
    .slice(0, 2)
    .map((word) => word[0]!.toLocaleUpperCase("es"))
    .join("");
}

function css(name: string): string {
  const root = getComputedStyle(document.documentElement);
  return root.getPropertyValue(name).trim() || root.color;
}

export async function iconOf(trip: Trip, side = 180): Promise<string> {
  const canvas = document.createElement("canvas");
  canvas.width = side;
  canvas.height = side;
  const draw = canvas.getContext("2d");
  if (!draw) return "";
  const url = coverUrl(trip, "thumb");
  const image = url ? await load(url) : null;
  if (image) {
    const crop = Math.min(image.naturalWidth, image.naturalHeight);
    draw.drawImage(
      image,
      (image.naturalWidth - crop) / 2,
      (image.naturalHeight - crop) / 2,
      crop,
      crop,
      0,
      0,
      side,
      side,
    );
  } else {
    const gradient = draw.createLinearGradient(0, 0, side, side);
    gradient.addColorStop(0, css("--map-slept-high"));
    gradient.addColorStop(1, css("--map-route"));
    draw.fillStyle = gradient;
    draw.fillRect(0, 0, side, side);
    draw.fillStyle = css("--mark-paper");
    draw.font = `700 ${Math.round(side * 0.42)}px system-ui, sans-serif`;
    draw.textAlign = "center";
    draw.textBaseline = "middle";
    draw.fillText(initials(trip.title), side / 2, side / 2 + side * 0.03);
  }
  return canvas.toDataURL("image/png");
}

function load(url: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = url;
  });
}

function meta(name: string, content: string) {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.name = name;
    document.head.appendChild(element);
  }
  element.content = content;
}

export async function dressAs(trip: Trip): Promise<void> {
  document.title = trip.title;
  meta("apple-mobile-web-app-title", trip.title.slice(0, 30));
  document.head.querySelector('link[rel="manifest"]')?.remove();
  const icon = await iconOf(trip);
  if (!icon) return;
  for (const link of Array.from(document.head.querySelectorAll<HTMLLinkElement>('link[rel="apple-touch-icon"], link[rel="icon"]'))) {
    link.href = icon;
    link.removeAttribute("type");
  }
}

export function preparedOnce(id: string): boolean {
  try {
    return localStorage.getItem(`${KEY}.prepared.${id}`) !== null;
  } catch {
    return true;
  }
}

export function markPrepared(id: string): void {
  try {
    localStorage.setItem(`${KEY}.prepared.${id}`, new Date().toISOString());
  } catch {
  }
}
