# 京东小家 for Home Assistant

这是一个非官方 Home Assistant 自定义集成，用于接入京东小家 App 中的空调设备。

本仓库的目标是把京东小家空调控制 API 封装成 Home Assistant custom integration。它不隶属于京东、京东小家或 Home Assistant。

[English README](README.md)

## 用途

这个仓库适合已经拥有通过京东小家操控的空调，并且可以从 App 本地抓包中提取会话信息的用户。这里的空调不是指京东品牌空调，而是指接入京东小家的空调设备，例如 KFR 35GW 这类壁挂式空调。

## 功能

- 空调实体：开关、模式、目标温度、风速、上下风、睡眠模式。
- 开关实体：背光灯、屏显、强力。
- 选择实体：左右风。
- 传感器：当前温度、当前湿度和若干诊断值。
- 支持 UI 配置流程。
- 支持 `tgt` token 刷新。

## 安装

### HACS

在 HACS 中添加自定义仓库：

```text
https://github.com/orangeboyChen/jd-smart-ac
```

类型选择：

```text
Integration
```

安装后重启 Home Assistant，然后进入：

```text
设置 -> 设备与服务 -> 添加集成 -> 京东小家
```

### 手动安装

把本仓库中的集成复制到 Home Assistant 配置目录：

```text
config/custom_components/jd_smart_ac/
```

重启 Home Assistant，然后进入：

```text
设置 -> 设备与服务 -> 添加集成 -> 京东小家
```

## 配置

需要从一个可正常使用的京东小家 App 会话中获取请求参数。可以使用 Stream、Proxyman、Charles、HTTP Toolkit 或 mitmproxy 等工具抓取 HTTPS 请求。

请打开空调页面并抓取成功调用：

```text
https://api.smart.jd.com/c/service/integration/v1/getDeviceSnapshot_v1
```

尽量从同一次请求中复制所有字段。

`feed_id`

空调设备的 feed ID，位于请求 body：

```json
{"json":{"feed_id":"YOUR_FEED_ID","digest":"","pullMode":0,"version":"2.0"}}
```

`cookie`

抓包中的完整 `Cookie` 请求头。

`tgt`

抓包中的 `tgt` 请求头。

`pin`

可选京东账号 PIN，用于 token 刷新。

`sgm_context`

抓包中的 `Sgm-Context` 请求头。UI 中是可选项，如果抓包里有，建议填写。

`device_id`

请求 URL 中的 `device_id` 参数。留空时集成会自动生成，建议使用抓包值。

`platform`

请求 URL 中的 `plat` 参数原值。不要猜这个字段，应直接复制抓包中的值。当前已确认的 iOS 抓包值是 `iPhone`；其他平台以实际抓包为准。

`app_version`

请求 URL 中的 `app_version` 参数，同时也对应 `appversion` 请求头。

`device_model`

请求 URL 中的 `hard_platform` 参数，同时也对应 `appplatform` 请求头。

`platform_version`

请求 URL 中的 `plat_version` 参数，同时也对应 `appplatformversion` 请求头。

`channel`

请求 URL 中的 `channel` 参数。

`user_agent`

请求中的 `User-Agent`。

## 实体

空调实体支持电源、模式、目标温度、当前温度、当前湿度、风速、上下风和睡眠模式。目标温度范围为 18-32 摄氏度，步进 1 摄氏度。

开关实体包括背光灯、屏显和强力。

选择实体用于左右风。

传感器实体包括当前温度、当前湿度，以及 TVOC、运行时间、蜂鸣器原始值、MDP 模式、保护状态等诊断值。
