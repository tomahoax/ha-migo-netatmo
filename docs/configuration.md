# Configuration

This page describes all available configuration options for the MiGo integration.

## Initial Setup

The integration is configured through the UI. During setup, you'll need:

| Field | Description |
|-------|-------------|
| Email | Your MiGO app email address |
| Password | Your MiGO app password |

## Integration Options

Currently, the integration has no additional configurable options after setup. All settings are managed through the created entities.

## Entity Configuration

### Climate Entity

The climate entity provides thermostat control:

| Feature | Description |
|---------|-------------|
| HVAC Modes | Off, Heat, Auto |
| Preset Modes | Away, Hot water only, Frost guard |
| Temperature Range | 7°C - 30°C |
| Temperature Step | 0.5°C |

### Number Entities

Configuration entities for fine-tuning:

| Entity | Range | Step | Description |
|--------|-------|------|-------------|
| DHW Temperature | 45°C - 60°C | 1°C | Domestic hot water setpoint |
| Manual Setpoint Duration | 5 - 720 min | 5 min | Duration for manual temperature changes |
| Temperature Offset | -5.0°C - +5.0°C | 0.5°C | Per-room temperature calibration |
| Hysteresis Threshold | 0.1°C - 2.0°C | 0.1°C | Temperature deadband for heating |

### Switch Entities

Toggle controls:

| Entity | Description |
|--------|-------------|
| DHW Boost | Temporarily boost hot water temperature |
| Heating Anticipation | Enable/disable predictive heating |

### Select Entities

Dropdown selections:

| Entity | Options | Description |
|--------|---------|-------------|
| Thermostat Mode | Auto, Away, Frost guard | Global operating mode |
| Active Schedule | (Your schedules) | Select active heating schedule |

## Debug Logging

To enable debug logging, add this to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.migo_netatmo: debug
```

This will log all API calls and entity updates, useful for troubleshooting.

## Data Refresh

The integration polls the API every 5 minutes by default. You can force a refresh using the "Refresh" button entity.
