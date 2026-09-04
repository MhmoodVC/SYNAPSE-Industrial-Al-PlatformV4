export interface HealthResponse {
  status: string;
  tests_passed: string;
  dataset_ready: boolean;
  total_runs: number;
  total_samples_per_run: number;
}

export interface RunItem {
  run_id: string;
  label: string;
  fault_type?: string;
  length?: number;
}

export interface TimelineResponse {
  available_runs: (string | RunItem)[];
  runs?: string[];
  labels?: string[];
  default_run: string;
  sample_length: number;
  total_runs?: number;
}

export interface TelemetryRecord {
  timestamp: string;
  run_id: string;
  step: number;
  vibration: number;
  motor_current: number;
  temperature: number;
  pressure: number;
  flow: number;
  operating_load: number;
  vibration_history: number[];
  motor_current_history: number[];
  temperature_history: number[];
  pressure_history: number[];
  flow_history: number[];
}

export interface DecisionOption {
  action_id: string;
  name: string;
  direct_cost: number;
  risk_score: number;
  failure_probability: number;
  post_action_load: number;
  net_expected_loss: number;
  requires_human_approval: boolean;
  justification: string;
}

export interface DecisionResponse {
  options: DecisionOption[];
  recommended_action: string;
  risk_tolerance: number;
  hourly_downtime_cost: number;
}

export interface PrognosticsResult {
  rul_hours: number;
  degradation_velocity: number;
  limiting_factor: string;
  confidence: number;
  z_current: number;
}

export interface SustainabilityMetrics {
  excess_power_kw?: number;
  excess_kw?: number;
  avoidable_co2_kg_per_h?: number;
  co2_kg_hr?: number;
  co2_waste_kg_h?: number;
  annual_carbon_waste_tonnes?: number;
  annual_co2_tonnes?: number;
  annual_penalty_t?: number;
  avoidable_waste_percent?: number;
  waste_percentage?: number;
}

export interface EvidencePart {
  observation: string;
  expected: string;
  physics_interpretation: string;
  action_rationale: string;
}

export interface GuardrailStatus {
  approved: boolean;
  human_in_the_loop_required: boolean;
  safety_envelope_violated: boolean;
  notes: string;
}

export interface SnapshotResponse {
  run_id: string;
  step: number;
  health_score: number;
  telemetry: TelemetryRecord;
  alert_state: string;
  persistence_count: number;
  multi_sensor_confirmed: boolean;
  evidence_card: EvidencePart;
  decision_options: DecisionOption[];
  recommended_action: string;
  guardrails: GuardrailStatus;
  prognostics: PrognosticsResult;
  sustainability: SustainabilityMetrics;
}
