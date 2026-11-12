import { Cover as Picture } from "@openarga/ui";

import type { Book } from "./api";
import { coverUrl } from "./api";

export function Cover({ book, size = "regular" }: { book: Book; size?: "regular" | "large" | "hero" | "small" }) {
  return (
    <Picture title={book.title} subtitle={book.authors[0]} src={book.has_cover ? coverUrl(book) : null} size={size} />
  );
}
