import type { CSSProperties, ImgHTMLAttributes } from "react";

import { RecipeFallbackArt } from "./RecipeFallbackArt";

export interface RecipeMediaSource {
  title: string;
  imageUrl?: string | null;
  thumbnailCrop?: {
    focalX: string | number;
    focalY: string | number;
    zoom: string | number;
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
  if (!recipe.imageUrl) return <RecipeFallbackArt title={recipe.title} className={className} />;
  const crop = recipe.thumbnailCrop ?? { focalX: "0.5", focalY: "0.5", zoom: "1" };
  return (
    <img
      className={className}
      src={recipe.imageUrl}
      alt={alt}
      loading={loading}
      decoding={decoding}
      style={{
        "--thumbnail-focal-x": crop.focalX,
        "--thumbnail-focal-y": crop.focalY,
        "--thumbnail-zoom": crop.zoom,
      } as CSSProperties}
    />
  );
}
