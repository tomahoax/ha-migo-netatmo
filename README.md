# MiGo (Netatmo) - Integration for Home Assistant

[![GitHub Release](https://img.shields.io/github/release/tomahoax/ha-migo-netatmo.svg)](https://github.com/tomahoax/ha-migo-netatmo/releases)
[![License](https://img.shields.io/github/license/tomahoax/ha-migo-netatmo.svg)](https://github.com/tomahoax/ha-migo-netatmo/blob/main/LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![codecov](https://codecov.io/gh/tomahoax/ha-migo-netatmo/graph/badge.svg)](https://codecov.io/gh/tomahoax/ha-migo-netatmo)

Home Assistant integration for **Saunier Duval** thermostats controlled via the **MiGO** app (Netatmo API).

> [!WARNING]
> This integration is not affiliated with Saunier Duval or Netatmo. The developers take no responsibility for any issues that may occur with your devices following the use of this integration.

## Why this integration?

Many Saunier Duval users in France, Italy, and Spain have tried to use the excellent [myPyllant integration](https://github.com/signalkraft/mypyllant-component) to connect their thermostat to Home Assistant, only to face authentication failures despite valid credentials.

The reason? **The MiGo app uses a completely different API than myVAILLANT**. MiGo authenticates through the Netatmo API (`app.netatmo.net`), while myPyllant uses the Vaillant Identity infrastructure (`identity.vaillant-group.com`). These are two entirely separate and incompatible systems (see [myPyllant issue #336](https://github.com/signalkraft/mypyllant-component/issues/336)).

This integration was created to fill that gap by reverse-engineering the Netatmo API used by the MiGo iOS app.

## Compatibility

> [!IMPORTANT]
> This integration is **ONLY** intended for users of the iOS/Android app:
>
> **[MiGo](https://apps.apple.com/app/migo-your-heating-assistant/id1023682652)**
>
> This integration **DOES NOT WORK** with the **MiGO Link** app (different API).

### How to identify which app you use?

| Application | Icon | This integration |
|-------------|:----:|------------------|
| **MiGo** | <img src="docs/images/migo-app-icon.png" width="40"> | **Compatible** |
| **MiGO Link** | <img src="docs/images/migo-link-app-icon.png" width="40"> | Not compatible |

### Tested boilers

- Saunier Duval Isotwin Condens 25-A

## Features

### Device Architecture

This integration creates **two separate devices** in Home Assistant:

1. **Gateway (NAVaillant)** - The main communication hub
   - Connected to your boiler via eBus
   - Provides WiFi connectivity
   - Controls DHW (Domestic Hot Water)

2. **Thermostat (NAThermVaillant)** - The wall-mounted thermostat
   - Connected to the Gateway via RF (radio)
   - Battery powered
   - Measures room temperature
   - Linked to Gateway via `via_device` relationship

### Climate Entity

- Display current temperature
- Set target temperature
- Change mode:
  - **Auto** (Schedule mode)
  - **Heat** (Manual mode)
  - **Off** (Frost guard)
- Preset modes:
  - **Away** - Away mode
  - **Hot water only** - Heating off, DHW only
  - **Frost guard** - Minimum temperature protection

### Sensors

#### Gateway Sensors
- Outdoor temperature
- WiFi signal strength
- Gateway firmware version

#### Thermostat Sensors
- Temperature sensor per room
- Humidity sensor per room (if available)
- Battery level
- RF signal strength
- Thermostat firmware version

#### Energy Consumption
- **Daily boiler runtime** - Tracks boiler operation time in seconds (compatible with Energy Dashboard via `state_class: total_increasing`)

### Switches

- **DHW boost** (hot water boost) - Gateway
- **Heating anticipation** (enable/disable) - Home setting

### Number Controls (Configuration)

#### Gateway Controls
- **DHW temperature** (45°C - 60°C)
- **Hysteresis threshold** (0.1°C - 2.0°C)

#### Home Controls
- **Manual setpoint duration** (5 min - 12 hours)

#### Room Controls
- **Temperature offset** per room (-5.0°C to +5.0°C)

### Binary Sensors

#### Gateway Binary Sensors
- eBus error
- Boiler error

#### Thermostat Binary Sensors
- Boiler status (running/idle)
- Device reachable

### Select

- Thermostat mode (Auto/Away/Frost guard)
- Active schedule

### Button

- Manual refresh

## Configuration Options

After installation, you can configure the integration options:

1. Go to **Settings** → **Devices & services**
2. Find **MiGo (Netatmo)** and click **Configure**
3. Adjust the following settings:

| Option | Description | Range | Default |
|--------|-------------|-------|---------|
| **Update interval** | How often to poll the API for updates | 60 - 3600 seconds | 300 seconds (5 min) |

> [!TIP]
> Lower polling intervals provide more responsive updates but may increase API load. A 5-minute interval is recommended for normal use.

## Installation

### HACS (Recommended)

[HACS](https://hacs.xyz/) (Home Assistant Community Store) is the recommended way to install this integration.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tomahoax&repository=ha-migo-netatmo&category=integration)

1. Click the button above to add this custom repository to HACS
2. Install the **MiGo (Netatmo)** integration from HACS
3. **Restart Home Assistant** (Settings → System → Restart)

<details>
<summary>Manual HACS installation (if button doesn't work)</summary>

#### Prerequisites

- HACS must be installed in your Home Assistant instance
- If you don't have HACS yet, follow the [official HACS installation guide](https://hacs.xyz/docs/use/)

#### Step 1: Add the custom repository

1. Open Home Assistant and go to **HACS** in the sidebar
2. Click on **Integrations**
3. Click the **⋮** (three dots menu) in the top right corner
4. Select **Custom repositories**
5. In the dialog that opens:
   - **Repository**: `https://github.com/tomahoax/ha-migo-netatmo`
   - **Category**: Select `Integration`
6. Click **Add**

#### Step 2: Install the integration

1. Still in HACS → Integrations, click **+ Explore & Download Repositories**
2. Search for **"MiGo"** or **"MiGo Netatmo"**
3. Click on the integration in the search results
4. Click **Download** in the bottom right corner
5. Select the latest version and click **Download**
6. **Restart Home Assistant** (Settings → System → Restart)

</details>

### Configure the integration

After restart:

1. Go to **Settings** → **Devices & services**
2. Click **+ Add Integration**
3. Search for **"MiGo"**
4. Enter your MiGO app credentials (email and password)
5. Click **Submit**

Your devices should now appear in Home Assistant!

### Advanced Configuration

You can optionally provide custom OAuth credentials:

- **Client ID** (optional) - Custom OAuth client ID
- **Client Secret** (optional) - Custom OAuth client secret

Leave these empty to use the default MiGO app credentials.

### Manual Installation

If you prefer not to use HACS:

1. Download the [latest release](https://github.com/tomahoax/ha-migo-netatmo/releases) (zip file)
2. Extract the archive
3. Copy the `custom_components/migo_netatmo` folder to your Home Assistant `config/custom_components/` directory
4. Restart Home Assistant
5. Configure the integration via Settings → Devices & services → Add Integration

## Energy Dashboard Integration

The **Daily boiler runtime** sensor can be used to track heating usage in the Home Assistant Energy Dashboard:

1. Go to **Settings** → **Dashboards** → **Energy**
2. Under **Gas consumption** or **Individual devices**, add the boiler runtime sensor
3. The sensor uses `state_class: total_increasing` for proper energy tracking

> [!NOTE]
> The sensor reports boiler runtime in seconds. To estimate energy consumption, you can create a template sensor that multiplies runtime by your boiler's power rating.

Example template sensor for estimated gas consumption:
```yaml
template:
  - sensor:
      - name: "Estimated Gas Consumption"
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        state: >
          {% set runtime_seconds = states('sensor.migo_thermostat_daily_boiler_runtime') | float(0) %}
          {% set boiler_power_kw = 25 %}  {# Adjust to your boiler's power #}
          {{ (runtime_seconds / 3600 * boiler_power_kw) | round(2) }}
```

## Troubleshooting

### Authentication failed

- Verify that your credentials work in the MiGO app
- Make sure you are using the correct app (MiGo. Your Heating Assistant, not MiGO Link)
- Check that at least one home is configured in your account

### No entities appear

- Check Home Assistant logs for errors
- Verify that your thermostat is properly connected in the MiGO app

### Two devices not showing

- Make sure you have both a gateway (NAVaillant) and thermostat (NAThermVaillant) in your MiGO setup
- The integration will only create devices for modules found in the API response

### Enable debug logs

Add this to your `configuration.yaml` and restart Home Assistant:

```yaml
logger:
  default: warning
  logs:
    custom_components.migo_netatmo: debug
```

## Technical Details

This integration uses the Netatmo API (`app.netatmo.net`) which is the backend for the MiGO app. It was developed through reverse engineering of the iOS app to provide a Home Assistant integration for users who cannot use the myVAILLANT/MiGO Link ecosystem.

### API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `/oauth2/token` | Authentication |
| `/api/homesdata` | Home structure and configuration |
| `/api/homestatus` | Real-time status |
| `/api/getroommeasure` | Historical data and consumption |
| `/api/setstate` | Control room temperature and DHW |
| `/api/setthermmode` | Set global mode |
| `/api/sethomedata` | Home settings (anticipation, duration) |
| `/syncapi/v1/setconfigs` | DHW temperature, offsets |
| `/api/changeheatingalgo` | Hysteresis settings |

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

This integration is provided as-is, without warranty. Use at your own risk.
