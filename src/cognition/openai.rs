use super::{AgentDecision, Brain, BrainError, BrainResult, Observation};
use reqwest::Client;
use schemars::schema_for;
use serde_json::{Value, json};
use std::{future::Future, pin::Pin, time::Duration};
#[derive(Clone)]
pub struct OpenAiBrain {
    client: Client,
    api_key: String,
    model: String,
}
impl OpenAiBrain {
    pub fn new(api_key: String, model: String, timeout: Duration) -> Result<Self, BrainError> {
        let client = Client::builder()
            .timeout(timeout)
            .build()
            .map_err(|e| BrainError(e.to_string()))?;
        Ok(Self {
            client,
            api_key,
            model,
        })
    }

    pub fn strict_schema() -> Value {
        let mut value =
            serde_json::to_value(schema_for!(AgentDecision)).expect("schema serialization");
        make_strict(&mut value);
        value
    }

    pub fn parse_response(value: &Value) -> BrainResult<AgentDecision> {
        let output = value
            .get("output")
            .and_then(Value::as_array)
            .ok_or_else(|| BrainError("missing output".into()))?;
        for item in output {
            if let Some(contents) = item.get("content").and_then(Value::as_array) {
                for content in contents {
                    if content.get("type").and_then(Value::as_str) == Some("output_text")
                        && let Some(text) = content.get("text").and_then(Value::as_str)
                    {
                        return serde_json::from_str(text).map_err(|e| BrainError(e.to_string()));
                    }
                }
            }
        }
        Err(BrainError("no structured output text".into()))
    }

    fn prompt(observation: &Observation) -> String {
        format!(
            "You are a survival agent. Prioritize finding food, maintaining energy, and constructing shelter. Propose one action only. State: position=({}, {}), hunger={}, energy={}, health={}, food={}, wood={}",
            observation.position.x,
            observation.position.y,
            observation.needs.hunger,
            observation.needs.energy,
            observation.needs.health,
            observation.inventory.food,
            observation.inventory.wood
        )
    }
}

fn make_strict(value: &mut Value) {
    match value {
        Value::Object(map) => {
            if map.contains_key("properties") {
                map.insert("additionalProperties".into(), Value::Bool(false));
            }
            for child in map.values_mut() {
                make_strict(child);
            }
        }
        Value::Array(items) => {
            for item in items {
                make_strict(item);
            }
        }
        _ => {}
    }
}
impl Brain for OpenAiBrain {
    fn decide(
        &self,
        observation: Observation,
    ) -> Pin<Box<dyn Future<Output = BrainResult<AgentDecision>> + Send>> {
        let client = self.client.clone();
        let key = self.api_key.clone();
        let model = self.model.clone();
        Box::pin(async move {
            let body = json!({"model":model,"input":[{"role":"user","content":[{"type":"input_text","text":OpenAiBrain::prompt(&observation)}]}],"text":{"format":{"type":"json_schema","name":"agent_decision","strict":true,"schema":OpenAiBrain::strict_schema()}}});
            let response = client
                .post("https://api.openai.com/v1/responses")
                .bearer_auth(key)
                .json(&body)
                .send()
                .await
                .map_err(|e| BrainError(e.to_string()))?;
            let value = response
                .error_for_status()
                .map_err(|e| BrainError(e.to_string()))?
                .json::<Value>()
                .await
                .map_err(|e| BrainError(e.to_string()))?;
            OpenAiBrain::parse_response(&value)
        })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn schema_is_strict_object() {
        let schema = OpenAiBrain::strict_schema();
        assert_eq!(schema["additionalProperties"], false);
        assert!(schema.get("$schema").is_some());
        assert!(strict_objects(&schema));
    }

    #[test]
    fn parses_responses_output() {
        let value = json!({"output":[{"content":[{"type":"output_text","text":"{\"action\":{\"kind\":\"rest\"}}"}]}]});
        assert!(matches!(
            OpenAiBrain::parse_response(&value),
            Ok(AgentDecision {
                action: super::super::DecisionAction::Rest
            })
        ));
    }

    fn strict_objects(value: &Value) -> bool {
        match value {
            Value::Object(map) => {
                (!map.contains_key("properties")
                    || map.get("additionalProperties") == Some(&Value::Bool(false)))
                    && map.values().all(strict_objects)
            }
            Value::Array(items) => items.iter().all(strict_objects),
            _ => true,
        }
    }
}
