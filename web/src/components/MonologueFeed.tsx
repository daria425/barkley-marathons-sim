import { useAppSelector } from "../store/hooks";

export function MonologueFeed({ personaName }: { personaName: string }) {
  const entries = useAppSelector((state) => state.race.monologues[personaName] ?? []);

  return (
    <div className="monologue-feed">
      {entries
        .slice()
        .reverse()
        .map((entry, i) => (
          <p key={i}>
            <span className="monologue-feed__time">[{entry.elapsedMin}m]</span> {entry.text}
          </p>
        ))}
    </div>
  );
}
