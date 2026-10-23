import { createContext, useContext } from "react";

export const ThemeContext = createContext(false);

/** True when dark mode is on. */
export const useDark = () => useContext(ThemeContext);
