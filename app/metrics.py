from prometheus_client import Gauge

SCI_SCORE_GAUGE = Gauge(
    "greenscope_sci_score_gco2_per_request",
    "SCI score in gCO2e per request",
    ["app"],
)

ENERGY_GAUGE = Gauge(
    "greenscope_energy_kwh",
    "Energy consumption in kWh",
    ["app"],
)

CARBON_INTENSITY_GAUGE = Gauge(
    "greenscope_carbon_intensity_gco2_per_kwh",
    "Grid carbon intensity in gCO2eq per kWh",
)

REQUEST_COUNT_GAUGE = Gauge(
    "greenscope_request_count",
    "HTTP request count per calculation period",
    ["app"],
)

OPERATIONAL_EMISSIONS_GAUGE = Gauge(
    "greenscope_operational_emissions_gco2",
    "Operational emissions in gCO2e",
    ["app"],
)

EMBODIED_EMISSIONS_GAUGE = Gauge(
    "greenscope_embodied_emissions_gco2",
    "Embodied emissions in gCO2e",
    ["app"],
)
