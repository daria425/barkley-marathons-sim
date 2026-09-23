import { Controls } from "@/components/Controls";
import { DottedBackground } from "@/components/DottedBackground";
import { RaceViewer } from "@/components/RaceViewer";
import { MonologueFeed } from "@/components/MonologueFeed";
import { Panel } from "@/components/Panel";
import { WatchFace } from "@/components/WatchFace";
import { useRaceSocket } from "@/hooks/useRaceSocket";
import { useAppSelector } from "@/store/hooks";

function IdleState() {
  return (
    <Panel className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
      <h2 className="text-sm font-semibold tracking-wide">No runner yet</h2>
      <p className="max-w-[22ch] text-sm text-muted-foreground">
        Start a run below to watch the brain take its first steps.
      </p>
    </Panel>
  );
}

function App() {
  const status = useRaceSocket();
  const runners = useAppSelector((state) => state.race.runners);
  const runnerList = Object.values(runners);
  const runner = runnerList[0];

  return (
    <div className="relative flex min-h-screen flex-col gap-4 p-4 lg:h-screen lg:gap-5 lg:overflow-hidden lg:p-6">
      <DottedBackground />

      <div className="flex min-h-0 flex-col gap-4 lg:flex-1 lg:flex-row lg:gap-5">
        <div className="h-[60vh] min-h-[420px] shrink-0 lg:h-auto lg:min-h-0 lg:min-w-0 lg:flex-1">
          <RaceViewer runners={runners} />
        </div>

        <aside className="flex min-h-0 flex-col gap-4 lg:basis-[40%] lg:shrink-0 lg:grow-0">
          {runner ? (
            <>
              <WatchFace runner={runner} />
              <MonologueFeed personaName={runner.persona_name} />
            </>
          ) : (
            <IdleState />
          )}
        </aside>
      </div>

      <Controls status={status} />
    </div>
  );
}

export default App;
