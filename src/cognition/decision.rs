use crate::domain::action::{Action, Direction, ResourceKind};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
pub struct AgentDecision {
    pub action: DecisionAction,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum DecisionAction {
    Move(DirectionDto),
    Gather(ResourceDto),
    Eat,
    BuildShelter,
    Rest,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum DirectionDto {
    North,
    East,
    South,
    West,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ResourceDto {
    Food,
    Wood,
}
impl From<DirectionDto> for Direction {
    fn from(v: DirectionDto) -> Self {
        match v {
            DirectionDto::North => Self::North,
            DirectionDto::East => Self::East,
            DirectionDto::South => Self::South,
            DirectionDto::West => Self::West,
        }
    }
}
impl From<ResourceDto> for ResourceKind {
    fn from(v: ResourceDto) -> Self {
        match v {
            ResourceDto::Food => Self::Food,
            ResourceDto::Wood => Self::Wood,
        }
    }
}
impl AgentDecision {
    pub fn into_action(self) -> Action {
        use DecisionAction::*;
        match self.action {
            Move(v) => Action::Move(v.into()),
            Gather(v) => Action::Gather(v.into()),
            Eat => Action::Eat,
            BuildShelter => Action::BuildShelter,
            Rest => Action::Rest,
        }
    }
}
