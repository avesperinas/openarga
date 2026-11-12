import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WALLPAPERS, type Wallpaper, WallpaperLayer, wallpaperStyle } from "../src/index";

const uploaded: Wallpaper = {
  ...WALLPAPERS[0]!,
  id: "abc",
  image: "/api/kernel/ui/wallpapers/abc/image",
  blurred: "/api/kernel/ui/wallpapers/abc/blurred",
  sources: [
    { type: "image/avif", srcset: "/a-720 720w, /a-1280 1280w" },
    { type: "image/webp", srcset: "/w-720 720w, /w-1280 1280w" },
  ],
  thumb: "/w-360",
  aspect: 1.5,
};

describe("la capa del fondo", () => {
  it("con variantes, pinta <picture> con srcset y el JPEG de último recurso", () => {
    const html = renderToStaticMarkup(<WallpaperLayer wallpaper={uploaded} />);

    expect(html).toContain('<source type="image/avif" srcSet="/a-720 720w, /a-1280 1280w"');
    expect(html).toContain('sizes="max(100vw, 150vh)"');
    expect(html).toContain('src="/api/kernel/ui/wallpapers/abc/image"');
    expect(wallpaperStyle(uploaded)).toMatchObject({ "--wallpaper-image": "none" });
  });

  it("sin variantes, la foto va por el fondo CSS y no hay <picture>", () => {
    const html = renderToStaticMarkup(<WallpaperLayer wallpaper={WALLPAPERS[0]!} />);

    expect(html).toBe('<div class="wallpaper" aria-hidden="true"></div>');
    expect(wallpaperStyle(WALLPAPERS[0]!)).toMatchObject({
      "--wallpaper-image": `url(${WALLPAPERS[0]!.image})`,
    });
  });
});
