# Emergence

Emergence is an experimental AI-driven social survival simulation. Agents inhabit a shared 2D world, gather resources, construct shelter, and eventually develop memories, relationships, and social behavior.

This is also a learning project: the implementation should make simulation design, asynchronous AI orchestration, and Python approachable to an experienced engineer.

## Current state

The project has completed **M2: The Living World**. It runs a deterministic grid simulation with survival, adjacent gathering, shelter construction, and persistent destination movement. Worlds persist in memory between ticks. There is no visual UI, LLM integration, or disk save/load yet. The previous Rust application is archived.

The current stack is Python 3.13+, uv, Pydantic, pytest, Ruff, and strict Pyright checking. Starlette, React, TypeScript, Vite, Canvas, and asynchronous OpenAI integration belong to future milestones.

## Setup and checks

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the repository root:

```sh
uv sync
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```

`uv sync` installs the package and development tools in `.venv` using `uv.lock`. Python 3.13 is selected by `.python-version`. There is no application launcher or frontend setup yet.

M2 verification passed formatting, linting, strict typing, and 169 tests. Verification used a temporary uv installation because uv was absent from PATH; a permanent global installation was not created.

## Try destination movement

Run `uv run python`, then paste this example. One decision starts travel; subsequent ticks continue it:

```python
from emergence.domain.actions import Move
from emergence.domain.agent import Agent
from emergence.domain.values import AgentId, Needs, Personality, Position
from emergence.simulation import Simulation
from emergence.world import Tile, World

agent = Agent(
    id=AgentId(value=1),
    name="Ada",
    position=Position(x=0, y=0),
    personality=Personality(
        sociability=50,
        cooperativeness=50,
        cautiousness=50,
        curiosity=50,
        assertiveness=50,
    ),
    needs=Needs(hunger=100, energy=100, health=100),
)
simulation = Simulation(
    World(width=4, height=1, tiles=(Tile(),) * 4, agents=(agent,)),
    seed=42,
)
events = simulation.step({agent.id: Move(destination=Position(x=3, y=0))})
print(simulation.world.agent(agent.id).position)  # x=1 y=0
simulation.step()
simulation.step()
print(simulation.world.agent(agent.id).position)  # x=3 y=0
print(simulation.world.tick)  # 3
```

Source packages are `domain/` (validated vocabulary), `world/` (snapshots), and `simulation/` (rules and A*). Tests mirror those packages. Start with the learning guide for a walkthrough.

## Read the project

- [Architecture](docs/ARCHITECTURE.md): who owns state, how decisions enter the simulation, and how time works.
- [Roadmap](docs/ROADMAP.md): milestone scope, status, and completion criteria.
- [Decisions](docs/DECISIONS.md): the reasons behind the important boundaries.
- [Learning guide](docs/GUIDE.md): how to study and extend the implementation as it grows.
- [Engineering instructions](AGENTS.md): development workflow and standards.

Each milestone starts with an Architect proposal and human approval, then implementation, independent review, and documentation. Milestones do not advance automatically; commits require explicit approval.

## Reset archive and local artifacts

The previous repository files were preserved in `../emergence-rust-archive-20261011-m0/repository-before-reset.tar.gz`. Git history remains in this repository.

Existing `run.sh`, `.secret`, and `logs/` are preserved local artifacts from the old application. They are ignored by Git and are not supported launch or configuration paths for the reboot. Keep credentials out of source control; future OpenAI configuration belongs exclusively on the backend.
