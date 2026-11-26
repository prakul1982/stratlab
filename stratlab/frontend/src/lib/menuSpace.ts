import { createContext, useContext } from "react";
import type { SpaceView } from "./spaces";

/** The space whose menu is showing (Shell works it out from the address): a page every space shares (the Calendar) opens on that
 * space's view of it. */
export const MenuSpace = createContext<SpaceView>("mine");
export const useMenuSpace = () => useContext(MenuSpace);
