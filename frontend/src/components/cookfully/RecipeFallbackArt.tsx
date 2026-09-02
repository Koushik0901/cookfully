import type { ImgHTMLAttributes } from "react";

const FALLBACKS = {
  breakfast: "/media/recipe-fallbacks/breakfast.jpg",
  grain: "/media/recipe-fallbacks/grain-bowl.jpg",
  savory: "/media/recipe-fallbacks/savory-skillet.jpg",
  fresh: "/media/recipe-fallbacks/fresh-produce.jpg",
  curry: "/media/recipe-fallbacks/chicken-curry-feast.jpg",
  paneer: "/media/recipe-fallbacks/rustic-paneer-curry-feast.jpg",
} as const;

type FallbackKind = keyof typeof FALLBACKS;

function recipeFallbackKind(title: string): FallbackKind {
  const kinds = Object.keys(FALLBACKS) as FallbackKind[];
  // Every title gets a stable, well-distributed slot.  Keyword forcing made a
  // cookbook full of curries, paneer, or grain dishes collapse to one image.
  let hash = 0x811c9dc5;
  for (const character of title.toLocaleLowerCase()) {
    hash = Math.imul(hash ^ character.charCodeAt(0), 0x01000193);
  }
  return kinds[(hash >>> 0) % kinds.length];
}

export function RecipeFallbackArt({
  title,
  className = "",
  loading = "lazy",
}: {
  title: string;
  className?: string;
  loading?: ImgHTMLAttributes<HTMLImageElement>["loading"];
}) {
  const kind = recipeFallbackKind(title);
  return <img className={`recipe-fallback-art ${className}`} src={FALLBACKS[kind]} alt="" loading={loading} decoding="async" draggable={false} data-fallback-kind={kind} />;
}
