import * as React from "react";

export type IconName =
  | "cup"
  | "umbrella"
  | "castle"
  | "parking"
  | "bed"
  | "bag"
  | "binoculars"
  | "today"
  | "modules"
  | "settings"
  | "edit"
  | "done"
  | "plus"
  | "close"
  | "chevron-left"
  | "chevron-right"
  | "chevron-up"
  | "chevron-down"
  | "target"
  | "info"
  | "bolt"
  | "calendar"
  | "chart"
  | "flame"
  | "heart"
  | "image"
  | "sun"
  | "moon"
  | "system"
  | "trash"
  | "book"
  | "basket"
  | "timer"
  | "undo"
  | "expand"
  | "arrow-right"
  | "minus"
  | "push"
  | "pull"
  | "leg"
  | "kettlebell"
  | "dumbbell"
  | "list"
  | "more"
  | "wallet"
  | "flow"
  | "people"
  | "globe"
  | "map"
  | "pin"
  | "plane"
  | "train"
  | "car"
  | "bus"
  | "boat"
  | "play"
  | "pause"
  | "filter"
  | "repeat"
  | "search"
  | "sidebar"
  | "link"
  | "clock"
  | "layers"
  | "eye"
  | "eye-off"
  | "note"
  | "folder"
  | "graph"
  | "paw"
  | "shield"
  | "home"
  | "id-card"
  | "contract"
  | "appliance"
  | "ticket"
  | "alert"
  | "box"
  | "phone"
  | "mail"
  | "copy"
  | "clip"
  | "camera"
  | "file"
  | "external"
  | "skip"
  | "food"
  | "music"
  | "landmark"
  | "party"
  | "mountain"
  | "bookmark"
  | "bell"
  | "atom"
  | "chip"
  | "spark"
  | "compass"
  | "film"
  | "headphones"
  | "lightbulb";

const PATHS: Record<IconName, React.ReactNode> = {
  food: (
    <>
      <path d="M7 3.5v6.2a2 2 0 0 0 2 2 2 2 0 0 0 2-2V3.5" />
      <path d="M9 3.5v17" />
      <path d="M17 20.5v-17c-2.2 1-3.3 3.5-3.3 6.5v3.5H17" />
    </>
  ),
  music: (
    <>
      <path d="M9 17.5V6l10-2v11.5" />
      <circle cx="6.5" cy="17.5" r="2.5" />
      <circle cx="16.5" cy="15.5" r="2.5" />
    </>
  ),
  landmark: (
    <>
      <path d="M3.5 9 12 4l8.5 5Z" />
      <path d="M6 9.5v8M10 9.5v8M14 9.5v8M18 9.5v8" />
      <path d="M4 20h16" />
    </>
  ),
  party: (
    <>
      <path d="M4 20.5 8.5 7.5l8 8Z" />
      <path d="M13 4.5c.4 1.4-.2 2.6-1.5 3.2" />
      <path d="M19.5 11c-1.4-.4-2.6.2-3.2 1.5" />
      <path d="M15.5 3.5v1.5M20.5 8.5H19M18.5 5.5l-1 1" />
    </>
  ),
  mountain: (
    <>
      <path d="m3 19.5 6.5-11 4 6.5 2.5-3.5 5 8Z" />
      <path d="m7.6 11.8 1.9 1.4 1.8-1.2" />
    </>
  ),
  bookmark: <path d="M6.5 3.5h11v17l-5.5-3.8-5.5 3.8Z" />,
  atom: (
    <>
      <circle cx="12" cy="12" r="1.4" />
      <ellipse cx="12" cy="12" rx="9" ry="3.6" />
      <ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(60 12 12)" />
      <ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(120 12 12)" />
    </>
  ),
  chip: (
    <>
      <rect x="6.5" y="6.5" width="11" height="11" rx="2" />
      <path d="M10 10h4v4h-4Z" />
      <path d="M9.5 3.5v3M14.5 3.5v3M9.5 17.5v3M14.5 17.5v3" />
      <path d="M3.5 9.5h3M3.5 14.5h3M17.5 9.5h3M17.5 14.5h3" />
    </>
  ),
  spark: (
    <>
      <path d="M12 3.5c.6 4.2 2.3 5.9 6.5 6.5-4.2.6-5.9 2.3-6.5 6.5-.6-4.2-2.3-5.9-6.5-6.5 4.2-.6 5.9-2.3 6.5-6.5Z" />
      <path d="M18.5 15.5c.2 1.6.9 2.3 2.5 2.5-1.6.2-2.3.9-2.5 2.5-.2-1.6-.9-2.3-2.5-2.5 1.6-.2 2.3-.9 2.5-2.5Z" />
    </>
  ),
  compass: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m15.5 8.5-2 5-5 2 2-5Z" />
    </>
  ),
  film: (
    <>
      <rect x="3.5" y="5" width="17" height="14" rx="2" />
      <path d="M7.5 5v14M16.5 5v14" />
      <path d="M3.5 9.5h4M3.5 14.5h4M16.5 9.5h4M16.5 14.5h4" />
    </>
  ),
  headphones: (
    <>
      <path d="M4.5 16v-3.5a7.5 7.5 0 0 1 15 0V16" />
      <path d="M4.5 14.5h2.5a1 1 0 0 1 1 1v3.5a1 1 0 0 1-1 1H6a1.5 1.5 0 0 1-1.5-1.5Z" />
      <path d="M19.5 14.5H17a1 1 0 0 0-1 1v3.5a1 1 0 0 0 1 1h1a1.5 1.5 0 0 0 1.5-1.5Z" />
    </>
  ),
  lightbulb: (
    <>
      <path d="M9 17.5h6" />
      <path d="M10 20.5h4" />
      <path d="M8.6 14.5A6 6 0 1 1 15.4 14.5c-.7.6-1.1 1.4-1.1 2.3v.7H9.7v-.7c0-.9-.4-1.7-1.1-2.3Z" />
    </>
  ),
  cup: (
    <>
      <path d="M5 8.5h11v5.5a4.5 4.5 0 0 1-4.5 4.5h-2A4.5 4.5 0 0 1 5 14Z" />
      <path d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16" />
      <path d="M8.5 3.5v2M12 3.5v2" />
      <path d="M4.5 20.5h12" />
    </>
  ),
  umbrella: (
    <>
      <path d="M3.5 11a8.5 8.5 0 0 1 17 0Z" />
      <path d="M12 11v7.5a2 2 0 0 1-4 0" />
      <path d="M12 2.5v1" />
    </>
  ),
  castle: (
    <>
      <path d="M4.5 20.5v-12h3v2h3v-2h3v2h3v-2h3v12Z" />
      <path d="M10 20.5v-4a2 2 0 0 1 4 0v4" />
      <path d="M12 8.5v-5l3 1.3-3 1.2" />
    </>
  ),
  parking: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3.5" />
      <path d="M10 16.5v-9h3a2.75 2.75 0 0 1 0 5.5h-3" />
    </>
  ),
  bed: (
    <>
      <path d="M3.5 18.5v-12" />
      <path d="M3.5 14.5h17v4" />
      <path d="M20.5 14.5v-2.5a3 3 0 0 0-3-3h-6v5.5" />
      <circle cx="7.5" cy="11.2" r="1.8" />
    </>
  ),
  bag: (
    <>
      <path d="M5 8h14l-1 12.5H6Z" />
      <path d="M9 10.5V7a3 3 0 0 1 6 0v3.5" />
    </>
  ),
  binoculars: (
    <>
      <circle cx="7" cy="15.5" r="3.5" />
      <circle cx="17" cy="15.5" r="3.5" />
      <path d="M10.5 15.5h3" />
      <path d="M4 14 6 5.5h3l1 6" />
      <path d="M20 14 18 5.5h-3l-1 6" />
    </>
  ),
  paw: (
    <>
      <circle cx="6.3" cy="10.6" r="1.7" />
      <circle cx="9.8" cy="6.6" r="1.8" />
      <circle cx="14.2" cy="6.6" r="1.8" />
      <circle cx="17.7" cy="10.6" r="1.7" />
      <path d="M12 12c-2.8 0-5 3.1-5 5.3 0 1.5 1.1 2.2 2.5 2.2 1 0 1.7-.5 2.5-.5s1.5.5 2.5.5c1.4 0 2.5-.7 2.5-2.2 0-2.2-2.2-5.3-5-5.3Z" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.5 5 6.2v5.3c0 4.3 2.9 7.6 7 9 4.1-1.4 7-4.7 7-9V6.2Z" />
      <path d="m9 12 2.2 2.2L15.2 10" />
    </>
  ),
  home: (
    <>
      <path d="M3.8 11 12 4.2l8.2 6.8" />
      <path d="M6 9.4v10.1h12V9.4" />
      <path d="M10 19.5v-5.2h4v5.2" />
    </>
  ),
  "id-card": (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="2.5" />
      <circle cx="9" cy="10.8" r="2" />
      <path d="M6 15.6c.6-1.3 1.7-2 3-2s2.4.7 3 2" />
      <path d="M14.5 10h3.5" />
      <path d="M14.5 13.5h2.5" />
    </>
  ),
  contract: (
    <>
      <path d="M14 3.5H7.5A1.5 1.5 0 0 0 6 5v14a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 18 19V7.5Z" />
      <path d="M14 3.5v4h4" />
      <path d="M9 11h6" />
      <path d="M9 14h4" />
      <path d="M9 17.4c.7-.9 1.4-.9 2 0s1.3.9 2 0" />
    </>
  ),
  appliance: (
    <>
      <rect x="5" y="3.5" width="14" height="17" rx="2.5" />
      <path d="M5 8h14" />
      <circle cx="12" cy="14" r="3.6" />
      <path d="M8 5.8h.01" />
      <path d="M10.5 5.8h.01" />
    </>
  ),
  ticket: (
    <>
      <path d="M4 8.7V7a1.5 1.5 0 0 1 1.5-1.5h13A1.5 1.5 0 0 1 20 7v1.7a2.3 2.3 0 0 0 0 4.6V17a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17v-3.7a2.3 2.3 0 0 0 0-4.6Z" />
      <path d="M14.5 5.5v2" />
      <path d="M14.5 11v2" />
      <path d="M14.5 16.5v2" />
    </>
  ),
  alert: (
    <>
      <path d="M10.3 4.7 3.3 17a2 2 0 0 0 1.7 3h14a2 2 0 0 0 1.7-3l-7-12.3a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9.5v4" />
      <path d="M12 16.8h.01" />
    </>
  ),
  box: (
    <>
      <rect x="3.5" y="4.5" width="17" height="4.5" rx="1.2" />
      <path d="M5 9v9.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V9" />
      <path d="M10 12.5h4" />
    </>
  ),
  phone: (
    <path d="M8.3 4H6a1.6 1.6 0 0 0-1.6 1.7c.6 7.4 6.5 13.3 13.9 13.9A1.6 1.6 0 0 0 20 18v-2.3a1.2 1.2 0 0 0-.8-1.1l-2.7-.9a1.2 1.2 0 0 0-1.2.3l-1.3 1.3a11.5 11.5 0 0 1-5.1-5.1l1.3-1.3a1.2 1.2 0 0 0 .3-1.2l-.9-2.7A1.2 1.2 0 0 0 8.3 4Z" />
  ),
  mail: (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="2.2" />
      <path d="m4.2 7.2 7.8 6 7.8-6" />
    </>
  ),
  copy: (
    <>
      <rect x="8.5" y="8.5" width="11" height="11" rx="2" />
      <path d="M15.5 8.5V6A1.5 1.5 0 0 0 14 4.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5" />
    </>
  ),
  clip: (
    <path d="m19.5 11.5-7.3 7.3a4.8 4.8 0 0 1-6.8-6.8l7.7-7.7a3.2 3.2 0 0 1 4.5 4.5l-7.6 7.6a1.6 1.6 0 0 1-2.3-2.3l7-7" />
  ),
  camera: (
    <>
      <path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2.2l1.5-2h5.6l1.5 2h2.2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5Z" />
      <circle cx="12" cy="12.8" r="3.4" />
    </>
  ),
  file: (
    <>
      <path d="M14 3.5H7.5A1.5 1.5 0 0 0 6 5v14a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 18 19V7.5Z" />
      <path d="M14 3.5v4h4" />
    </>
  ),
  external: (
    <>
      <path d="M14 4h6v6" />
      <path d="m20 4-8.5 8.5" />
      <path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10" />
    </>
  ),
  skip: (
    <>
      <path d="M6 6.5v11l8.5-5.5Z" />
      <path d="M18 6.5v11" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M4 12h16" />
      <path d="M12 4c2.2 2.3 3.2 5 3.2 8s-1 5.7-3.2 8c-2.2-2.3-3.2-5-3.2-8s1-5.7 3.2-8Z" />
    </>
  ),
  map: (
    <>
      <path d="M4 6.5 9 4.5l6 2 5-2v13l-5 2-6-2-5 2Z" />
      <path d="M9 4.5v13" />
      <path d="M15 6.5v13" />
    </>
  ),
  pin: (
    <>
      <path d="M12 20.5s-6-5.4-6-10.3a6 6 0 0 1 12 0c0 4.9-6 10.3-6 10.3Z" />
      <circle cx="12" cy="10.2" r="2.2" />
    </>
  ),
  plane: (
    <>
      <path d="M10.5 13.5 4 11l1.5-1.5 7 .5 3.8-3.8a1.8 1.8 0 0 1 2.5 2.5L15 12.5l.5 7L14 21l-2.5-6.5" />
      <path d="M7.5 16.5 5 19" />
    </>
  ),
  train: (
    <>
      <rect x="6" y="3.5" width="12" height="13" rx="3" />
      <path d="M6 10.5h12" />
      <path d="M9.5 13.5h.01" />
      <path d="M14.5 13.5h.01" />
      <path d="m8.5 16.5-2 4" />
      <path d="m15.5 16.5 2 4" />
    </>
  ),
  car: (
    <>
      <path d="M5 16.5v-4l1.8-4.6A2 2 0 0 1 8.7 6.5h6.6a2 2 0 0 1 1.9 1.4l1.8 4.6v4" />
      <path d="M4 16.5h16" />
      <path d="M5 12.5h14" />
      <path d="M7 16.5v2" />
      <path d="M17 16.5v2" />
    </>
  ),
  bus: (
    <>
      <rect x="5" y="3.5" width="14" height="14.5" rx="3" />
      <path d="M5 11.5h14" />
      <path d="M8.5 15h.01" />
      <path d="M15.5 15h.01" />
      <path d="M8 18v2.5" />
      <path d="M16 18v2.5" />
    </>
  ),
  boat: (
    <>
      <path d="M3.5 15.5h17l-2.3 3.5H5.8Z" />
      <path d="M12 4v11.5" />
      <path d="M12 5.5 18 13h-6" />
      <path d="M12 7.5 7.5 13H12" />
    </>
  ),
  play: <path d="M8 5.5v13l10.5-6.5Z" />,
  pause: (
    <>
      <path d="M9 5.5v13" />
      <path d="M15 5.5v13" />
    </>
  ),
  filter: (
    <>
      <path d="M4 6h16" />
      <path d="M7 12h10" />
      <path d="M10 18h4" />
    </>
  ),
  today: (
    <>
      <path d="M4 10.5 12 4l8 6.5" />
      <path d="M6 9.5V19a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9.5" />
    </>
  ),
  modules: (
    <>
      <rect x="4" y="4" width="6.5" height="6.5" rx="2" />
      <rect x="13.5" y="4" width="6.5" height="6.5" rx="2" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="2" />
      <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="2" />
    </>
  ),
  settings: (
    <>
      <path d="M4 7h10" />
      <path d="M18 7h2" />
      <circle cx="16" cy="7" r="2" />
      <path d="M4 17h6" />
      <path d="M14 17h6" />
      <circle cx="12" cy="17" r="2" />
    </>
  ),
  edit: (
    <>
      <path d="M4 20h4l10-10a2.5 2.5 0 0 0-3.5-3.5L4.5 16.5 4 20Z" />
      <path d="M13.5 7.5 16.5 10.5" />
    </>
  ),
  done: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  minus: <path d="M5 12h14" />,
  plus: (
    <>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </>
  ),
  close: (
    <>
      <path d="m6.5 6.5 11 11" />
      <path d="m17.5 6.5-11 11" />
    </>
  ),
  "chevron-left": <path d="m14.5 5.5-7 6.5 7 6.5" />,
  "chevron-right": <path d="m9.5 5.5 7 6.5-7 6.5" />,
  "chevron-up": <path d="m5.5 14.5 6.5-7 6.5 7" />,
  "chevron-down": <path d="m5.5 9.5 6.5 7 6.5-7" />,
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5" />
      <path d="M12 8h.01" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.5" />
    </>
  ),
  expand: <path d="M9 4H4v5M15 4h5v5M15 20h5v-5M9 20H4v-5" />,
  bolt: <path d="M13.5 3 5.5 13.5h5L10 21l8.5-10.5h-5L13.5 3Z" />,
  calendar: (
    <>
      <rect x="4" y="5.5" width="16" height="14.5" rx="3" />
      <path d="M4 10h16" />
      <path d="M8.5 3.5v4" />
      <path d="M15.5 3.5v4" />
    </>
  ),
  push: (
    <>
      <path d="M3.5 17.5h17" />
      <path d="M6.5 17.5v3M17.5 17.5v3" />
      <circle cx="5.6" cy="13.7" r="1.7" />
      <path d="M7.7 14.7h7.3l2.2 2.8" />
      <path d="M11 14.5V7" />
      <path d="M5.5 7h11" />
      <rect x="4" y="4.8" width="2" height="4.4" rx="0.9" />
      <rect x="16" y="4.8" width="2" height="4.4" rx="0.9" />
    </>
  ),
  pull: (
    <>
      <path d="M3 3.5h18" />
      <path d="M8.5 3.5 10.3 9M15.5 3.5 13.7 9" />
      <circle cx="12" cy="7.4" r="1.7" />
      <path d="M10.3 9.5h3.4" />
      <path d="M12 9.5v5.5" />
      <path d="m12 15-1.6 5M12 15l1.6 5" />
    </>
  ),
  leg: (
    <>
      <path d="M3.5 7.5h17" />
      <rect x="2.5" y="5" width="2" height="5" rx="0.9" />
      <rect x="19.5" y="5" width="2" height="5" rx="0.9" />
      <circle cx="12" cy="4.4" r="1.7" />
      <path d="M9 7.5l1.2 2M15 7.5l-1.2 2" />
      <path d="M12 7.5v5" />
      <path d="M12 12.5 8.5 15.3l.8 4.7M12 12.5l3.5 2.8-.8 4.7" />
    </>
  ),
  kettlebell: (
    <>
      <path d="M8.6 10.2 8 7.6A2.2 2.2 0 0 1 10.1 5h3.8a2.2 2.2 0 0 1 2.1 2.6l-.6 2.6" />
      <path d="M12 9.6a5.3 5.3 0 0 0-3.9 8.9c.4.5.9.8 1.5.8h4.8c.6 0 1.1-.3 1.5-.8A5.3 5.3 0 0 0 12 9.6Z" />
    </>
  ),
  dumbbell: (
    <>
      <g transform="rotate(-35 12 12)">
        <path d="M9 12h6" />
        <rect x="6.3" y="6.8" width="2.7" height="10.4" rx="1.1" />
        <rect x="15" y="6.8" width="2.7" height="10.4" rx="1.1" />
        <path d="M4.3 9.6v4.8M19.7 9.6v4.8" />
      </g>
    </>
  ),
  chart: (
    <>
      <path d="M4 16.5 9 11l3.5 3.5L20 7" />
      <path d="M20 7h-4.5" />
      <path d="M20 7v4.5" />
    </>
  ),
  flame: (
    <>
      <path d="M12 3s5 4.5 5 9a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5 0 1.5.5 2.5 1.5 2.5S12 6 12 3Z" />
    </>
  ),
  heart: <path d="M12 19.5s-7-4.3-7-9.5A4 4 0 0 1 12 7.6 4 4 0 0 1 19 10c0 5.2-7 9.5-7 9.5Z" />,
  image: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="3" />
      <circle cx="9" cy="10" r="1.5" />
      <path d="m5 17 4.5-4.5L13 16l2.5-2.5L19 17" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="3.75" />
      <path d="M12 3.5v1.75M12 18.75v1.75M3.5 12h1.75M18.75 12h1.75M6 6l1.25 1.25M16.75 16.75 18 18M6 18l1.25-1.25M16.75 7.25 18 6" />
    </>
  ),
  moon: <path d="M19 14.5A7.5 7.5 0 0 1 9.5 5a7.5 7.5 0 1 0 9.5 9.5Z" />,
  system: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" />
    </>
  ),
  book: (
    <>
      <path d="M12 6.5C10.5 5.2 8.6 4.5 6.5 4.5H4v13h2.5c2.1 0 4 .7 5.5 2" />
      <path d="M12 6.5c1.5-1.3 3.4-2 5.5-2H20v13h-2.5c-2.1 0-4 .7-5.5 2" />
      <path d="M12 6.5v13" />
    </>
  ),
  basket: (
    <>
      <path d="M4 9.5h16l-1.4 8a2 2 0 0 1-2 1.7H7.4a2 2 0 0 1-2-1.7Z" />
      <path d="M8.5 9.5 11 4.5" />
      <path d="M15.5 9.5 13 4.5" />
      <path d="M10 13v3" />
      <path d="M14 13v3" />
    </>
  ),
  timer: (
    <>
      <circle cx="12" cy="13.5" r="7.5" />
      <path d="M12 9.5v4l2.5 1.5" />
      <path d="M9.5 2.5h5" />
    </>
  ),
  trash: (
    <>
      <path d="M4.5 7h15" />
      <path d="M9.5 7V5.5a1.5 1.5 0 0 1 1.5-1.5h2a1.5 1.5 0 0 1 1.5 1.5V7" />
      <path d="M6.5 7l.9 11.2a2 2 0 0 0 2 1.8h5.2a2 2 0 0 0 2-1.8L17.5 7" />
    </>
  ),
  undo: (
    <>
      <path d="M9 5.5 5 9.5l4 4" />
      <path d="M5 9.5h9a5 5 0 0 1 0 10h-1.5" />
    </>
  ),
  "arrow-right": (
    <>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </>
  ),
  list: (
    <>
      <path d="M9.5 6.5H20" />
      <path d="M9.5 12H20" />
      <path d="M9.5 17.5H20" />
      <circle cx="5" cy="6.5" r="1" fill="currentColor" />
      <circle cx="5" cy="12" r="1" fill="currentColor" />
      <circle cx="5" cy="17.5" r="1" fill="currentColor" />
    </>
  ),
  more: (
    <>
      <circle cx="5.5" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="18.5" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  wallet: (
    <>
      <path d="M18.5 7.5V6a1.5 1.5 0 0 0-1.5-1.5H6A2 2 0 0 0 4 6.5v11A2 2 0 0 0 6 19.5h12.5a1.5 1.5 0 0 0 1.5-1.5v-9A1.5 1.5 0 0 0 18.5 7.5H6a2 2 0 0 1-2-2" />
      <path d="M20 11.5h-3.5a1.75 1.75 0 0 0 0 3.5H20" />
    </>
  ),
  people: (
    <>
      <circle cx="9" cy="8.5" r="3" />
      <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
      <circle cx="16.5" cy="9.5" r="2.5" />
      <path d="M15 14.2a4.5 4.5 0 0 1 5.5 4.8" />
    </>
  ),
  flow: (
    <>
      <path d="M8 19V5" />
      <path d="m4.5 8.5 3.5-3.5 3.5 3.5" />
      <path d="M16 5v14" />
      <path d="m12.5 15.5 3.5 3.5 3.5-3.5" />
    </>
  ),
  repeat: (
    <>
      <path d="m17 3 3 3-3 3" />
      <path d="M4 11V9a3 3 0 0 1 3-3h13" />
      <path d="m7 21-3-3 3-3" />
      <path d="M20 13v2a3 3 0 0 1-3 3H4" />
    </>
  ),
  bell: (
    <>
      <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z" />
      <path d="M10 20.5a2.2 2.2 0 0 0 4 0" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" />
    </>
  ),
  sidebar: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
      <path d="M9.5 4.5v15" />
    </>
  ),
  link: (
    <>
      <path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1" />
      <path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  layers: (
    <>
      <path d="m12 4 8.5 4.5L12 13 3.5 8.5Z" />
      <path d="m3.5 12.5 8.5 4.5 8.5-4.5" />
      <path d="m3.5 16.5 8.5 4.5 8.5-4.5" />
    </>
  ),
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  "eye-off": (
    <>
      <path d="m4 4 16 16" />
      <path d="M10.6 5.6a9.7 9.7 0 0 1 1.4-.1c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.9 3.6" />
      <path d="M6.6 6.9C4.1 8.6 2.5 12 2.5 12s3.5 6.5 9.5 6.5a9 9 0 0 0 4.2-1" />
    </>
  ),
  note: (
    <>
      <path d="M6 3.5h8.5L19 8v12.5H6Z" />
      <path d="M14.5 3.5V8H19" />
      <path d="M9 12.5h6M9 16h4" />
    </>
  ),
  folder: (
    <>
      <path d="M3.5 7V18a1.5 1.5 0 0 0 1.5 1.5h14a1.5 1.5 0 0 0 1.5-1.5V9a1.5 1.5 0 0 0-1.5-1.5h-7L10 5H5a1.5 1.5 0 0 0-1.5 1.5Z" />
    </>
  ),
  graph: (
    <>
      <circle cx="12" cy="6" r="2.25" />
      <circle cx="5.5" cy="17" r="2.25" />
      <circle cx="18.5" cy="17" r="2.25" />
      <path d="M10.9 8 6.6 15M13.1 8l4.3 7M7.75 17h8.5" />
    </>
  ),
};

export interface IconProps {
  name: IconName;
  label?: string;
}

export function Icon({ name, label }: IconProps) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {PATHS[name]}
    </svg>
  );
}

export interface IconBadgeProps {
  name: IconName;
  hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
  label?: string;
}

export function IconBadge({ name, hue, label }: IconBadgeProps) {
  return (
    <span className="icon-badge" data-hue={hue}>
      <Icon name={name} label={label} />
    </span>
  );
}
