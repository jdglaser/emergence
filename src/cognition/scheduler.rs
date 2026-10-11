use super::{AgentDecision, Brain, BrainError, Observation};
use crate::{
    domain::agent::AgentId,
    simulation::{engine::Simulation, event::Event},
};
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::Arc,
    time::Duration,
};
use tokio::{sync::Semaphore, time::timeout};

#[derive(Debug, Clone, PartialEq, Eq)]
enum SlotState {
    NeedsDecision,
    Outstanding { request_id: u64 },
    Resolved,
    Cooldown { eligible_at_tick: u64 },
}

#[derive(Debug, Clone)]
struct Slot {
    next_request_id: u64,
    state: SlotState,
}

struct Response {
    request_id: u64,
    result: Result<AgentDecision, BrainError>,
}

/// Coordinates cognition at a simulation-time barrier.
///
/// Brain tasks receive owned observations, never a simulation reference. All tasks
/// finish before their decisions are submitted in deterministic `AgentId` order.
pub struct CognitionScheduler {
    brain: Arc<dyn Brain>,
    radius: u32,
    cooldown_ticks: u64,
    timeout: Duration,
    slots: BTreeMap<AgentId, Slot>,
    limit: Arc<Semaphore>,
}

impl CognitionScheduler {
    pub fn new(
        brain: Arc<dyn Brain>,
        radius: u32,
        concurrency: usize,
        cooldown_ticks: u64,
        timeout: Duration,
    ) -> Self {
        Self {
            brain,
            radius,
            cooldown_ticks: cooldown_ticks.max(1),
            timeout,
            slots: BTreeMap::new(),
            limit: Arc::new(Semaphore::new(concurrency.max(1))),
        }
    }

    /// Resolves all required decisions without advancing the simulation clock.
    pub async fn resolve_required(&mut self, simulation: &mut Simulation) -> Vec<Event> {
        let tick = simulation.tick_count();
        self.promote_cooldowns(tick);

        // Snapshot every observation before a request starts, from one stable state.
        let mut requests = Vec::new();
        for (agent, _) in simulation.agents() {
            let slot = self.slots.entry(agent.clone()).or_insert(Slot {
                next_request_id: 0,
                state: SlotState::NeedsDecision,
            });
            if slot.state != SlotState::NeedsDecision || !simulation.is_eligible(agent) {
                continue;
            }
            let Some(observation) = Observation::from_simulation(simulation, agent, self.radius)
            else {
                continue;
            };
            slot.next_request_id = slot.next_request_id.saturating_add(1);
            let request_id = slot.next_request_id;
            slot.state = SlotState::Outstanding { request_id };
            requests.push((agent.clone(), request_id, observation));
        }

        let mut handles = BTreeMap::new();
        for (agent, request_id, observation) in requests {
            let brain = Arc::clone(&self.brain);
            let limit = Arc::clone(&self.limit);
            let duration = self.timeout;
            handles.insert(
                agent.clone(),
                tokio::spawn(async move {
                    let result = match limit.acquire_owned().await {
                        Ok(_permit) => match timeout(duration, brain.decide(observation)).await {
                            Ok(result) => result,
                            Err(_) => Err(BrainError("request timed out".into())),
                        },
                        Err(_) => Err(BrainError("scheduler stopped".into())),
                    };
                    Response { request_id, result }
                }),
            );
        }

        let mut responses = BTreeMap::new();
        for (agent, handle) in handles {
            let response = match handle.await {
                Ok(response) => response,
                Err(error) => Response {
                    request_id: self.request_id(&agent),
                    result: Err(BrainError(format!("request task failed: {error}"))),
                },
            };
            responses.insert(agent, response);
        }

        let mut events = Vec::new();
        for (agent, response) in responses {
            let matching_request = self.slots.get(&agent).is_some_and(|slot| {
                slot.state
                    == SlotState::Outstanding {
                        request_id: response.request_id,
                    }
            });
            if !matching_request {
                continue;
            }
            match response.result {
                Ok(decision) if simulation.is_eligible(&agent) => {
                    if let Some(event) =
                        simulation.submit_action(agent.clone(), decision.into_action())
                    {
                        self.cool_down(&agent, tick);
                        events.push(event);
                    } else if let Some(slot) = self.slots.get_mut(&agent) {
                        slot.state = SlotState::Resolved;
                    }
                }
                _ => self.cool_down(&agent, tick),
            }
        }
        events
    }

    /// Apply engine events after a tick. Rejection wins over a completion trigger.
    pub fn observe_events(&mut self, events: &[Event], tick: u64) {
        let rejected: BTreeSet<_> = events
            .iter()
            .filter_map(|event| match event {
                Event::ActionRejected { agent, .. } => Some(agent.clone()),
                _ => None,
            })
            .collect();
        for agent in &rejected {
            self.cool_down(agent, tick);
        }
        for event in events {
            let agent = match event {
                Event::ActivityCompleted { agent } | Event::Ate { agent } => agent,
                _ => continue,
            };
            if !rejected.contains(agent) {
                self.slots
                    .entry(agent.clone())
                    .or_insert(Slot {
                        next_request_id: 0,
                        state: SlotState::NeedsDecision,
                    })
                    .state = SlotState::NeedsDecision;
            }
        }
    }

    fn promote_cooldowns(&mut self, tick: u64) {
        for slot in self.slots.values_mut() {
            if let SlotState::Cooldown { eligible_at_tick } = slot.state
                && eligible_at_tick <= tick
            {
                slot.state = SlotState::NeedsDecision;
            }
        }
    }

    fn cool_down(&mut self, agent: &AgentId, tick: u64) {
        let slot = self.slots.entry(agent.clone()).or_insert(Slot {
            next_request_id: 0,
            state: SlotState::NeedsDecision,
        });
        slot.state = SlotState::Cooldown {
            eligible_at_tick: tick.saturating_add(self.cooldown_ticks),
        };
    }

    fn request_id(&self, agent: &AgentId) -> u64 {
        self.slots.get(agent).map_or(0, |slot| slot.next_request_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        cognition::{DecisionAction, DeterministicTestBrain},
        domain::{
            agent::{Agent, AgentState, Inventory, Personality, SurvivalNeeds, TraitLevel},
            world::{GridSize, Position, World},
        },
        simulation::{event::RejectionReason, rules::Rules},
    };
    use std::{
        sync::atomic::{AtomicUsize, Ordering},
        time::Instant,
    };

    fn agent(id: u64) -> Agent {
        Agent {
            id: AgentId(id),
            name: format!("agent-{id}"),
            personality: Personality {
                sociability: TraitLevel::Low,
                cooperation: TraitLevel::Low,
                risk_tolerance: TraitLevel::Low,
            },
            needs: SurvivalNeeds {
                hunger: 0,
                energy: 100,
                health: 100,
            },
            inventory: Inventory { food: 0, wood: 0 },
            state: AgentState {
                current_activity: None,
            },
        }
    }

    fn simulation(count: u64) -> Simulation {
        let mut simulation = Simulation::new(
            World::new(GridSize {
                width: 4,
                height: 4,
            }),
            Rules::default(),
        );
        for id in 1..=count {
            assert!(simulation.add_agent(
                agent(id),
                Position {
                    x: id as u32 - 1,
                    y: 0
                }
            ));
        }
        simulation
    }

    #[tokio::test]
    async fn barrier_waits_without_advancing_simulation_time() {
        let mut sim = simulation(1);
        let brain = Arc::new(DeterministicTestBrain::new(
            vec![AgentDecision {
                action: DecisionAction::Rest,
            }],
            Duration::from_millis(20),
        ));
        let mut scheduler = CognitionScheduler::new(brain, 1, 1, 1, Duration::from_secs(1));
        let start = Instant::now();
        assert!(scheduler.resolve_required(&mut sim).await.is_empty());
        assert!(start.elapsed() >= Duration::from_millis(15));
        assert_eq!(sim.tick_count(), 0);
        assert!(!sim.is_eligible(&AgentId(1)));
    }

    #[tokio::test]
    async fn completed_activity_triggers_once_but_idle_agent_is_not_repolled() {
        let mut sim = simulation(1);
        let brain = Arc::new(DeterministicTestBrain::new(
            vec![
                AgentDecision {
                    action: DecisionAction::Rest,
                },
                AgentDecision {
                    action: DecisionAction::Rest,
                },
            ],
            Duration::ZERO,
        ));
        let mut scheduler = CognitionScheduler::new(brain, 1, 1, 1, Duration::from_secs(1));
        scheduler.resolve_required(&mut sim).await;
        scheduler.resolve_required(&mut sim).await;
        assert_eq!(scheduler.slots[&AgentId(1)].next_request_id, 1);
        let first_tick_events = sim.tick();
        scheduler.observe_events(&first_tick_events, sim.tick_count());
        let events = sim.tick();
        scheduler.observe_events(&events, sim.tick_count());
        scheduler.resolve_required(&mut sim).await;
        assert_eq!(scheduler.slots[&AgentId(1)].next_request_id, 2);
    }

    #[tokio::test]
    async fn errors_and_rejections_use_tick_cooldowns_with_rejection_precedence() {
        let mut sim = simulation(1);
        let brain = Arc::new(DeterministicTestBrain::new(vec![], Duration::ZERO));
        let mut scheduler = CognitionScheduler::new(brain, 1, 1, 3, Duration::from_secs(1));
        scheduler.resolve_required(&mut sim).await;
        scheduler.resolve_required(&mut sim).await;
        assert_eq!(scheduler.slots[&AgentId(1)].next_request_id, 1);
        scheduler.observe_events(
            &[
                Event::ActivityCompleted { agent: AgentId(1) },
                Event::ActionRejected {
                    agent: AgentId(1),
                    action: crate::domain::action::Action::Eat,
                    reason: RejectionReason::NoFood,
                },
            ],
            0,
        );
        assert!(matches!(
            scheduler.slots[&AgentId(1)].state,
            SlotState::Cooldown { .. }
        ));
        for _ in 0..3 {
            sim.tick();
        }
        scheduler.resolve_required(&mut sim).await;
        assert_eq!(scheduler.slots[&AgentId(1)].next_request_id, 2);
    }

    #[tokio::test]
    async fn zero_configured_cooldown_still_waits_for_the_next_tick() {
        let mut sim = simulation(1);
        let brain = Arc::new(DeterministicTestBrain::new(vec![], Duration::ZERO));
        let mut scheduler = CognitionScheduler::new(brain, 1, 1, 0, Duration::from_secs(1));

        scheduler.resolve_required(&mut sim).await;
        scheduler.resolve_required(&mut sim).await;
        assert_eq!(scheduler.slots[&AgentId(1)].next_request_id, 1);

        sim.tick();
        scheduler.resolve_required(&mut sim).await;
        assert_eq!(scheduler.slots[&AgentId(1)].next_request_id, 2);
    }

    #[derive(Clone)]
    struct CountingBrain {
        current: Arc<AtomicUsize>,
        peak: Arc<AtomicUsize>,
    }
    impl Brain for CountingBrain {
        fn decide(
            &self,
            _: Observation,
        ) -> std::pin::Pin<
            Box<dyn std::future::Future<Output = Result<AgentDecision, BrainError>> + Send>,
        > {
            let current = Arc::clone(&self.current);
            let peak = Arc::clone(&self.peak);
            Box::pin(async move {
                let now = current.fetch_add(1, Ordering::SeqCst) + 1;
                peak.fetch_max(now, Ordering::SeqCst);
                tokio::time::sleep(Duration::from_millis(10)).await;
                current.fetch_sub(1, Ordering::SeqCst);
                Ok(AgentDecision {
                    action: DecisionAction::Rest,
                })
            })
        }
    }

    #[tokio::test]
    async fn requests_are_concurrent_and_limited() {
        let current = Arc::new(AtomicUsize::new(0));
        let peak = Arc::new(AtomicUsize::new(0));
        let brain = Arc::new(CountingBrain {
            current,
            peak: Arc::clone(&peak),
        });
        let mut sim = simulation(3);
        CognitionScheduler::new(brain, 1, 2, 1, Duration::from_secs(1))
            .resolve_required(&mut sim)
            .await;
        assert_eq!(peak.load(Ordering::SeqCst), 2);
    }
}
