A simulation of an LLM running the Barkley Marathons—one of the world's most brutal ultramarathons: 100
miles in 60 hours through unmarked terrain in Tennessee, with secret "books" hidden along each of 5 loops to prove passage. The simulator
models the runner's body (heart rate, glycogen, hydration, core temp, sleep debt) and the harsh world (weather, fog, terrain, day/night cycle),
feeding observations to the LLM as the "brain" making decisions every few minutes (effort level, eating, drinking, bearing, resting, quitting).
The magic: Claude only sees a noisy, fog-and-fatigue-degraded position estimate, not the true map—so navigation becomes hilarious failures,
backtracking, and hallucinations kicking in around hour 40. Built on FastAPI + asyncio with SQLite logging and Langfuse tracing, v1 runs a
single runner to completion with a WebSocket feed of real-time state; no frontend yet, just raw decision-making chaos you can watch unfold.
