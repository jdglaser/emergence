use crate::{
    domain::{
        action::ResourceKind,
        agent::{AgentId, Inventory, Personality, SurvivalNeeds},
        world::Position,
    },
    simulation::engine::Simulation,
};
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Observation {
    pub agent: AgentId,
    pub name: String,
    pub personality: Personality,
    pub needs: SurvivalNeeds,
    pub inventory: Inventory,
    pub position: Position,
    pub nearby_agents: Vec<ObservedAgent>,
    pub nearby_resources: Vec<ObservedResource>,
    pub shelters: Vec<ObservedShelter>,
    pub available_actions: Vec<&'static str>,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObservedAgent {
    pub id: AgentId,
    pub name: String,
    pub position: Position,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObservedResource {
    pub position: Position,
    pub kind: ResourceKind,
    pub quantity: u32,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObservedShelter {
    pub position: Position,
}
impl Observation {
    pub fn from_simulation(sim: &Simulation, id: &AgentId, radius: u32) -> Option<Self> {
        let a = sim.agent(id)?;
        let p = sim.position(id)?;
        let nearby_agents = sim
            .agents()
            .filter_map(|(other, x)| {
                let op = sim.position(other)?;
                (other != id && distance(p, op) <= radius).then(|| ObservedAgent {
                    id: other.clone(),
                    name: x.name.clone(),
                    position: op,
                })
            })
            .collect();
        let nearby_resources = sim
            .world()
            .resources
            .iter()
            .filter(|(op, _)| distance(p, **op) <= radius)
            .map(|(position, node)| ObservedResource {
                position: *position,
                kind: node.kind,
                quantity: node.quantity,
            })
            .collect();
        let shelters = sim
            .world()
            .shelters
            .iter()
            .filter(|op| distance(p, **op) <= radius)
            .map(|position| ObservedShelter {
                position: *position,
            })
            .collect();
        let mut available_actions = vec!["rest"];
        if !sim.valid_move_directions(id).is_empty() {
            available_actions.push("move");
        }
        if !sim.gatherable_resources(id).is_empty() {
            available_actions.push("gather");
        }
        if sim.can_eat(id) {
            available_actions.push("eat");
        }
        if sim.can_build_shelter(id) {
            available_actions.push("build_shelter");
        }
        Some(Self {
            agent: id.clone(),
            name: a.name.clone(),
            personality: a.personality.clone(),
            needs: a.needs.clone(),
            inventory: a.inventory.clone(),
            position: p,
            nearby_agents,
            nearby_resources,
            shelters,
            available_actions,
        })
    }
}

fn distance(a: Position, b: Position) -> u32 {
    a.x.abs_diff(b.x).saturating_add(a.y.abs_diff(b.y))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        domain::{
            agent::{Agent, AgentState, Inventory, Personality, SurvivalNeeds, TraitLevel},
            world::{GridSize, ResourceNode, World},
        },
        simulation::{engine::Simulation, rules::Rules},
    };
    fn agent(id: u64) -> Agent {
        Agent {
            id: AgentId(id),
            name: format!("agent-{id}"),
            personality: Personality {
                sociability: TraitLevel::Low,
                cooperation: TraitLevel::Medium,
                risk_tolerance: TraitLevel::High,
            },
            needs: SurvivalNeeds {
                hunger: 1,
                energy: 2,
                health: 3,
            },
            inventory: Inventory { food: 4, wood: 5 },
            state: AgentState {
                current_activity: None,
            },
        }
    }

    #[test]
    fn observation_is_radius_limited_and_includes_shelters() {
        let mut world = World::new(GridSize {
            width: 10,
            height: 10,
        });
        world.resources.insert(
            Position { x: 2, y: 1 },
            ResourceNode {
                kind: ResourceKind::Food,
                quantity: 1,
            },
        );
        world.resources.insert(
            Position { x: 9, y: 9 },
            ResourceNode {
                kind: ResourceKind::Wood,
                quantity: 1,
            },
        );
        world.shelters.insert(Position { x: 1, y: 2 });
        let mut sim = Simulation::new(world, Rules::default());
        assert!(sim.add_agent(agent(1), Position { x: 1, y: 1 }));
        assert!(sim.add_agent(agent(2), Position { x: 2, y: 1 }));
        assert!(sim.add_agent(agent(3), Position { x: 8, y: 8 }));
        let observed = Observation::from_simulation(&sim, &AgentId(1), 2).expect("agent exists");
        assert_eq!(observed.nearby_agents.len(), 1);
        assert_eq!(observed.nearby_resources.len(), 1);
        assert_eq!(observed.shelters.len(), 1);
        assert_eq!(
            observed.available_actions,
            vec!["rest", "move", "eat", "build_shelter"]
        );
    }
}
