use super::agent::AgentId;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Action {
    Move(Direction),
    Gather(ResourceKind),
    Eat,
    BuildShelter,
    Speak {
        message: String,
        recipient: Vec<AgentId>,
    },
    GiveResources {
        recipient: AgentId,
        resource: ResourceKind,
        amount: u32,
    },
    Rest,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Direction {
    North,
    East,
    South,
    West,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum ResourceKind {
    Food,
    Wood,
}

#[cfg(test)]
mod tests {
    use super::{Action, ResourceKind};
    use crate::domain::agent::AgentId;

    #[test]
    fn speech_has_explicit_recipients() {
        let action = Action::Speak {
            message: "We should gather wood.".to_owned(),
            recipient: vec![AgentId(2), AgentId(3)],
        };

        assert_eq!(
            action,
            Action::Speak {
                message: "We should gather wood.".to_owned(),
                recipient: vec![AgentId(2), AgentId(3)],
            }
        );
    }

    #[test]
    fn resource_gift_identifies_recipient_and_resource() {
        let action = Action::GiveResources {
            recipient: AgentId(7),
            resource: ResourceKind::Food,
            amount: 2,
        };

        assert_eq!(
            action,
            Action::GiveResources {
                recipient: AgentId(7),
                resource: ResourceKind::Food,
                amount: 2,
            }
        );
    }
}
