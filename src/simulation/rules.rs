#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rules {
    pub move_ticks: u32,
    pub gather_ticks: u32,
    pub build_ticks: u32,
    pub rest_ticks: u32,
    pub hunger_per_tick: u8,
    pub active_energy_per_tick: u8,
    pub rest_energy_per_tick: u8,
    pub eat_hunger_reduction: u8,
    pub shelter_health_per_tick: u8,
    pub build_wood_cost: u32,
}
impl Default for Rules {
    fn default() -> Self {
        Self {
            move_ticks: 1,
            gather_ticks: 2,
            build_ticks: 3,
            rest_ticks: 2,
            hunger_per_tick: 1,
            active_energy_per_tick: 1,
            rest_energy_per_tick: 3,
            eat_hunger_reduction: 20,
            shelter_health_per_tick: 1,
            build_wood_cost: 3,
        }
    }
}
