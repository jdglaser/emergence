use std::collections::{BTreeMap, BTreeSet};

use super::{action::ResourceKind, agent::AgentId};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Position {
    pub x: u32,
    pub y: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GridSize {
    pub width: u32,
    pub height: u32,
}

impl GridSize {
    pub fn contains(self, position: Position) -> bool {
        position.x < self.width && position.y < self.height
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResourceNode {
    pub kind: ResourceKind,
    pub quantity: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Shelter {
    pub position: Position,
    pub builder: AgentId,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct World {
    pub size: GridSize,
    pub agent_positions: BTreeMap<AgentId, Position>,
    pub resources: BTreeMap<Position, ResourceNode>,
    pub shelters: BTreeSet<Position>,
}

impl World {
    pub fn new(size: GridSize) -> Self {
        Self {
            size,
            agent_positions: BTreeMap::new(),
            resources: BTreeMap::new(),
            shelters: BTreeSet::new(),
        }
    }
}
