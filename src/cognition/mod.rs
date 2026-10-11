//! Cognition proposes commands; it never mutates simulation state directly.
mod brain;
mod decision;
mod observation;
mod openai;
mod scheduler;
mod test_brain;

pub use brain::{Brain, BrainError, BrainResult};
pub use decision::{AgentDecision, DecisionAction};
pub use observation::{Observation, ObservedAgent, ObservedResource, ObservedShelter};
pub use openai::OpenAiBrain;
pub use scheduler::CognitionScheduler;
pub use test_brain::DeterministicTestBrain;
