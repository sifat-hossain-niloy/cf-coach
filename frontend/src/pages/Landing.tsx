import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { HANDLE_RE } from "../lib/format";

const FEATURES = [
  ["Weak tags", "Which topics hold you back at your next rating band, with the math shown."],
  ["Rating bands", "Solve rates per 100-point band, in contest vs. practice."],
  ["Daily upsolve queue", "Five problems a day, ordered easy to hard, picked from your own history."],
  ["Progress to next rank", "Rating history, target line, and a rough contests-to-go estimate."],
];

export default function Landing() {
  const [handle, setHandle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const h = handle.trim();
    if (!HANDLE_RE.test(h)) {
      setError("Handles are 3 to 24 letters, digits, underscores, dots or hyphens.");
      return;
    }
    navigate(`/u/${encodeURIComponent(h)}`);
  };

  return (
    <div className="mx-auto max-w-2xl py-8 sm:py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">Your Codeforces training coach</h1>
      <p className="mt-3 text-lg muted">
        Enter a Codeforces handle to get a personal training dashboard. No account needed.
      </p>
      <form onSubmit={submit} className="mt-6 flex flex-col gap-2 sm:flex-row">
        <label htmlFor="handle" className="sr-only">Codeforces handle</label>
        <input
          id="handle"
          autoFocus
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          value={handle}
          onChange={(e) => (setHandle(e.target.value), setError(null))}
          placeholder="Your Codeforces handle"
          className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-base outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30 dark:border-slate-700 dark:bg-slate-900"
        />
        <button className="btn-primary px-5 py-3 text-base">Open dashboard</button>
      </form>
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      <p className="mt-3 text-sm muted">
        Or see an example: <Link className="underline" to="/u/tourist">tourist</Link>
      </p>

      <ul className="mt-10 grid gap-3 sm:grid-cols-2">
        {FEATURES.map(([title, body]) => (
          <li key={title} className="card">
            <p className="font-semibold">{title}</p>
            <p className="mt-1 text-sm muted">{body}</p>
          </li>
        ))}
      </ul>
      <p className="mt-6 text-xs muted">
        The first sync of a handle can take a minute: Codeforces allows one API request every two seconds, shared by
        everyone using this site. After that, data refreshes at most every 10 minutes.
      </p>
    </div>
  );
}
