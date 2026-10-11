use super::{AgentDecision, Brain, BrainResult, Observation};
use std::{collections::VecDeque, future::Future, pin::Pin, sync::Mutex, time::Duration};
use tokio::time::sleep;
#[derive(Debug)]
pub struct DeterministicTestBrain {
    responses: Mutex<VecDeque<(Duration, BrainResult<AgentDecision>)>>,
}
impl DeterministicTestBrain {
    pub fn new(decisions: Vec<AgentDecision>, delay: Duration) -> Self {
        Self {
            responses: Mutex::new(
                decisions
                    .into_iter()
                    .map(|decision| (delay, Ok(decision)))
                    .collect(),
            ),
        }
    }

    pub fn with_delays(decisions: Vec<(AgentDecision, Duration)>) -> Self {
        Self {
            responses: Mutex::new(
                decisions
                    .into_iter()
                    .map(|(decision, delay)| (delay, Ok(decision)))
                    .collect(),
            ),
        }
    }
}
impl Brain for DeterministicTestBrain {
    fn decide(
        &self,
        _observation: Observation,
    ) -> Pin<Box<dyn Future<Output = BrainResult<AgentDecision>> + Send>> {
        let response = self
            .responses
            .lock()
            .map_err(|_| super::BrainError("script lock poisoned".into()))
            .and_then(|mut responses| {
                responses
                    .pop_front()
                    .ok_or_else(|| super::BrainError("no scripted decision".into()))
            });
        Box::pin(async move {
            match response {
                Ok((delay, result)) => {
                    sleep(delay).await;
                    result
                }
                Err(error) => Err(error),
            }
        })
    }
}
