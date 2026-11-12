import * as React from "react";

import { type Wallpaper, wallpaperSizes } from "./appearance";

export function WallpaperLayer({ wallpaper }: { wallpaper: Wallpaper }) {
  const sources = wallpaper.sources ?? [];
  return (
    <div className="wallpaper" aria-hidden="true">
      {sources.length > 0 && (
        <picture>
          {sources.map((source) => (
            <source
              key={source.type}
              type={source.type}
              srcSet={source.srcset}
              sizes={wallpaperSizes(wallpaper)}
            />
          ))}
          <img className="wallpaper-photo" src={wallpaper.image} alt="" decoding="async" />
        </picture>
      )}
    </div>
  );
}
