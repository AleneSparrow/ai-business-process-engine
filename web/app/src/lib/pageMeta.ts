/** Set document title + description from marketing routes. The SPA has one
 * index.html, so each public page has to own its tab title or every share
 * and Google result looks like the homepage. */
export function setPageMeta(title: string, description: string) {
  document.title = title;
  let meta = document.querySelector('meta[name="description"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("name", "description");
    document.head.appendChild(meta);
  }
  meta.setAttribute("content", description);
}
