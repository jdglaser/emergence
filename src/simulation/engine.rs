use super::{
    event::{CriticalNeed, Event, RejectionReason},
    rules::Rules,
};
use crate::domain::{
    action::{Action, Direction, ResourceKind},
    agent::{Activity, Agent, AgentId},
    world::{Position, World},
};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone)]
struct Running {
    action: Action,
    remaining: u32,
    site: Option<Position>,
}

#[derive(Debug, Clone)]
struct ConflictRng {
    state: u64,
}

impl ConflictRng {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut value = self.state;
        value = (value ^ (value >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        value = (value ^ (value >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        value ^ (value >> 31)
    }

    fn bounded(&mut self, upper: u64) -> u64 {
        debug_assert!(upper > 0);
        let zone = u64::MAX - u64::MAX % upper;

        loop {
            let value = self.next_u64();
            if value < zone {
                return value % upper;
            }
        }
    }
}

/// Stable default seed used by `Simulation::new` for reproducible conflicts.
const DEFAULT_CONFLICT_SEED: u64 = 0x00E6_E46E_6365;
#[derive(Debug, Clone)]
pub struct Simulation {
    world: World,
    agents: BTreeMap<AgentId, Agent>,
    pub rules: Rules,
    pending: BTreeMap<AgentId, Action>,
    running: BTreeMap<AgentId, Running>,
    sites: BTreeSet<Position>,
    conflict_rng: ConflictRng,
    tick: u64,
}

impl Simulation {
    pub fn new(world: World, rules: Rules) -> Self {
        Self::with_seed(world, rules, DEFAULT_CONFLICT_SEED)
    }

    pub fn with_seed(world: World, rules: Rules, seed: u64) -> Self {
        Self {
            world,
            agents: BTreeMap::new(),
            rules,
            pending: BTreeMap::new(),
            running: BTreeMap::new(),
            sites: BTreeSet::new(),
            conflict_rng: ConflictRng::new(seed),
            tick: 0,
        }
    }

    pub fn add_agent(&mut self, agent: Agent, position: Position) -> bool {
        if !self.world.size.contains(position) || self.agents.contains_key(&agent.id) {
            return false;
        }
        self.world
            .agent_positions
            .insert(agent.id.clone(), position);
        self.agents.insert(agent.id.clone(), agent);
        true
    }

    pub fn world(&self) -> &World {
        &self.world
    }

    pub fn agent(&self, id: &AgentId) -> Option<&Agent> {
        self.agents.get(id)
    }

    pub fn tick_count(&self) -> u64 {
        self.tick
    }

    pub fn agents(&self) -> impl Iterator<Item = (&AgentId, &Agent)> {
        self.agents.iter()
    }

    pub fn position(&self, id: &AgentId) -> Option<Position> {
        self.world.agent_positions.get(id).copied()
    }

    pub fn is_eligible(&self, id: &AgentId) -> bool {
        self.agents
            .get(id)
            .is_some_and(|agent| agent.state.current_activity.is_none())
            && !self.pending.contains_key(id)
    }

    pub fn valid_move_directions(&self, id: &AgentId) -> Vec<Direction> {
        let Some(position) = self.position(id) else {
            return Vec::new();
        };
        [
            Direction::North,
            Direction::East,
            Direction::South,
            Direction::West,
        ]
        .into_iter()
        .filter(|direction| {
            step(position, direction).is_some_and(|target| self.world.size.contains(target))
        })
        .collect()
    }

    pub fn gatherable_resources(&self, id: &AgentId) -> Vec<ResourceKind> {
        self.position(id)
            .and_then(|position| self.world.resources.get(&position))
            .filter(|node| node.quantity > 0)
            .map(|node| vec![node.kind])
            .unwrap_or_default()
    }

    pub fn can_eat(&self, id: &AgentId) -> bool {
        self.agent(id).is_some_and(|agent| agent.inventory.food > 0)
    }

    pub fn can_build_shelter(&self, id: &AgentId) -> bool {
        let Some(position) = self.position(id) else {
            return false;
        };
        self.agent(id)
            .is_some_and(|agent| agent.inventory.wood >= self.rules.build_wood_cost)
            && !self.world.shelters.contains(&position)
            && !self.sites.contains(&position)
    }

    pub fn submit_action(&mut self, agent: AgentId, action: Action) -> Option<Event> {
        if !self.agents.contains_key(&agent) {
            return Some(Event::ActionRejected {
                agent,
                action,
                reason: RejectionReason::UnknownAgent,
            });
        }
        if self.running.contains_key(&agent) {
            return Some(Event::ActionRejected {
                agent,
                action,
                reason: RejectionReason::AgentBusy,
            });
        }
        if self.pending.contains_key(&agent) {
            return Some(Event::ActionRejected {
                agent,
                action,
                reason: RejectionReason::DuplicatePendingAction,
            });
        }
        self.pending.insert(agent, action);
        None
    }

    pub fn tick(&mut self) -> Vec<Event> {
        self.tick = self.tick.saturating_add(1);
        let mut events = Vec::new();
        let pending = std::mem::take(&mut self.pending);
        let mut builds = BTreeMap::new();
        for (id, action) in pending {
            if action == Action::BuildShelter {
                builds.insert(id, action);
            } else {
                self.start(id, action, &mut events);
            }
        }

        self.start_builds(builds, &mut events);
        self.survival(&mut events);
        self.advance_activities(&mut events);

        events
    }

    fn start_builds(&mut self, builds: BTreeMap<AgentId, Action>, events: &mut Vec<Event>) {
        let mut contenders = BTreeMap::<Position, Vec<AgentId>>::new();

        for (id, action) in builds {
            let position = self.position(&id).expect("known agent position");
            if self.agents[&id].inventory.wood < self.rules.build_wood_cost {
                reject(events, id, action, RejectionReason::InsufficientWood);
            } else if self.world.shelters.contains(&position) || self.sites.contains(&position) {
                reject(
                    events,
                    id,
                    action,
                    RejectionReason::ConstructionSiteReserved,
                );
            } else {
                contenders.entry(position).or_default().push(id);
            }
        }

        for (position, ids) in contenders {
            let winner = if ids.len() == 1 {
                ids[0].clone()
            } else {
                self.select_weighted(ids.iter().cloned().map(|id| (id, 1)))
            };

            for id in ids {
                if id == winner {
                    self.start_build(id, position, events);
                } else {
                    reject(
                        events,
                        id,
                        Action::BuildShelter,
                        RejectionReason::ConstructionSiteReserved,
                    );
                }
            }
        }
    }

    fn start_build(&mut self, id: AgentId, position: Position, events: &mut Vec<Event>) {
        self.agents
            .get_mut(&id)
            .expect("known agent")
            .inventory
            .wood -= self.rules.build_wood_cost;
        self.sites.insert(position);
        self.agents
            .get_mut(&id)
            .expect("known agent")
            .state
            .current_activity = Some(Activity::BuildingShelter);
        self.running.insert(
            id.clone(),
            Running {
                action: Action::BuildShelter,
                remaining: self.rules.build_ticks,
                site: Some(position),
            },
        );
        events.push(Event::ActivityStarted { agent: id });
    }

    fn start(&mut self, id: AgentId, action: Action, events: &mut Vec<Event>) {
        let pos = *self
            .world
            .agent_positions
            .get(&id)
            .expect("known agent position");
        let (activity, remaining, site) = match &action {
            Action::Move(direction) => {
                let Some(target) = step(pos, direction) else {
                    reject(events, id, action, RejectionReason::InvalidMove);
                    return;
                };
                if !self.world.size.contains(target) {
                    reject(events, id, action, RejectionReason::InvalidMove);
                    return;
                }
                (Activity::Moving, self.rules.move_ticks, None)
            }
            Action::Gather(kind) => match self.world.resources.get(&pos) {
                Some(n) if n.kind == *kind && n.quantity > 0 => {
                    (Activity::Gathering, self.rules.gather_ticks, None)
                }
                _ => {
                    reject(events, id, action, RejectionReason::ResourceUnavailable);
                    return;
                }
            },
            Action::BuildShelter => unreachable!("shelter builds are resolved as a group"),
            Action::Rest => (Activity::Resting, self.rules.rest_ticks, None),
            Action::Eat => {
                let a = self.agents.get_mut(&id).expect("known");
                if a.inventory.food == 0 {
                    reject(events, id, action, RejectionReason::NoFood);
                    return;
                }
                a.inventory.food -= 1;
                a.needs.hunger = a
                    .needs
                    .hunger
                    .saturating_sub(self.rules.eat_hunger_reduction);
                events.push(Event::Ate { agent: id });
                return;
            }
            Action::Speak { .. } | Action::GiveResources { .. } => {
                reject(events, id, action, RejectionReason::UnsupportedAction);
                return;
            }
        };
        self.agents
            .get_mut(&id)
            .expect("known")
            .state
            .current_activity = Some(activity);
        self.running.insert(
            id.clone(),
            Running {
                action,
                remaining,
                site,
            },
        );
        events.push(Event::ActivityStarted { agent: id });
    }

    fn advance_activities(&mut self, events: &mut Vec<Event>) {
        let ids: Vec<_> = self.running.keys().cloned().collect();
        let mut ready_gathers =
            BTreeMap::<(Position, ResourceKind), Vec<(AgentId, Running)>>::new();

        for id in ids {
            let mut running = self.running.remove(&id).expect("running activity");
            running.remaining = running.remaining.saturating_sub(1);
            if running.remaining > 0 {
                self.running.insert(id, running);
                continue;
            }

            let position = self.position(&id).expect("known agent position");
            if let Action::Gather(kind) = &running.action {
                ready_gathers
                    .entry((position, *kind))
                    .or_default()
                    .push((id, running));
            } else {
                self.complete_activity(id, running, events);
            }
        }

        self.complete_gathers(ready_gathers, events);
    }

    fn complete_gathers(
        &mut self,
        gathers: BTreeMap<(Position, ResourceKind), Vec<(AgentId, Running)>>,
        events: &mut Vec<Event>,
    ) {
        for ((position, kind), contenders) in gathers {
            let available = self
                .world
                .resources
                .get(&position)
                .filter(|node| node.kind == kind)
                .map_or(0, |node| node.quantity);
            let winners = if available >= contenders.len() as u32 {
                contenders.iter().map(|(id, _)| id.clone()).collect()
            } else {
                self.select_without_replacement(
                    contenders.iter().map(|(id, _)| (id.clone(), 1)),
                    available as usize,
                )
            };

            for (id, running) in contenders {
                if winners.contains(&id) {
                    let resource = self
                        .world
                        .resources
                        .get_mut(&position)
                        .expect("available resource");
                    resource.quantity -= 1;
                    self.agents
                        .get_mut(&id)
                        .expect("known agent")
                        .inventory
                        .add(kind);
                    events.push(Event::Gathered {
                        agent: id.clone(),
                        resource: kind,
                    });
                } else {
                    reject(
                        events,
                        id.clone(),
                        running.action,
                        RejectionReason::ResourceUnavailable,
                    );
                }

                self.finish_activity(id, events);
            }
        }
    }

    fn complete_activity(&mut self, id: AgentId, run: Running, events: &mut Vec<Event>) {
        let pos = *self.world.agent_positions.get(&id).expect("pos");
        match &run.action {
            Action::Move(direction) => {
                self.world
                    .agent_positions
                    .insert(id.clone(), step(pos, direction).expect("validated move"));
            }
            Action::Gather(_) => unreachable!("gathers are resolved as a group"),
            Action::BuildShelter => {
                let site = run.site.expect("build site");
                self.sites.remove(&site);
                self.world.shelters.insert(site);
                events.push(Event::ShelterBuilt {
                    agent: id.clone(),
                    position: site,
                });
            }
            Action::Rest => {}
            _ => {}
        }
        self.finish_activity(id, events);
    }

    fn finish_activity(&mut self, id: AgentId, events: &mut Vec<Event>) {
        self.agents
            .get_mut(&id)
            .expect("known")
            .state
            .current_activity = None;
        events.push(Event::ActivityCompleted { agent: id });
    }

    fn select_without_replacement(
        &mut self,
        contenders: impl IntoIterator<Item = (AgentId, u32)>,
        count: usize,
    ) -> BTreeSet<AgentId> {
        let mut remaining: Vec<_> = contenders.into_iter().collect();
        let mut winners = BTreeSet::new();

        for _ in 0..count.min(remaining.len()) {
            let winner = self.select_weighted(remaining.iter().cloned());
            remaining.retain(|(id, _)| id != &winner);
            winners.insert(winner);
        }

        winners
    }

    fn select_weighted(&mut self, contenders: impl IntoIterator<Item = (AgentId, u32)>) -> AgentId {
        let contenders: Vec<_> = contenders.into_iter().collect();
        debug_assert!(!contenders.is_empty());
        let total = contenders
            .iter()
            .map(|(_, weight)| u64::from(*weight))
            .sum::<u64>();
        debug_assert!(total > 0);
        let mut selected = self.conflict_rng.bounded(total);

        for (id, weight) in contenders {
            if selected < u64::from(weight) {
                return id;
            }
            selected -= u64::from(weight);
        }

        unreachable!("positive contender weights must select a winner")
    }

    fn survival(&mut self, events: &mut Vec<Event>) {
        for (id, a) in &mut self.agents {
            let previous = a.needs.clone();
            a.needs.hunger = a.needs.hunger.saturating_add(self.rules.hunger_per_tick);
            if a.state.current_activity.is_some() {
                if a.state.current_activity == Some(Activity::Resting) {
                    a.needs.energy = a
                        .needs
                        .energy
                        .saturating_add(self.rules.rest_energy_per_tick)
                } else {
                    a.needs.energy = a
                        .needs
                        .energy
                        .saturating_sub(self.rules.active_energy_per_tick)
                }
            }
            if a.needs.hunger >= 100 {
                a.needs.health = a.needs.health.saturating_sub(1)
            }
            if self
                .world
                .shelters
                .contains(&self.world.agent_positions[id])
            {
                a.needs.health = a
                    .needs
                    .health
                    .saturating_add(self.rules.shelter_health_per_tick)
            }
            if previous.hunger < 80 && a.needs.hunger >= 80 {
                events.push(Event::CriticalNeedReached {
                    agent: id.clone(),
                    need: CriticalNeed::Hunger,
                });
            }
            if previous.energy > 20 && a.needs.energy <= 20 {
                events.push(Event::CriticalNeedReached {
                    agent: id.clone(),
                    need: CriticalNeed::Energy,
                });
            }
            if previous.health > 20 && a.needs.health <= 20 {
                events.push(Event::CriticalNeedReached {
                    agent: id.clone(),
                    need: CriticalNeed::Health,
                });
            }
        }
    }
}

fn step(pos: Position, d: &Direction) -> Option<Position> {
    match d {
        Direction::North => Some(Position {
            x: pos.x,
            y: pos.y.checked_sub(1)?,
        }),
        Direction::South => Some(Position {
            x: pos.x,
            y: pos.y.saturating_add(1),
        }),
        Direction::West => Some(Position {
            x: pos.x.checked_sub(1)?,
            y: pos.y,
        }),
        Direction::East => Some(Position {
            x: pos.x.saturating_add(1),
            y: pos.y,
        }),
    }
}

fn reject(events: &mut Vec<Event>, agent: AgentId, action: Action, reason: RejectionReason) {
    events.push(Event::ActionRejected {
        agent,
        action,
        reason,
    });
}
trait Add {
    fn add(&mut self, k: ResourceKind);
}
impl Add for crate::domain::agent::Inventory {
    fn add(&mut self, k: ResourceKind) {
        match k {
            ResourceKind::Food => self.food += 1,
            ResourceKind::Wood => self.wood += 1,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::{
        agent::{Inventory, Personality, SurvivalNeeds, TraitLevel},
        world::{GridSize, ResourceNode},
    };

    fn agent(id: u64, wood: u32) -> Agent {
        Agent {
            id: AgentId(id),
            name: format!("Agent {id}"),
            personality: Personality {
                sociability: TraitLevel::Medium,
                cooperation: TraitLevel::Medium,
                risk_tolerance: TraitLevel::Medium,
            },
            needs: SurvivalNeeds {
                hunger: 0,
                energy: 10,
                health: 10,
            },
            inventory: Inventory { food: 0, wood },
            state: crate::domain::agent::AgentState {
                current_activity: None,
            },
        }
    }

    fn sim() -> Simulation {
        Simulation::new(
            World::new(GridSize {
                width: 3,
                height: 3,
            }),
            Rules::default(),
        )
    }

    fn sim_with_seed(seed: u64) -> Simulation {
        Simulation::with_seed(
            World::new(GridSize {
                width: 3,
                height: 3,
            }),
            Rules::default(),
            seed,
        )
    }

    fn contested_gather(seed: u64, quantity: u32) -> Simulation {
        let mut simulation = sim_with_seed(seed);
        let position = Position { x: 1, y: 1 };
        simulation.add_agent(agent(1, 0), position);
        simulation.add_agent(agent(2, 0), position);
        simulation.world.resources.insert(
            position,
            ResourceNode {
                kind: ResourceKind::Wood,
                quantity,
            },
        );
        simulation.submit_action(AgentId(1), Action::Gather(ResourceKind::Wood));
        simulation.submit_action(AgentId(2), Action::Gather(ResourceKind::Wood));
        simulation
    }

    #[test]
    fn movement_is_deterministic_and_rejects_edges() {
        let mut simulation = sim();
        assert!(simulation.add_agent(agent(2, 0), Position { x: 1, y: 1 }));
        assert!(simulation.add_agent(agent(1, 0), Position { x: 0, y: 0 }));
        assert_eq!(
            simulation.submit_action(AgentId(2), Action::Move(Direction::East)),
            None
        );
        simulation.tick();
        assert_eq!(
            simulation.world.agent_positions[&AgentId(2)],
            Position { x: 2, y: 1 }
        );
        simulation.submit_action(AgentId(2), Action::Move(Direction::East));
        assert!(matches!(
            simulation.tick().as_slice(),
            [Event::ActionRejected {
                reason: RejectionReason::InvalidMove,
                ..
            }]
        ));
    }

    #[test]
    fn gathering_revalidates_resource_at_completion() {
        let mut simulation = sim();
        simulation.add_agent(agent(1, 0), Position { x: 1, y: 1 });
        simulation.add_agent(agent(2, 0), Position { x: 1, y: 1 });
        simulation.world.resources.insert(
            Position { x: 1, y: 1 },
            ResourceNode {
                kind: ResourceKind::Wood,
                quantity: 1,
            },
        );
        simulation.submit_action(AgentId(1), Action::Gather(ResourceKind::Wood));
        simulation.submit_action(AgentId(2), Action::Gather(ResourceKind::Wood));
        simulation.tick();
        assert!(simulation.tick().iter().any(|event| matches!(
            event,
            Event::ActionRejected {
                reason: RejectionReason::ResourceUnavailable,
                ..
            }
        )));
        assert_eq!(simulation.agents[&AgentId(1)].inventory.wood, 1);
        assert_eq!(simulation.agents[&AgentId(2)].inventory.wood, 0);
    }

    #[test]
    fn contested_gather_selects_one_winner_and_completes_every_activity() {
        let mut simulation = contested_gather(7, 1);
        simulation.tick();
        let events = simulation.tick();

        assert_eq!(
            events
                .iter()
                .filter(|event| matches!(event, Event::Gathered { .. }))
                .count(),
            1
        );
        assert_eq!(
            events
                .iter()
                .filter(|event| matches!(event, Event::ActivityCompleted { .. }))
                .count(),
            2
        );
        assert_eq!(
            simulation.agents[&AgentId(1)].inventory.wood
                + simulation.agents[&AgentId(2)].inventory.wood,
            1
        );
    }

    #[test]
    fn equal_weight_contenders_can_each_win_across_fixed_seeds() {
        let mut winners = BTreeSet::new();

        for seed in 0..64 {
            let mut simulation = contested_gather(seed, 1);
            simulation.tick();
            let events = simulation.tick();
            let winner = events.iter().find_map(|event| match event {
                Event::Gathered { agent, .. } => Some(agent.clone()),
                _ => None,
            });
            winners.insert(winner.expect("one gather winner"));
        }

        assert_eq!(winners, BTreeSet::from([AgentId(1), AgentId(2)]));
    }

    #[test]
    fn same_seed_reproduces_contested_gather_outcome() {
        let mut first = contested_gather(42, 1);
        let mut second = contested_gather(42, 1);

        let first_start = first.tick();
        let second_start = second.tick();
        assert_eq!(first_start, second_start);
        assert_eq!(first.tick(), second.tick());
        assert_eq!(first.agents, second.agents);
        assert_eq!(first.world.resources, second.world.resources);
    }

    #[test]
    fn sufficient_gather_resource_preserves_all_completions() {
        let mut simulation = contested_gather(7, 2);
        simulation.tick();
        let events = simulation.tick();

        assert_eq!(
            events
                .iter()
                .filter(|event| matches!(event, Event::Gathered { .. }))
                .count(),
            2
        );
        assert!(!events.iter().any(|event| matches!(
            event,
            Event::ActionRejected {
                reason: RejectionReason::ResourceUnavailable,
                ..
            }
        )));
    }

    #[test]
    fn busy_agents_are_rejected_and_rest_changes_needs() {
        let mut simulation = sim();
        simulation.add_agent(agent(1, 0), Position { x: 1, y: 1 });
        simulation.submit_action(AgentId(1), Action::Rest);
        simulation.tick();
        assert!(matches!(
            simulation.submit_action(AgentId(1), Action::Rest),
            Some(Event::ActionRejected {
                reason: RejectionReason::AgentBusy,
                ..
            })
        ));
        simulation.tick();
        let a = &simulation.agents[&AgentId(1)];
        assert_eq!(a.state.current_activity, None);
        assert!(a.needs.energy > 10);
        assert!(a.needs.hunger > 0);
    }

    #[test]
    fn building_deducts_wood_and_reserves_site() {
        let mut simulation = sim();
        simulation.add_agent(agent(1, 3), Position { x: 1, y: 1 });
        simulation.add_agent(agent(2, 3), Position { x: 1, y: 1 });
        simulation.submit_action(AgentId(1), Action::BuildShelter);
        simulation.tick();
        assert_eq!(simulation.agents[&AgentId(1)].inventory.wood, 0);
        simulation.submit_action(AgentId(2), Action::BuildShelter);
        assert!(simulation.tick().iter().any(|event| matches!(
            event,
            Event::ActionRejected {
                reason: RejectionReason::ConstructionSiteReserved,
                ..
            }
        )));
    }

    #[test]
    fn contested_build_selects_one_builder_and_rejects_the_other() {
        let mut simulation = sim_with_seed(11);
        let position = Position { x: 1, y: 1 };
        simulation.add_agent(agent(1, 3), position);
        simulation.add_agent(agent(2, 3), position);
        simulation.submit_action(AgentId(1), Action::BuildShelter);
        simulation.submit_action(AgentId(2), Action::BuildShelter);
        let events = simulation.tick();

        assert_eq!(
            events
                .iter()
                .filter(|event| matches!(event, Event::ActivityStarted { .. }))
                .count(),
            1
        );
        assert_eq!(
            events
                .iter()
                .filter(|event| matches!(
                    event,
                    Event::ActionRejected {
                        reason: RejectionReason::ConstructionSiteReserved,
                        ..
                    }
                ))
                .count(),
            1
        );
        assert_eq!(
            simulation.agents[&AgentId(1)].inventory.wood
                + simulation.agents[&AgentId(2)].inventory.wood,
            3
        );
    }

    #[test]
    fn north_and_west_edges_are_invalid_moves() {
        let mut simulation = sim();
        simulation.add_agent(agent(1, 0), Position { x: 0, y: 0 });
        simulation.submit_action(AgentId(1), Action::Move(Direction::North));
        assert!(matches!(
            simulation.tick().as_slice(),
            [Event::ActionRejected {
                reason: RejectionReason::InvalidMove,
                ..
            }]
        ));
        simulation.submit_action(AgentId(1), Action::Move(Direction::West));
        assert!(matches!(
            simulation.tick().as_slice(),
            [Event::ActionRejected {
                reason: RejectionReason::InvalidMove,
                ..
            }]
        ));
    }

    #[test]
    fn final_activity_tick_applies_rest_energy_and_critical_events_do_not_repeat() {
        let mut simulation = sim();
        let mut subject = agent(1, 0);
        subject.needs.energy = 20;
        subject.needs.hunger = 79;
        simulation.add_agent(subject, Position { x: 1, y: 1 });
        simulation.submit_action(AgentId(1), Action::Rest);
        let first = simulation.tick();
        assert_eq!(
            simulation.agent(&AgentId(1)).expect("agent").needs.energy,
            23
        );
        assert!(first.iter().any(|event| matches!(
            event,
            Event::CriticalNeedReached {
                need: CriticalNeed::Hunger,
                ..
            }
        )));
        let second = simulation.tick();
        assert_eq!(
            simulation.agent(&AgentId(1)).expect("agent").needs.energy,
            26
        );
        assert!(!second.iter().any(|event| matches!(
            event,
            Event::CriticalNeedReached {
                need: CriticalNeed::Hunger,
                ..
            }
        )));
    }
}
