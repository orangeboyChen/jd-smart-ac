# JD Smart for Home Assistant

Unofficial Home Assistant custom integration for air conditioners controlled through the JD Smart / JD Xiaojia app.

This repository packages the JD Smart air-conditioner control API as a Home Assistant custom integration. It is not affiliated with JD.com, JD Smart, JD Xiaojia, or Home Assistant.

[简体中文 README](README_zh-Hans.md)

## Purpose

This repository is for users who own an air conditioner controlled through the JD Smart / JD Xiaojia app and can extract session values from a local app traffic capture. This does not mean JD-branded air conditioners only; it means air conditioners connected to JD Smart / JD Xiaojia, such as KFR 35GW style wall-mounted units.

## Features

- Climate entity for power, HVAC mode, target temperature, fan speed, vertical swing, and sleep preset.
- Switch entities for backlight, display, and eco mode.
- Select entity for horizontal swing direction.
- Sensor entities for current temperature, humidity, and diagnostic values.
- Config flow UI.
- `tgt` token refresh support.

## Installation

### HACS

Add this repository as a HACS custom repository:

```text
https://github.com/orangeboyChen/jd-smart-ac
```

Repository type:

```text
Integration
```

Install it from HACS, restart Home Assistant, then add the integration from:

```text
Settings -> Devices & services -> Add integration -> JD Smart
```

### Manual

Copy the integration into your Home Assistant configuration directory:

```text
config/custom_components/jd_smart_ac/
```

Restart Home Assistant, then add the integration from:

```text
Settings -> Devices & services -> Add integration -> JD Smart
```

## Configuration

You need values from a working JD Smart / JD Xiaojia mobile app session. You can capture HTTPS traffic with a tool such as Stream, Proxyman, Charles, HTTP Toolkit, or mitmproxy.

Open the air conditioner page and capture a successful request to:

```text
https://api.smart.jd.com/c/service/integration/v1/getDeviceSnapshot_v1
```

Use values from the same request whenever possible.

`feed_id`

The air conditioner feed ID. It appears in the request body:

```json
{"json":{"feed_id":"YOUR_FEED_ID","digest":"","pullMode":0,"version":"2.0"}}
```

`cookie`

The full `Cookie` request header from the captured app request.

`tgt`

The `tgt` request header from the captured app request.

`pin`

Optional JD account PIN, used for token refresh.

`sgm_context`

The `Sgm-Context` request header. It is optional in the UI, but copy it if your working capture contains it.

`device_id`

The `device_id` query parameter from the request URL. If left empty, the integration generates one, but using the captured value is recommended.

`platform`

The exact `plat` query parameter from your capture. Do not guess this value. The confirmed iOS capture used `iPhone`; other platforms should use the captured value.

`app_version`

The `app_version` query parameter and `appversion` request header.

`device_model`

The `hard_platform` query parameter and `appplatform` request header.

`platform_version`

The `plat_version` query parameter and `appplatformversion` request header.

`channel`

The `channel` query parameter.

`user_agent`

The request `User-Agent` header.

## Entities

The climate entity supports power, HVAC mode, target temperature, current temperature, current humidity, fan speed, vertical swing, and sleep preset. The target temperature range is 18-32 C with 1 C steps.

Switch entities include backlight, display, and eco mode.

The select entity controls horizontal swing direction.

Sensor entities include current temperature, current humidity, TVOC, runtime counters, speaker raw value, MDP mode, protection state, and other diagnostic values.
