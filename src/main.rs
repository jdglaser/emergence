use emergence::{
    cognition::{AgentDecision, CognitionScheduler, DecisionAction, DeterministicTestBrain},
    domain::{
        agent::{Agent, AgentId, AgentState, Inventory, Personality, SurvivalNeeds, TraitLevel},
        world::{GridSize, Position, World},
    },
    simulation::{engine::Simulation, rules::Rules},
};
use std::{sync::Arc, time::Duration};

#[tokio::main]
async fn main() {
    let make_agent = |id: u64, name: &str| Agent {
        id: AgentId(id),
        name: name.into(),
        personality: Personality {
            sociability: TraitLevel::Medium,
            cooperation: TraitLevel::Medium,
            risk_tolerance: TraitLevel::Medium,
        },
        needs: SurvivalNeeds {
            hunger: 10,
            energy: 90,
            health: 100,
        },
        inventory: Inventory { food: 1, wood: 0 },
        state: AgentState {
            current_activity: None,
        },
    };
    let mut simulation = Simulation::new(
        World::new(GridSize {
            width: 3,
            height: 3,
        }),
        Rules::default(),
    );
    let _ = simulation.add_agent(make_agent(1, "Aster"), Position { x: 1, y: 1 });
    let _ = simulation.add_agent(make_agent(2, "Birch"), Position { x: 2, y: 1 });
    let brain = Arc::new(DeterministicTestBrain::with_delays(vec![
        (
            AgentDecision {
                action: DecisionAction::Rest,
            },
            Duration::from_millis(20),
        ),
        (
            AgentDecision {
                action: DecisionAction::Rest,
            },
            Duration::from_millis(250),
        ),
        (
            AgentDecision {
                action: DecisionAction::Rest,
            },
            Duration::from_millis(20),
        ),
        (
            AgentDecision {
                action: DecisionAction::Rest,
            },
            Duration::from_millis(250),
        ),
    ]));
    let mut scheduler = CognitionScheduler::new(brain, 2, 2, 1, Duration::from_secs(2));
    let interval = std::env::var("EMERGENCE_TICK_INTERVAL_MS")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(50);
    for _ in 0..8 {
        let boundary_tick = simulation.tick_count();
        println!("cognition barrier begins at tick {boundary_tick}");
        let barrier_start = std::time::Instant::now();
        let responses = scheduler.resolve_required(&mut simulation).await;
        println!(
            "cognition barrier ends at tick {} after {:?}",
            simulation.tick_count(),
            barrier_start.elapsed()
        );
        let mut events = responses;
        events.extend(simulation.tick());
        scheduler.observe_events(&events, simulation.tick_count());
        println!("tick {}: {:?}", simulation.tick_count(), events);
        tokio::time::sleep(Duration::from_millis(interval)).await;
    }
}
