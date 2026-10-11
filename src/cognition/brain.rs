use super::{AgentDecision, Observation};
use std::{future::Future, pin::Pin};
pub type BrainResult<T> = Result<T, BrainError>;
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BrainError(pub String);
pub trait Brain: Send + Sync {
    fn decide(
        &self,
        observation: Observation,
    ) -> Pin<Box<dyn Future<Output = BrainResult<AgentDecision>> + Send>>;
}
