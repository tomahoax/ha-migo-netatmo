# Troubleshooting

This guide helps you resolve common issues with the MiGo integration.

## Authentication Issues

### "Invalid authentication" error

**Symptoms**: Cannot add the integration, authentication fails.

**Solutions**:
1. Verify credentials work in the MiGO mobile app
2. Check you're using the correct app:
   - **Correct**: MiGo (orange flame icon)
   - **Incorrect**: MiGO Link (different API)
3. Ensure at least one home is configured in the app
4. Try resetting your password in the MiGO app

### Token refresh failures

**Symptoms**: Integration works initially but stops after some time.

**Solutions**:
1. Check Home Assistant logs for token errors
2. Remove and re-add the integration
3. Ensure your account is not locked (try the app)

## Entity Issues

### No entities appear

**Symptoms**: Integration added successfully but no entities are created.

**Solutions**:
1. Check Home Assistant logs for errors:
   ```yaml
   logger:
     logs:
       custom_components.migo_netatmo: debug
   ```
2. Verify thermostat is connected in the MiGO app
3. Check that your home has rooms configured
4. Restart Home Assistant

### Entities show "unavailable"

**Symptoms**: Entities exist but show unavailable state.

**Solutions**:
1. Check your internet connection
2. Verify the MiGO app can connect
3. Check logs for API errors
4. Use the Refresh button to force an update

### Temperature not updating

**Symptoms**: Current temperature is stale or incorrect.

**Solutions**:
1. Data refreshes every 5 minutes by default
2. Use the Refresh button for immediate update
3. Check if the thermostat batteries are low
4. Verify RF signal strength is adequate

## Control Issues

### Temperature changes not applied

**Symptoms**: Setting temperature in HA doesn't affect the thermostat.

**Solutions**:
1. Check logs for API errors
2. Verify the same change works in the MiGO app
3. Ensure you're in the correct mode (Manual for direct control)
4. Check if schedule is overriding your setting

### Mode changes reset

**Symptoms**: HVAC mode changes back automatically.

**Solutions**:
1. Check the manual setpoint duration setting
2. In Auto mode, the schedule controls temperature
3. Use Heat mode for manual control

## Network Issues

### API timeout errors

**Symptoms**: Logs show timeout or connection errors.

**Solutions**:
1. Check your internet connection
2. Verify Netatmo services are operational
3. Check if a firewall is blocking `app.netatmo.net`
4. Try increasing the timeout (advanced)

### SSL/TLS errors

**Symptoms**: Certificate or SSL errors in logs.

**Solutions**:
1. Ensure system time is correct
2. Update Home Assistant to latest version
3. Check for proxy interference

## Debug Logging

Enable debug logging to diagnose issues:

```yaml
logger:
  default: warning
  logs:
    custom_components.migo_netatmo: debug
```

### Reading Logs

Look for these patterns:

| Pattern | Meaning |
|---------|---------|
| `API request failed` | Network or API error |
| `Authentication failed` | Credential issue |
| `Token expired` | Need to refresh token |
| `Device not found` | Configuration problem |

## Getting Help

If you can't resolve the issue:

1. Check [existing issues](https://github.com/tomahoax/ha-migo-netatmo/issues)
2. Enable debug logging and capture relevant logs
3. [Open a new issue](https://github.com/tomahoax/ha-migo-netatmo/issues/new/choose) with:
   - Home Assistant version
   - Integration version
   - Relevant logs (redact credentials)
   - Steps to reproduce
