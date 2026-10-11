use crate::domain::{
    action::{Action, ResourceKind},
    agent::AgentId,
    world::Position,
};
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RejectionReason {
    UnknownAgent,
    AgentBusy,
    DuplicatePendingAction,
    InvalidMove,
    ResourceUnavailable,
    InsufficientWood,
    ConstructionSiteReserved,
    UnsupportedAction,
    NoFood,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CriticalNeed {
    Hunger,
    Energy,
    Health,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Event {
    ActionRejected {
        agent: AgentId,
        action: Action,
        reason: RejectionReason,
    },
    ActivityStarted {
        agent: AgentId,
    },
    ActivityCompleted {
        agent: AgentId,
    },
    Gathered {
        agent: AgentId,
        resource: ResourceKind,
    },
    ShelterBuilt {
        agent: AgentId,
        position: Position,
    },
    Ate {
        agent: AgentId,
    },
    CriticalNeedReached {
        agent: AgentId,
        need: CriticalNeed,
    },
}
