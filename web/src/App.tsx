import "./App.css";
import { Controls } from "./components/Controls";
import { RaceMap } from "./components/Map";
import { MonologueFeed } from "./components/MonologueFeed";
import { WatchFace } from "./components/WatchFace";
import { useRaceSocket } from "./hooks/useRaceSocket";
import { useAppSelector } from "./store/hooks";

function App() {
  useRaceSocket();
  const runners = useAppSelector((state) => state.race.runners);
  const runnerList = Object.values(runners);

  return (
    <div className="app">
      <Controls />
      <div className="app__layout">
        <RaceMap runners={runners} />
        <aside className="app__sidebar">
          {runnerList.map((runner) => (
            <div key={runner.persona_name}>
              <WatchFace runner={runner} />
              <MonologueFeed personaName={runner.persona_name} />
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}

export default App;
