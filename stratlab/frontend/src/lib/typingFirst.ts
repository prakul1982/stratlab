/** Whether a page may put the cursor in its search box on arrival: on a desktop-sized screen with a mouse, yes; on a
 * phone or a touch screen, no, as a focused box opens the on-screen keyboard over the page (R59-001). */
export function typingFirst(): boolean {
  return typeof matchMedia === "function" && matchMedia("(pointer: fine)").matches && !matchMedia("(max-width: 640px)").matches;
}
