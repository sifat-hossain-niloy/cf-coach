import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { BandsSection, PracticeSection, RatingSection, WeakTagsSection } from "../components/Charts";
import { ErrorNote, Skeleton } from "../components/common";
import { QueueSection } from "../components/QueueSection";
import { SummaryHeader, SyncPill } from "../components/SummaryHeader";
import { TagTable } from "../components/TagTable";
import { bandForTarget } from "../lib/format";
import { useApi, useHandleSync } from "../lib/hooks";
import { readJSON, writeJSON } from "../lib/storage";

export default function Dashboard() {
  const { handle = "" } = useParams();
  const sync = useHandleSync(handle);
  const targetKey = `cfcoach:target:${handle.toLowerCase()}`;
  const [target, setTargetState] = useState<number | null>(() => readJSON<number | null>(targetKey, null));
  useEffect(() => setTargetState(readJSON<number | null>(targetKey, null)), [targetKey]);
  const setTarget = (t: number | null) => (setTargetState(t), writeJSON(targetKey, t));

  const ready = sync.hasData;
  const v = sync.version;
  const summary = useApi(() => api.summary(handle, target), [handle, target, v], ready);
  const level = summary.data?.level.value;
  const band = level !== undefined ? bandForTarget(level, target) : null;
  const weak = useApi(() => api.weak(handle, band), [handle, v, band?.lo, band?.hi], ready && level !== undefined);
  const bands = useApi(() => api.bands(handle), [handle, v], ready);
  const tags = useApi(() => api.tags(handle), [handle, v], ready);
  const progress = useApi(() => api.progress(handle, target), [handle, target, v], ready);

  useEffect(() => {
    document.title = `${summary.data?.handle ?? handle} · CF Coach`;
  }, [handle, summary.data?.handle]);

  if (sync.phase === "not_found") {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <h1 className="text-2xl font-bold">Handle not found</h1>
        <p className="mt-2 muted">
          Codeforces has no user called <b>{handle}</b>. Check the spelling and try again.
        </p>
        <Link to="/" className="btn-primary mt-6">Try another handle</Link>
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <h1 className="text-2xl font-bold">Building {handle}'s dashboard</h1>
        <p className="mt-2 muted">
          Fetching submissions and contests from Codeforces. A big history takes a minute, because requests are spaced two
          seconds apart for everyone.
        </p>
        <div className="mt-6 flex justify-center">
          <SyncPill sync={sync} />
        </div>
        {sync.phase === "error" && <Link to="/" className="mt-6 inline-block text-sm underline">Back</Link>}
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-4">
      {summary.data ? (
        <SummaryHeader summary={summary.data} sync={sync} target={target} onTarget={setTarget} />
      ) : (
        <>
          <ErrorNote error={summary.error} />
          <Skeleton h={180} />
        </>
      )}
      <QueueSection handle={handle} version={v} band={band} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {weak.data ? <WeakTagsSection weak={weak.data} /> : <Skeleton h={360} />}
        <div className="min-w-0 space-y-4">
          {bands.data ? <BandsSection bands={bands.data} /> : <Skeleton h={300} />}
          {progress.data ? <PracticeSection progress={progress.data} /> : <Skeleton h={260} />}
        </div>
      </div>
      {progress.data ? <RatingSection progress={progress.data} /> : <Skeleton h={320} />}
      {tags.data ? <TagTable tags={tags.data} /> : <Skeleton h={300} />}
    </div>
  );
}
