/** The first stop for the keyboard: jumps past the header to the page's `main` (give it id="main"). Only visible when focused. */
export function SkipLink({ to = "main" }: { to?: string }) {
  return <a className="skip-link sr-only" href={`#${to}`} onClick={(e) => {
    const el = document.getElementById(to);
    if (el) { e.preventDefault(); el.focus(); el.scrollIntoView(); }
  }}>Skip to main content</a>;
}
