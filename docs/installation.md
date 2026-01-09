# Installation Guide

This guide walks you through installing the MiGo integration for Home Assistant.

## Prerequisites

- Home Assistant 2024.1.0 or later
- HACS (recommended) or manual installation
- MiGO app credentials (email and password)

## HACS Installation (Recommended)

[HACS](https://hacs.xyz/) (Home Assistant Community Store) is the recommended installation method.

### Quick Install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tomahoax&repository=ha-migo-netatmo&category=integration)

1. Click the button above
2. Click "Download" in HACS
3. Restart Home Assistant

### Manual HACS Install

If the button doesn't work:

1. Open HACS in the sidebar
2. Click **Integrations**
3. Click the **⋮** menu → **Custom repositories**
4. Add:
   - Repository: `https://github.com/tomahoax/ha-migo-netatmo`
   - Category: `Integration`
5. Search for "MiGo" and download
6. Restart Home Assistant

## Manual Installation

1. Download the [latest release](https://github.com/tomahoax/ha-migo-netatmo/releases)
2. Extract the archive
3. Copy `custom_components/migo_netatmo` to your `config/custom_components/` directory
4. Restart Home Assistant

## Configuration

After installation and restart:

1. Go to **Settings** → **Devices & services**
2. Click **+ Add Integration**
3. Search for **"MiGo"**
4. Enter your MiGO app credentials
5. Click **Submit**

Your thermostat should now appear in Home Assistant.

## Updating

### Via HACS

1. Open HACS → Integrations
2. Find MiGo integration
3. Click **Update** if available
4. Restart Home Assistant

### Manual Update

1. Download the latest release
2. Replace the `custom_components/migo_netatmo` folder
3. Restart Home Assistant
