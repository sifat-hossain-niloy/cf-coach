import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import "./index.css";
import Landing from "./pages/Landing";
import { useTheme } from "./lib/hooks";
import { ThemeContext } from "./lib/theme";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Compare = lazy(() => import("./pages/Compare"));

function App() {
  const [dark, toggle] = useTheme();
  return (
    <ThemeContext.Provider value={dark}>
      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <img src="/favicon.svg" alt="" className="h-6 w-6" />
              CF Coach
            </Link>
            <button onClick={toggle} className="btn-ghost" aria-label="Toggle dark mode">
              {dark ? "☀︎ Light" : "☾ Dark"}
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
          <Suspense fallback={<p className="muted">Loading…</p>}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/u/:handle" element={<Dashboard />} />
              <Route path="/compare/:a/:b" element={<Compare />} />
              <Route path="*" element={<p className="muted">Page not found. <Link className="underline" to="/">Go home</Link></p>} />
            </Routes>
          </Suspense>
        </main>
        <footer className="border-t border-slate-200 py-5 text-center text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
          Not affiliated with Codeforces. Data from the public{" "}
          <a className="underline" href="https://codeforces.com/apiHelp" target="_blank" rel="noreferrer">
            Codeforces API
          </a>
          .
        </footer>
      </div>
    </ThemeContext.Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
