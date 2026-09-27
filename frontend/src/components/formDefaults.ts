import type { DeviceConfig } from "../api/client";

export const deviceDefaults: DeviceConfig = {
  name: "",
  ip: "",
  port: 502,
  unit_id: 1,
  address: 0,
  quantity: 10,
  function: "03",
  expected: "",
  address_mode: "dec",
  connect_timeout_ms: 3000,
  response_timeout_ms: 1000,
  scan_rate_ms: 1000,
  delay_between_polls_ms: 20,
  enabled: true,
  check_profile: "full_stack",
};
