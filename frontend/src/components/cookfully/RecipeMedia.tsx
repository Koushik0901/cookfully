import type { CSSProperties, ImgHTMLAttributes } from "react";
import { useEffect, useState } from "react";

import { RecipeFallbackArt } from "./RecipeFallbackArt";

export interface RecipeMediaSource {
  title: string;
  imageUrl?: string | null;
  thumbnailCrop?: {
    x: string | number;
    y: string | number;
    width: string | number;
    height: string | number;
  } | null;
}

export function RecipeMedia({
  recipe,
  className = "",
  alt = "",
  loading = "lazy",
  decoding = "async",
}: {
  recipe: RecipeMediaSource;
  className?: string;
  alt?: string;
  loading?: ImgHTMLAttributes<HTMLImageElement>["loading"];
  decoding?: ImgHTMLAttributes<HTMLImageElement>["decoding"];
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [recipe.imageUrl]);
  if (!recipe.imageUrl || failed) return <RecipeFallbackArt title={recipe.title} className={className} />;
  const crop = recipe.thumbnailCrop ?? { x: "0", y: "0", width: "1", height: "1" };
  return (
    <img
      className={className}
      src={recipe.imageUrl}
      alt={alt}
      loading={loading}
      decoding={decoding}
      draggable={false}
      onError={() => setFailed(true)}
      style={{
        "--crop-x": String(crop.x),
        "--crop-y": String(crop.y),
        "--crop-width": String(crop.width),
        "--crop-height": String(crop.height),
      } as CSSProperties}
    />
  );
}
