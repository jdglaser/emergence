#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Agent {
    pub id: AgentId,
    pub name: String,
    pub personality: Personality,
    pub needs: SurvivalNeeds,
    pub inventory: Inventory,
    pub state: AgentState,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct AgentId(pub u64);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Personality {
    pub sociability: TraitLevel,
    pub cooperation: TraitLevel,
    pub risk_tolerance: TraitLevel,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TraitLevel {
    Low,
    Medium,
    High,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SurvivalNeeds {
    pub hunger: u8,
    pub energy: u8,
    pub health: u8,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Inventory {
    pub food: u32,
    pub wood: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgentState {
    pub current_activity: Option<Activity>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Activity {
    Gathering,
    Moving,
    BuildingShelter,
    Resting,
}

#[cfg(test)]
mod tests {
    use super::{
        Activity, Agent, AgentId, AgentState, Inventory, Personality, SurvivalNeeds, TraitLevel,
    };

    fn personality() -> Personality {
        Personality {
            sociability: TraitLevel::Medium,
            cooperation: TraitLevel::High,
            risk_tolerance: TraitLevel::Low,
        }
    }

    #[test]
    fn agent_contains_its_domain_data() {
        let agent = Agent {
            id: AgentId(1),
            name: "Aster".to_owned(),
            personality: personality(),
            needs: SurvivalNeeds {
                hunger: 10,
                energy: 90,
                health: 100,
            },
            inventory: Inventory { food: 3, wood: 1 },
            state: AgentState {
                current_activity: None,
            },
        };

        assert_eq!(agent.id, AgentId(1));
        assert_eq!(agent.name, "Aster");
        assert_eq!(agent.inventory.food, 3);
    }

    #[test]
    fn state_distinguishes_idle_and_active_agents() {
        let idle = AgentState {
            current_activity: None,
        };
        let active = AgentState {
            current_activity: Some(Activity::Gathering),
        };

        assert_ne!(idle, active);
        assert_eq!(active.current_activity, Some(Activity::Gathering));
    }
}
