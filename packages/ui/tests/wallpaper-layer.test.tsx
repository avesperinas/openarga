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

describe("the background layer", () => {
  it("with variants, it renders <picture> with srcset and the JPEG as a last resort", () => {
    const html = renderToStaticMarkup(<WallpaperLayer wallpaper={uploaded} />);

    expect(html).toContain('<source type="image/avif" srcSet="/a-720 720w, /a-1280 1280w"');
    expect(html).toContain('sizes="max(100vw, 150vh)"');
    expect(html).toContain('src="/api/kernel/ui/wallpapers/abc/image"');
    expect(wallpaperStyle(uploaded)).toMatchObject({ "--wallpaper-image": "none" });
  });

  it("without variants, the photo goes through the CSS background and there is no <picture>", () => {
    const html = renderToStaticMarkup(<WallpaperLayer wallpaper={WALLPAPERS[0]!} />);

    expect(html).toBe('<div class="wallpaper" aria-hidden="true"></div>');
    expect(wallpaperStyle(WALLPAPERS[0]!)).toMatchObject({
      "--wallpaper-image": `url(${WALLPAPERS[0]!.image})`,
    });
  });
});
